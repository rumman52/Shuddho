import logging

import pytest

from ml.detector.runtime import DetectorPrediction
from services.analysis.shuddho_analysis.detector import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DetectorService,
)
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
    assert service.is_loaded() is True


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


def test_detector_service_logs_warning_when_checkpoint_env_is_missing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_environment({})

    assert service.is_loaded() is False
    assert service.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert "SHUDDHO_DETECTOR_CHECKPOINT is not set" in caplog.text


def test_detector_service_logs_warning_when_checkpoint_path_is_missing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_checkpoint_path("missing-checkpoint")

    assert service.is_loaded() is False
    assert service.checkpoint_path == "missing-checkpoint"
    assert "Detector checkpoint was not found" in caplog.text


def test_detector_service_reads_threshold_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    class RuntimeWithThreshold:
        def __init__(self) -> None:
            self.confidence_threshold = 0.1

        def predict(self, text: str) -> list[DetectorPrediction]:
            return []

    runtime = RuntimeWithThreshold()

    def fake_load(checkpoint_path: str) -> RuntimeWithThreshold:
        assert checkpoint_path == "checkpoints/detector"
        return runtime

    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.BanglaDetectorRuntime.load", fake_load)

    service = DetectorService.from_environment(
        {
            "SHUDDHO_DETECTOR_CHECKPOINT": "checkpoints/detector",
            "SHUDDHO_DETECTOR_THRESHOLD": "0.91",
        }
    )

    assert service.is_loaded() is True
    assert service.confidence_threshold == 0.91
    assert service.checkpoint_path == "checkpoints/detector"
    assert runtime.confidence_threshold == 0.91


def test_detector_service_invalid_threshold_falls_back_without_crashing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_environment(
            {
                "SHUDDHO_DETECTOR_THRESHOLD": "not-a-number",
            }
        )

    assert service.is_loaded() is False
    assert service.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert "Invalid SHUDDHO_DETECTOR_THRESHOLD value" in caplog.text


def test_detector_service_supports_legacy_threshold_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RuntimeWithThreshold:
        def __init__(self) -> None:
            self.confidence_threshold = 0.1

        def predict(self, text: str) -> list[DetectorPrediction]:
            return []

    runtime = RuntimeWithThreshold()

    def fake_load(checkpoint_path: str) -> RuntimeWithThreshold:
        assert checkpoint_path == "checkpoints/detector"
        return runtime

    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.BanglaDetectorRuntime.load", fake_load)

    service = DetectorService.from_environment(
        {
            "SHUDDHO_DETECTOR_CHECKPOINT": "checkpoints/detector",
            "SHUDDHO_DETECTOR_CONFIDENCE_THRESHOLD": "0.77",
        }
    )

    assert service.is_loaded() is True
    assert service.confidence_threshold == 0.77
    assert runtime.confidence_threshold == 0.77
