from ml.detector.runtime import DetectorPrediction
from services.analysis.shuddho_analysis.detector import DetectorService
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource


class FakeRuntime:
    def __init__(self, predictions: list[DetectorPrediction]) -> None:
        self.predictions = predictions

    def predict(self, text: str) -> list[DetectorPrediction]:
        return list(self.predictions)


def test_detector_service_maps_runtime_predictions_into_findings() -> None:
    text = "আমি কিন্ত স্কুলে যাই।"
    service = DetectorService(
        runtime=FakeRuntime(
            [
                DetectorPrediction(label="spelling", start=4, end=9, text="কিন্ত", confidence=0.91),
            ]
        ),
        confidence_threshold=0.8,
    )

    findings = service.detect(text=text, normalized=BanglaNormalizer().normalize(text), rule_suggestions=[])

    assert len(findings) == 1
    assert findings[0].rule_id == "DET_SPELLING"
    assert findings[0].span_start == 4
    assert findings[0].original_text == "কিন্ত"
    assert findings[0].source == SuggestionSource.MODEL


def test_detector_service_skips_predictions_overlapping_existing_rules() -> None:
    text = "আমি কিন্ত স্কুলে যাই।।"
    service = DetectorService(
        runtime=FakeRuntime(
            [
                DetectorPrediction(label="punctuation", start=14, end=16, text="।।", confidence=0.92),
                DetectorPrediction(label="spelling", start=4, end=9, text="কিন্ত", confidence=0.91),
            ]
        ),
        confidence_threshold=0.8,
    )
    rule_suggestions = [
        Suggestion(
            id="rule_1",
            rule_id="PUNC_001",
            category=SuggestionCategory.PUNCTUATION,
            subtype="duplicate_punctuation",
            span_start=14,
            span_end=16,
            original_text="।।",
            replacement_options=["।"],
            confidence=0.99,
            explanation_bn="",
            explanation_en="",
            source=SuggestionSource.RULE,
            severity=SuggestionSeverity.LOW,
        )
    ]

    findings = service.detect(text=text, normalized=BanglaNormalizer().normalize(text), rule_suggestions=rule_suggestions)

    assert len(findings) == 1
    assert findings[0].rule_id == "DET_SPELLING"
