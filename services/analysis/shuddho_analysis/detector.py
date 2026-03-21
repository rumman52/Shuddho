from __future__ import annotations

from ml.detector.labels import DETECTOR_LABEL_TO_CATEGORY
from ml.detector.runtime import BanglaDetectorRuntime
from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import Suggestion, SuggestionSeverity, SuggestionSource

from .models import DetectorFinding


class DetectorService:
    def __init__(
        self,
        runtime: BanglaDetectorRuntime | None = None,
        *,
        confidence_threshold: float = 0.82,
    ) -> None:
        self.runtime = runtime
        self.confidence_threshold = confidence_threshold

    @classmethod
    def from_checkpoint_path(
        cls,
        checkpoint_path: str | None,
        *,
        confidence_threshold: float = 0.82,
    ) -> "DetectorService":
        if not checkpoint_path:
            return cls(confidence_threshold=confidence_threshold)

        try:
            runtime = BanglaDetectorRuntime.load(checkpoint_path)
        except (FileNotFoundError, RuntimeError, KeyError, ValueError):
            return cls(confidence_threshold=confidence_threshold)
        return cls(runtime=runtime, confidence_threshold=confidence_threshold)

    def detect(
        self,
        *,
        text: str,
        normalized: NormalizedText,
        rule_suggestions: list[Suggestion],
    ) -> list[DetectorFinding]:
        if self.runtime is None:
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
