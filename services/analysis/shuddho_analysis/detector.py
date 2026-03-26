from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from ml.detector.labels import DETECTOR_LABEL_TO_CATEGORY
from ml.detector.runtime import BanglaDetectorRuntime
from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import Suggestion, SuggestionSeverity, SuggestionSource

from .models import DetectorFinding

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.82
DETECTOR_CHECKPOINT_ENV_VAR = "SHUDDHO_DETECTOR_CHECKPOINT"
DETECTOR_THRESHOLD_ENV_VAR = "SHUDDHO_DETECTOR_THRESHOLD"
LEGACY_DETECTOR_THRESHOLD_ENV_VAR = "SHUDDHO_DETECTOR_CONFIDENCE_THRESHOLD"


class DetectorService:
    def __init__(
        self,
        runtime: BanglaDetectorRuntime | None = None,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        checkpoint_path: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.confidence_threshold = confidence_threshold
        self.checkpoint_path = checkpoint_path

        # Keep the runtime's internal prediction gate aligned with the service-level threshold.
        if self.runtime is not None and hasattr(self.runtime, "confidence_threshold"):
            self.runtime.confidence_threshold = confidence_threshold

    def is_loaded(self) -> bool:
        return self.runtime is not None

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "DetectorService":
        environment = os.environ if environ is None else environ
        checkpoint_path = environment.get(DETECTOR_CHECKPOINT_ENV_VAR)
        threshold_value = environment.get(DETECTOR_THRESHOLD_ENV_VAR)
        threshold_env_var = DETECTOR_THRESHOLD_ENV_VAR
        if threshold_value is None:
            threshold_value = environment.get(LEGACY_DETECTOR_THRESHOLD_ENV_VAR)
            threshold_env_var = LEGACY_DETECTOR_THRESHOLD_ENV_VAR

        confidence_threshold = cls._resolve_confidence_threshold(
            threshold_value,
            env_var_name=threshold_env_var,
        )
        return cls.from_checkpoint_path(
            checkpoint_path,
            confidence_threshold=confidence_threshold,
        )

    @classmethod
    def from_checkpoint_path(
        cls,
        checkpoint_path: str | None,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> "DetectorService":
        normalized_checkpoint_path = checkpoint_path.strip() if checkpoint_path else None
        if not normalized_checkpoint_path:
            logger.warning(
                "%s is not set; detector runtime is disabled and analyze requests will fall back to rules and spell checks only.",
                DETECTOR_CHECKPOINT_ENV_VAR,
            )
            return cls(confidence_threshold=confidence_threshold)

        try:
            runtime = BanglaDetectorRuntime.load(normalized_checkpoint_path)
        except FileNotFoundError:
            logger.warning(
                "Detector checkpoint was not found at '%s'; detector runtime is disabled and analyze requests will fall back to rules and spell checks only.",
                normalized_checkpoint_path,
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
            )
        except (OSError, RuntimeError, KeyError, ValueError) as error:
            logger.warning(
                "Detector checkpoint at '%s' could not be loaded (%s); detector runtime is disabled and analyze requests will fall back to rules and spell checks only.",
                normalized_checkpoint_path,
                error,
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
            )

        return cls(
            runtime=runtime,
            confidence_threshold=confidence_threshold,
            checkpoint_path=normalized_checkpoint_path,
        )

    def detect(
        self,
        *,
        text: str,
        normalized: NormalizedText,
        rule_suggestions: list[Suggestion],
    ) -> list[DetectorFinding]:
        if not self.is_loaded():
            return []

        findings: list[DetectorFinding] = []
        for prediction in self.runtime.predict(text):
            if prediction.confidence < self.confidence_threshold:
                continue
            if any(self._overlaps_rule(prediction.start, prediction.end, suggestion) for suggestion in rule_suggestions):
                continue

            category = DETECTOR_LABEL_TO_CATEGORY.get(prediction.label)
            if category is None:
                continue

            findings.append(
                DetectorFinding(
                    rule_id=f"DET_{prediction.label.upper()}",
                    category=category,
                    subtype=f"detector_{prediction.label}",
                    span_start=prediction.start,
                    span_end=prediction.end,
                    original_text=prediction.text,
                    replacement_options=(),
                    confidence=round(prediction.confidence, 2),
                    explanation_bn=f"মডেলটি এই অংশে {prediction.label} ধরনের সমস্যা অনুমান করেছে।",
                    explanation_en=f"The detector estimated a {prediction.label} issue in this span.",
                    severity=SuggestionSeverity.LOW,
                    source=SuggestionSource.MODEL,
                )
            )
        return findings

    def _overlaps_rule(self, start: int, end: int, suggestion: Suggestion) -> bool:
        return start < suggestion.span_end and suggestion.span_start < end

    @staticmethod
    def _resolve_confidence_threshold(value: str | None, *, env_var_name: str) -> float:
        if value is None or not value.strip():
            return DEFAULT_CONFIDENCE_THRESHOLD

        try:
            threshold = float(value)
        except ValueError:
            logger.warning(
                "Invalid %s value '%s'; expected a number between 0.0 and 1.0. Falling back to %.2f.",
                env_var_name,
                value,
                DEFAULT_CONFIDENCE_THRESHOLD,
            )
            return DEFAULT_CONFIDENCE_THRESHOLD

        if not 0.0 <= threshold <= 1.0:
            logger.warning(
                "Out-of-range %s value %.4f; expected a number between 0.0 and 1.0. Falling back to %.2f.",
                env_var_name,
                threshold,
                DEFAULT_CONFIDENCE_THRESHOLD,
            )
            return DEFAULT_CONFIDENCE_THRESHOLD

        return threshold
