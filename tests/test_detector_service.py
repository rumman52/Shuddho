import logging
from pathlib import Path

import pytest

from ml.detector.runtime import DetectorPrediction
from services.analysis.shuddho_analysis.detector import (
    DEFAULT_CHECKPOINT_DISPLAY_PATH,
    DEFAULT_CONFIDENCE_THRESHOLD,
    BanglaBertTokenClassifierScaffold,
    DetectorService,
    DetectorTokenPrediction,
)
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource


class FakeRuntime:
    def __init__(self, predictions: list[DetectorPrediction]) -> None:
        self.predictions = predictions

    def predict(self, text: str) -> list[DetectorPrediction]:
        return list(self.predictions)


class FakeTokenBackend:
    backend_name = "fake_token_backend"

    def __init__(
        self,
        *,
        token_predictions: list[DetectorTokenPrediction],
        span_predictions: list[DetectorPrediction] | None = None,
        confidence_threshold: float = 0.8,
    ) -> None:
        self.token_predictions = token_predictions
        self.span_predictions = span_predictions or []
        self.confidence_threshold = confidence_threshold
        self.checkpoint_path = "fake-checkpoint"

    def predict(self, text: str) -> list[DetectorPrediction]:
        return list(self.span_predictions)

    def predict_token_spans(self, text: str) -> list[DetectorTokenPrediction]:
        return list(self.token_predictions)


class FailingBackend(FakeTokenBackend):
    def predict(self, text: str) -> list[DetectorPrediction]:
        raise RuntimeError("backend failure")

    def predict_token_spans(self, text: str) -> list[DetectorTokenPrediction]:
        raise RuntimeError("backend failure")


class FakeTokenizer:
    def __call__(self, text: str, *, truncation: bool, max_length: int, return_offsets_mapping: bool) -> dict[str, list]:
        assert truncation is True
        assert return_offsets_mapping is True
        assert max_length >= 2
        return {
            "input_ids": [11, 12],
            "attention_mask": [1, 1],
            "offset_mapping": [(0, 5), (6, 12)],
        }


class FakeModel:
    def __call__(self, **kwargs) -> dict[str, list[list[list[float]]]]:
        return {
            "logits": [
                [
                    [0.0, 5.0, 0.0],
                    [5.0, 0.0, 0.0],
                ]
            ]
        }


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


def test_detector_service_exposes_token_predictions_from_backend() -> None:
    backend = FakeTokenBackend(
        token_predictions=[
            DetectorTokenPrediction(token="কিন্ত", start=0, end=5, label="spelling", confidence=0.88),
            DetectorTokenPrediction(token="স্কুলে", start=6, end=12, label="ok", confidence=0.99),
        ],
        span_predictions=[
            DetectorPrediction(label="spelling", start=0, end=5, text="কিন্ত", confidence=0.88),
        ],
    )
    service = DetectorService(backend=backend)

    token_predictions = service.detect_token_spans("কিন্ত স্কুলে")

    assert [prediction.label for prediction in token_predictions] == ["spelling", "ok"]


def test_banglabert_scaffold_collapses_token_predictions_into_spans() -> None:
    scaffold = BanglaBertTokenClassifierScaffold(
        model=FakeModel(),
        tokenizer=FakeTokenizer(),
        id_to_label={0: "ok", 1: "spelling", 2: "grammar"},
        confidence_threshold=0.6,
        checkpoint_path="fake-bert",
    )

    token_predictions = scaffold.predict_token_spans("কিন্ত স্কুলে")
    span_predictions = scaffold.predict("কিন্ত স্কুলে")

    assert [prediction.label for prediction in token_predictions] == ["spelling", "ok"]
    assert len(span_predictions) == 1
    assert span_predictions[0].label == "spelling"
    assert span_predictions[0].start == 0
    assert span_predictions[0].end == 5


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


def test_detector_service_skips_predictions_overlapping_actionable_spell_suggestions() -> None:
    text = "আমি কিন্ত স্কুলে যাই।"
    service = DetectorService(
        runtime=FakeRuntime(
            [
                DetectorPrediction(label="spelling", start=4, end=9, text="কিন্ত", confidence=0.91),
            ]
        ),
        confidence_threshold=0.8,
    )
    spell_suggestions = [
        Suggestion(
            id="spell_1",
            rule_id="SPELL_002",
            category=SuggestionCategory.SPELLING,
            subtype="orthography_variant",
            span_start=4,
            span_end=9,
            original_text="কিন্ত",
            replacement_options=["কিন্তু"],
            confidence=0.95,
            explanation_bn="",
            explanation_en="",
            source=SuggestionSource.SPELL,
            severity=SuggestionSeverity.LOW,
        )
    ]

    findings = service.detect(
        text=text,
        normalized=BanglaNormalizer().normalize(text),
        rule_suggestions=[],
        spell_suggestions=spell_suggestions,
    )

    assert findings == []


def test_detector_service_returns_empty_predictions_when_backend_fails() -> None:
    service = DetectorService(backend=FailingBackend(token_predictions=[]))

    assert service.detect_token_spans("কিন্ত") == []
    assert service.detect(
        text="কিন্ত",
        normalized=BanglaNormalizer().normalize("কিন্ত"),
        rule_suggestions=[],
    ) == []


