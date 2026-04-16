from __future__ import annotations

import logging
import math
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ml.detector.labels import DETECTOR_ID_TO_LABEL, DETECTOR_LABEL_TO_CATEGORY, normalize_detector_label
from ml.detector.runtime import BanglaDetectorRuntime, DetectorPrediction
from ml.training.dataset import tokenize_with_offsets
from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import Suggestion, SuggestionSeverity, SuggestionSource

from .models import DetectorFinding

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.92
DETECTOR_ENABLED_ENV_VAR = "SHUDDHO_DETECTOR_ENABLED"
DETECTOR_CHECKPOINT_ENV_VAR = "SHUDDHO_DETECTOR_CHECKPOINT"
DETECTOR_THRESHOLD_ENV_VAR = "SHUDDHO_DETECTOR_THRESHOLD"
LEGACY_DETECTOR_THRESHOLD_ENV_VAR = "SHUDDHO_DETECTOR_CONFIDENCE_THRESHOLD"
RUNTIME_CHECKPOINT_REQUIRED_FILES = ("metadata.json", "best_model.pt")
SCAFFOLD_CHECKPOINT_MARKER_FILES = ("config.json",)
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHECKPOINT_RELATIVE_PATH = Path("artifacts") / "detector" / "detector-base"
DEFAULT_CHECKPOINT_DISPLAY_PATH = DEFAULT_CHECKPOINT_RELATIVE_PATH.as_posix()
DETECTOR_ENABLED_AUTO_VALUE = "auto"


@dataclass(frozen=True)
class DetectorRuntimeStatus:
    enabled: bool
    loaded: bool
    status: str
    reason: str | None
    checkpoint: str | None
    checkpoint_exists: bool
    backend_name: str
    threshold: float


@dataclass(frozen=True)
class DetectorTokenPrediction:
    token: str
    start: int
    end: int
    label: str
    confidence: float


@runtime_checkable
class TokenSpanDetectorBackend(Protocol):
    backend_name: str
    checkpoint_path: str | None
    confidence_threshold: float

    def predict(self, text: str) -> list[DetectorPrediction]:
        ...

    def predict_token_spans(self, text: str) -> list[DetectorTokenPrediction]:
        ...