def test_detector_service_auto_loads_default_checkpoint_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RuntimeWithThreshold:
        def __init__(self) -> None:
            self.confidence_threshold = 0.1

        def predict(self, text: str) -> list[DetectorPrediction]:
            return []

    runtime = RuntimeWithThreshold()
    default_checkpoint_dir = tmp_path / "artifacts" / "detector" / "detector-base"
    default_checkpoint_dir.mkdir(parents=True)
    (default_checkpoint_dir / "metadata.json").write_text("{}", encoding="utf-8")
    (default_checkpoint_dir / "best_model.pt").write_text("stub", encoding="utf-8")

    def fake_load(checkpoint_path: str) -> RuntimeWithThreshold:
        assert Path(checkpoint_path) == default_checkpoint_dir
        return runtime

    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.REPO_ROOT", tmp_path)
    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.BanglaDetectorRuntime.load", fake_load)

    service = DetectorService.from_environment({})
    runtime_status = service.runtime_status()

    assert service.is_loaded() is True
    assert service.checkpoint_path == DEFAULT_CHECKPOINT_DISPLAY_PATH
    assert runtime_status.enabled is True
    assert runtime_status.loaded is True
    assert runtime_status.status == "ready"
    assert runtime_status.checkpoint_exists is True
    assert service.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert runtime.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_detector_service_can_be_disabled_explicitly_from_environment(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_environment(
            {
                "SHUDDHO_DETECTOR_ENABLED": "false",
                "SHUDDHO_DETECTOR_CHECKPOINT": "artifacts/detector/detector-base",
            }
        )

    assert service.is_loaded() is False
    assert service.checkpoint_path == "artifacts/detector/detector-base"
    assert service.runtime_status().enabled is False
    assert service.runtime_status().status == "disabled"
    assert "SHUDDHO_DETECTOR_ENABLED is disabled" in caplog.text


def test_detector_service_logs_warning_when_checkpoint_path_is_missing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_checkpoint_path("missing-checkpoint")

    assert service.is_loaded() is False
    assert service.checkpoint_path == "missing-checkpoint"
    assert service.runtime_status().status == "missing_checkpoint"
    assert "Detector checkpoint was not found" in caplog.text


def test_detector_service_logs_clear_warning_when_checkpoint_directory_is_incomplete(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    checkpoint_dir = tmp_path / "detector"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "metadata.json").write_text("{}", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_checkpoint_path(str(checkpoint_dir))

    assert service.is_loaded() is False
    assert service.checkpoint_path == str(checkpoint_dir)
    assert "best_model.pt" in caplog.text
    assert "Native checkpoints require metadata.json, best_model.pt." in caplog.text


def test_detector_service_reads_threshold_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RuntimeWithThreshold:
        def __init__(self) -> None:
            self.confidence_threshold = 0.1

        def predict(self, text: str) -> list[DetectorPrediction]:
            return []

    runtime = RuntimeWithThreshold()
    checkpoint_dir = tmp_path / "detector"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "metadata.json").write_text("{}", encoding="utf-8")
    (checkpoint_dir / "best_model.pt").write_text("stub", encoding="utf-8")

    def fake_load(checkpoint_path: str) -> RuntimeWithThreshold:
        assert Path(checkpoint_path) == checkpoint_dir
        return runtime

    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.BanglaDetectorRuntime.load", fake_load)

    service = DetectorService.from_environment(
        {
            "SHUDDHO_DETECTOR_CHECKPOINT": str(checkpoint_dir),
            "SHUDDHO_DETECTOR_THRESHOLD": "0.91",
        }
    )

    assert service.is_loaded() is True
    assert service.confidence_threshold == 0.91
    assert service.checkpoint_path == str(checkpoint_dir)
    assert runtime.confidence_threshold == 0.91


def test_detector_service_invalid_threshold_falls_back_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.REPO_ROOT", tmp_path)
    with caplog.at_level(logging.WARNING):
        service = DetectorService.from_environment(
            {
                "SHUDDHO_DETECTOR_THRESHOLD": "not-a-number",
            }
        )

    assert service.is_loaded() is False
    assert service.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert service.runtime_status().status == "missing_checkpoint"
    assert "Invalid SHUDDHO_DETECTOR_THRESHOLD value" in caplog.text


def test_detector_service_supports_legacy_threshold_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RuntimeWithThreshold:
        def __init__(self) -> None:
            self.confidence_threshold = 0.1

        def predict(self, text: str) -> list[DetectorPrediction]:
            return []

    runtime = RuntimeWithThreshold()
    checkpoint_dir = tmp_path / "detector"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "metadata.json").write_text("{}", encoding="utf-8")
    (checkpoint_dir / "best_model.pt").write_text("stub", encoding="utf-8")

    def fake_load(checkpoint_path: str) -> RuntimeWithThreshold:
        assert Path(checkpoint_path) == checkpoint_dir
        return runtime

    monkeypatch.setattr("services.analysis.shuddho_analysis.detector.BanglaDetectorRuntime.load", fake_load)

    service = DetectorService.from_environment(
        {
            "SHUDDHO_DETECTOR_CHECKPOINT": str(checkpoint_dir),
            "SHUDDHO_DETECTOR_CONFIDENCE_THRESHOLD": "0.77",
        }
    )

    assert service.is_loaded() is True
    assert service.confidence_threshold == 0.77
    assert runtime.confidence_threshold == 0.77