class RuntimeSpanDetectorAdapter:
    backend_name = "shuddho_detector_runtime"

    def __init__(
        self,
        runtime: Any,
        *,
        checkpoint_path: str | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.runtime = runtime
        self.checkpoint_path = checkpoint_path
        self.confidence_threshold = confidence_threshold
        if hasattr(self.runtime, "confidence_threshold"):
            self.runtime.confidence_threshold = confidence_threshold

    def predict(self, text: str) -> list[DetectorPrediction]:
        return list(self.runtime.predict(text))

    def predict_token_spans(self, text: str) -> list[DetectorTokenPrediction]:
        span_predictions = self.predict(text)
        tokens = tokenize_with_offsets(text)
        token_predictions: list[DetectorTokenPrediction] = []

        for token in tokens:
            supporting_prediction = _best_supporting_span_prediction(
                token.start,
                token.end,
                span_predictions,
            )
            if supporting_prediction is None:
                token_predictions.append(
                    DetectorTokenPrediction(
                        token=token.text,
                        start=token.start,
                        end=token.end,
                        label="ok",
                        confidence=1.0,
                    )
                )
                continue

            token_predictions.append(
                DetectorTokenPrediction(
                    token=token.text,
                    start=token.start,
                    end=token.end,
                    label=supporting_prediction.label,
                    confidence=supporting_prediction.confidence,
                )
            )

        return token_predictions


class BanglaBertTokenClassifierScaffold:
    backend_name = "banglabert_token_classifier"

    def __init__(
        self,
        *,
        model: Any | None = None,
        tokenizer: Any | None = None,
        id_to_label: Mapping[int, str] | None = None,
        max_length: int = 256,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        checkpoint_path: str | None = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.id_to_label = {
            int(index): normalize_detector_label(label)
            for index, label in (id_to_label or DETECTOR_ID_TO_LABEL).items()
        }
        self.max_length = max_length
        self.confidence_threshold = confidence_threshold
        self.checkpoint_path = checkpoint_path

    def is_loaded(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    @classmethod
    def load(
        cls,
        checkpoint_path: str | Path,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> "BanglaBertTokenClassifierScaffold":
        checkpoint_dir = Path(checkpoint_path)
        if not checkpoint_dir.exists():
            raise FileNotFoundError(checkpoint_dir)

        try:
            from transformers import AutoModelForTokenClassification, AutoTokenizer
        except (ImportError, OSError) as error:
            raise RuntimeError("Transformers is required to load BanglaBERT detector checkpoints") from error

        tokenizer = AutoTokenizer.from_pretrained(checkpoint_dir)
        model = AutoModelForTokenClassification.from_pretrained(checkpoint_dir)
        raw_id_to_label = getattr(model.config, "id2label", None) or DETECTOR_ID_TO_LABEL
        id_to_label = {
            int(index): normalize_detector_label(label)
            for index, label in raw_id_to_label.items()
        }
        max_length = int(
            min(
                getattr(model.config, "max_position_embeddings", 256),
                getattr(tokenizer, "model_max_length", 256),
            )
        )
        return cls(
            model=model,
            tokenizer=tokenizer,
            id_to_label=id_to_label,
            max_length=max_length,
            confidence_threshold=confidence_threshold,
            checkpoint_path=str(checkpoint_dir),
        )

    def predict(self, text: str) -> list[DetectorPrediction]:
        token_predictions = self.predict_token_spans(text)
        return _collapse_token_predictions(
            text,
            token_predictions,
            confidence_threshold=self.confidence_threshold,
        )

    def predict_token_spans(self, text: str) -> list[DetectorTokenPrediction]:
        if not self.is_loaded():
            return []

        encoded = self._tokenize(text)
        offsets = _extract_offset_mapping(encoded.get("offset_mapping", []))
        if not offsets:
            return []

        logits = self._forward(encoded)
        if not logits:
            return []

        token_predictions: list[DetectorTokenPrediction] = []
        for offset, token_logits in zip(offsets, logits):
            start, end = offset
            if end <= start:
                continue
            probabilities = _softmax(token_logits)
            predicted_index = _argmax(probabilities)
            label = self.id_to_label.get(predicted_index, "ok")
            confidence = round(float(probabilities[predicted_index]), 4)
            if label != "ok" and confidence < self.confidence_threshold:
                label = "ok"
            token_predictions.append(
                DetectorTokenPrediction(
                    token=text[start:end],
                    start=start,
                    end=end,
                    label=label,
                    confidence=confidence,
                )
            )

        return token_predictions

    def _tokenize(self, text: str) -> Mapping[str, Any]:
        return self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            return_offsets_mapping=True,
        )

    def _forward(self, encoded: Mapping[str, Any]) -> list[list[float]]:
        model_inputs = {
            key: _ensure_batched(value)
            for key, value in encoded.items()
            if key != "offset_mapping"
        }
        outputs = _call_model(self.model, model_inputs)
        logits = outputs["logits"] if isinstance(outputs, Mapping) else getattr(outputs, "logits")
        batched_logits = _to_python(logits)
        if batched_logits and isinstance(batched_logits[0], list) and batched_logits[0] and isinstance(batched_logits[0][0], list):
            return batched_logits[0]
        return batched_logits


class DetectorService:
    def __init__(
        self,
        runtime: Any | None = None,
        *,
        backend: TokenSpanDetectorBackend | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        checkpoint_path: str | None = None,
        enabled: bool | None = None,
        status: str | None = None,
        reason: str | None = None,
        checkpoint_exists: bool | None = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.checkpoint_path = checkpoint_path.strip() if checkpoint_path else None
        self.backend = backend or self._coerce_backend(
            runtime,
            confidence_threshold=confidence_threshold,
            checkpoint_path=self.checkpoint_path,
        )
        self.runtime = runtime if backend is None else getattr(backend, "runtime", runtime)
        self.enabled = self.backend is not None if enabled is None else enabled
        if checkpoint_exists is None:
            _, resolved_checkpoint_path = self._resolve_checkpoint_path(self.checkpoint_path)
            checkpoint_exists = bool(resolved_checkpoint_path and resolved_checkpoint_path.exists())
        self.checkpoint_exists = checkpoint_exists
        if self.backend is not None and status is None:
            status = "ready"
        self.status = status or ("disabled" if not self.enabled else "unavailable")
        self.reason = None if self.status == "ready" else reason

    def is_loaded(self) -> bool:
        return self.backend is not None

    def is_enabled(self) -> bool:
        return self.enabled

    @property
    def backend_name(self) -> str:
        if self.backend is None:
            return "disabled"
        return getattr(self.backend, "backend_name", "detector_backend")

    def runtime_status(self) -> DetectorRuntimeStatus:
        return DetectorRuntimeStatus(
            enabled=self.enabled,
            loaded=self.is_loaded(),
            status=self.status,
            reason=self.reason,
            checkpoint=self.checkpoint_path,
            checkpoint_exists=self.checkpoint_exists,
            backend_name=self.backend_name,
            threshold=self.confidence_threshold,
        )

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "DetectorService":
        environment = os.environ if environ is None else environ
        explicit_checkpoint = environment.get(DETECTOR_CHECKPOINT_ENV_VAR)
        threshold_value = environment.get(DETECTOR_THRESHOLD_ENV_VAR)
        threshold_env_var = DETECTOR_THRESHOLD_ENV_VAR
        if threshold_value is None:
            threshold_value = environment.get(LEGACY_DETECTOR_THRESHOLD_ENV_VAR)
            threshold_env_var = LEGACY_DETECTOR_THRESHOLD_ENV_VAR

        confidence_threshold = cls._resolve_confidence_threshold(
            threshold_value,
            env_var_name=threshold_env_var,
        )
        enabled_mode = cls._resolve_enabled_mode(environment.get(DETECTOR_ENABLED_ENV_VAR))
        configured_checkpoint = cls._configured_checkpoint_path(explicit_checkpoint)
        normalized_checkpoint_path, resolved_checkpoint_path = cls._resolve_checkpoint_path(configured_checkpoint)
        checkpoint_exists = bool(resolved_checkpoint_path and resolved_checkpoint_path.exists())

        logger.info(
            "Detector environment initialization enabled_mode=%s checkpoint=%s checkpoint_exists=%s threshold=%.2f",
            enabled_mode,
            normalized_checkpoint_path,
            checkpoint_exists,
            confidence_threshold,
        )

        if enabled_mode == "false":
            logger.warning(
                "%s is disabled via %s; detector-backed suggestions will be skipped.",
                DETECTOR_ENABLED_ENV_VAR,
                environment.get(DETECTOR_ENABLED_ENV_VAR),
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=False,
                status="disabled",
                reason=f"{DETECTOR_ENABLED_ENV_VAR}=false disabled detector startup.",
                checkpoint_exists=checkpoint_exists,
            )

        return cls.from_checkpoint_path(
            normalized_checkpoint_path,
            confidence_threshold=confidence_threshold,
            enabled=True,
        )

    @classmethod
    def from_checkpoint_path(
        cls,
        checkpoint_path: str | None,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        enabled: bool = True,
    ) -> "DetectorService":
        normalized_checkpoint_path, resolved_checkpoint_path = cls._resolve_checkpoint_path(checkpoint_path)
        checkpoint_exists = bool(resolved_checkpoint_path and resolved_checkpoint_path.exists())
        if not normalized_checkpoint_path or resolved_checkpoint_path is None:
            logger.warning(
                "No detector checkpoint path could be resolved; detector-backed suggestions will be skipped.",
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=enabled,
                status="missing_checkpoint",
                reason="No detector checkpoint path is configured.",
                checkpoint_exists=False,
            )

        try:
            backend = cls._load_backend_from_checkpoint(
                normalized_checkpoint_path,
                confidence_threshold=confidence_threshold,
            )
        except FileNotFoundError as error:
            logger.warning(
                "Detector checkpoint was not found or is incomplete at '%s' (%s); detector runtime is disabled and analyze requests will fall back to rules and spell checks only. Native checkpoints require %s.",
                normalized_checkpoint_path,
                error,
                ", ".join(RUNTIME_CHECKPOINT_REQUIRED_FILES),
            )
            return cls(
                confidence_threshold=confidence_threshold,
                checkpoint_path=normalized_checkpoint_path,
                enabled=enabled,
                status="missing_checkpoint",
                reason=f"Detector checkpoint could not be loaded from '{normalized_checkpoint_path}': {error}",
                checkpoint_exists=checkpoint_exists,
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
                enabled=enabled,
                status="load_failed",
                reason=f"Detector checkpoint failed to load from '{normalized_checkpoint_path}': {error}",
                checkpoint_exists=checkpoint_exists,
            )

        return cls(
            backend=backend,
            confidence_threshold=confidence_threshold,
            checkpoint_path=normalized_checkpoint_path,
            enabled=enabled,
            status="ready",
            checkpoint_exists=checkpoint_exists,
        )

    def detect_token_spans(self, text: str) -> list[DetectorTokenPrediction]:
        if not self.is_loaded():
            return []

        try:
            return list(self.backend.predict_token_spans(text))
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            logger.warning("Detector backend '%s' failed during token prediction (%s). Falling back to no detector output.", self.backend_name, error)
            return []

    def detect(
        self,
        *,
        text: str,
        normalized: NormalizedText,
        rule_suggestions: list[Suggestion],
        spell_suggestions: list[Suggestion] | None = None,
    ) -> list[DetectorFinding]:
        del normalized
        if not self.is_loaded():
            return []

        try:
            predictions = list(self.backend.predict(text))
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            logger.warning("Detector backend '%s' failed during span prediction (%s). Falling back to no detector output.", self.backend_name, error)
            return []

        spell_candidates = spell_suggestions or []
        findings: list[DetectorFinding] = []
        for prediction in predictions:
            if prediction.confidence < self.confidence_threshold:
                continue
            if any(self._overlaps_suggestion(prediction.start, prediction.end, suggestion) for suggestion in rule_suggestions):
                continue
            if any(self._overlaps_actionable_spell(prediction.start, prediction.end, suggestion) for suggestion in spell_candidates):
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
                    original_text=text[prediction.start : prediction.end],
                    replacement_options=(),
                    confidence=round(prediction.confidence, 2),
                    explanation_bn=f"Detector highlighted a likely {prediction.label} issue in this span.",
                    explanation_en=f"The detector estimated a {prediction.label} issue in this span.",
                    severity=SuggestionSeverity.LOW,
                    source=SuggestionSource.MODEL,
                )
            )
        return findings

    @classmethod
    def _load_backend_from_checkpoint(
        cls,
        checkpoint_path: str,
        *,
        confidence_threshold: float,
    ) -> TokenSpanDetectorBackend:
        _, checkpoint_dir = cls._resolve_checkpoint_path(checkpoint_path)
        if checkpoint_dir is None:
            raise FileNotFoundError(checkpoint_path)
        if not checkpoint_dir.exists():
            raise FileNotFoundError(checkpoint_dir)

        if (checkpoint_dir / "metadata.json").exists():
            missing_runtime_files = cls._missing_runtime_checkpoint_files(checkpoint_dir)
            if missing_runtime_files:
                raise FileNotFoundError(
                    f"missing required detector checkpoint files: {', '.join(missing_runtime_files)}"
                )

            runtime = BanglaDetectorRuntime.load(str(checkpoint_dir))
            return RuntimeSpanDetectorAdapter(
                runtime,
                checkpoint_path=str(checkpoint_dir),
                confidence_threshold=confidence_threshold,
            )

        if cls._looks_like_transformers_checkpoint(checkpoint_dir):
            return BanglaBertTokenClassifierScaffold.load(
                checkpoint_dir,
                confidence_threshold=confidence_threshold,
            )

        raise FileNotFoundError(
            f"missing required detector checkpoint files: {', '.join(cls._missing_runtime_checkpoint_files(checkpoint_dir))}"
        )

    @staticmethod
    def _looks_like_transformers_checkpoint(checkpoint_dir: Path) -> bool:
        return any((checkpoint_dir / marker).exists() for marker in SCAFFOLD_CHECKPOINT_MARKER_FILES)

    @staticmethod
    def _missing_runtime_checkpoint_files(checkpoint_dir: Path) -> list[str]:
        return [
            filename
            for filename in RUNTIME_CHECKPOINT_REQUIRED_FILES
            if not (checkpoint_dir / filename).exists()
        ]

    def _coerce_backend(
        self,
        runtime: Any | None,
        *,
        confidence_threshold: float,
        checkpoint_path: str | None,
    ) -> TokenSpanDetectorBackend | None:
        if runtime is None:
            return None
        if isinstance(runtime, TokenSpanDetectorBackend):
            return runtime
        return RuntimeSpanDetectorAdapter(
            runtime,
            checkpoint_path=checkpoint_path,
            confidence_threshold=confidence_threshold,
        )

    def _overlaps_suggestion(self, start: int, end: int, suggestion: Suggestion) -> bool:
        return start < suggestion.span_end and suggestion.span_start < end

    def _overlaps_actionable_spell(self, start: int, end: int, suggestion: Suggestion) -> bool:
        if suggestion.source != SuggestionSource.SPELL:
            return False
        if not suggestion.replacement_options:
            return False
        if suggestion.confidence < max(self.confidence_threshold, 0.86):
            return False
        return self._overlaps_suggestion(start, end, suggestion)

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

    @staticmethod
    def _configured_checkpoint_path(explicit_checkpoint: str | None) -> str:
        if explicit_checkpoint and explicit_checkpoint.strip():
            return explicit_checkpoint.strip()
        return DEFAULT_CHECKPOINT_DISPLAY_PATH

    @staticmethod
    def _resolve_checkpoint_path(checkpoint_path: str | None) -> tuple[str | None, Path | None]:
        if checkpoint_path is None or not checkpoint_path.strip():
            return None, None

        normalized_checkpoint_path = checkpoint_path.strip()
        resolved_checkpoint_path = Path(normalized_checkpoint_path)
        if not resolved_checkpoint_path.is_absolute():
            resolved_checkpoint_path = REPO_ROOT / resolved_checkpoint_path
        return normalized_checkpoint_path, resolved_checkpoint_path

    @staticmethod
    def _resolve_enabled_mode(value: str | None) -> str:
        if value is None or not value.strip():
            return DETECTOR_ENABLED_AUTO_VALUE

        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return "true"
        if normalized in {"0", "false", "no", "off"}:
            return "false"
        if normalized == DETECTOR_ENABLED_AUTO_VALUE:
            return DETECTOR_ENABLED_AUTO_VALUE

        logger.warning(
            "Invalid %s value '%s'; expected auto/true/false. Falling back to auto.",
            DETECTOR_ENABLED_ENV_VAR,
            value,
        )
        return DETECTOR_ENABLED_AUTO_VALUE


def _best_supporting_span_prediction(
    start: int,
    end: int,
    predictions: Sequence[DetectorPrediction],
) -> DetectorPrediction | None:
    best_prediction: DetectorPrediction | None = None
    best_overlap = -1
    for prediction in predictions:
        overlap = min(end, prediction.end) - max(start, prediction.start)
        if overlap <= 0:
            continue
        if overlap > best_overlap or (overlap == best_overlap and prediction.confidence > (best_prediction.confidence if best_prediction else 0.0)):
            best_prediction = prediction
            best_overlap = overlap
    return best_prediction


def _collapse_token_predictions(
    text: str,
    token_predictions: Sequence[DetectorTokenPrediction],
    *,
    confidence_threshold: float,
) -> list[DetectorPrediction]:
    grouped_predictions: list[DetectorPrediction] = []
    active_label: str | None = None
    active_start = 0
    active_end = 0
    active_confidences: list[float] = []

    for token_prediction in token_predictions:
        label = normalize_detector_label(token_prediction.label)
        if label == "ok" or token_prediction.confidence < confidence_threshold:
            if active_label is not None:
                grouped_predictions.append(
                    _build_prediction(
                        text,
                        label=active_label,
                        start=active_start,
                        end=active_end,
                        confidences=active_confidences,
                    )
                )
                active_label = None
                active_confidences = []
            continue

        if active_label == label and token_prediction.start <= active_end + 1:
            active_end = token_prediction.end
            active_confidences.append(token_prediction.confidence)
            continue

        if active_label is not None:
            grouped_predictions.append(
                _build_prediction(
                    text,
                    label=active_label,
                    start=active_start,
                    end=active_end,
                    confidences=active_confidences,
                )
            )

        active_label = label
        active_start = token_prediction.start
        active_end = token_prediction.end
        active_confidences = [token_prediction.confidence]

    if active_label is not None:
        grouped_predictions.append(
            _build_prediction(
                text,
                label=active_label,
                start=active_start,
                end=active_end,
                confidences=active_confidences,
            )
        )

    return grouped_predictions


def _build_prediction(
    text: str,
    *,
    label: str,
    start: int,
    end: int,
    confidences: Sequence[float],
) -> DetectorPrediction:
    mean_confidence = sum(confidences) / max(len(confidences), 1)
    return DetectorPrediction(
        label=label,
        start=start,
        end=end,
        text=text[start:end],
        confidence=round(mean_confidence, 4),
    )


def _extract_offset_mapping(raw_offsets: Any) -> list[tuple[int, int]]:
    offsets = _to_python(raw_offsets)
    if offsets and isinstance(offsets[0], list) and offsets[0] and isinstance(offsets[0][0], (list, tuple)):
        offsets = offsets[0]

    normalized_offsets: list[tuple[int, int]] = []
    for offset in offsets:
        if not isinstance(offset, (list, tuple)) or len(offset) != 2:
            continue
        start, end = offset
        normalized_offsets.append((int(start), int(end)))
    return normalized_offsets


def _ensure_batched(value: Any) -> Any:
    python_value = _to_python(value)
    if isinstance(python_value, list) and python_value and not isinstance(python_value[0], list):
        return [python_value]
    return python_value


def _call_model(model: Any, model_inputs: Mapping[str, Any]) -> Any:
    try:
        return model(**model_inputs)
    except (AttributeError, TypeError, ValueError, RuntimeError):
        torch_module = sys.modules.get("torch")
        if torch_module is None:
            raise

        tensor_inputs = {
            key: torch_module.tensor(value, dtype=torch_module.long)
            for key, value in model_inputs.items()
        }
        return model(**tensor_inputs)


def _to_python(value: Any) -> Any:
    current = value
    for attribute in ("detach", "cpu"):
        method = getattr(current, attribute, None)
        if callable(method):
            current = method()
    tolist = getattr(current, "tolist", None)
    if callable(tolist):
        return tolist()
    return current


def _softmax(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    max_value = max(values)
    exps = [math.exp(value - max_value) for value in values]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def _argmax(values: Sequence[float]) -> int:
    best_index = 0
    best_value = float("-inf")
    for index, value in enumerate(values):
        if value > best_value:
            best_index = index
            best_value = value
    return best_index
