from pathlib import Path

from services.analysis.shuddho_analysis.corrector_service import CorrectorService
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource


def test_corrector_service_missing_checkpoint_falls_back_without_crashing(tmp_path: Path) -> None:
    missing_checkpoint = tmp_path / "missing-corrector"
    service = CorrectorService.from_environment({"SHUDDHO_CORRECTOR_CHECKPOINT": str(missing_checkpoint)})
    status = service.runtime_status()

    assert service.is_loaded() is False
    assert service.is_enabled() is True
    assert status.status == "missing_checkpoint"
    assert status.checkpoint == str(missing_checkpoint)
    assert service.suggest("আমি বাংলা লিখি।", mode=AnalyzeMode.STANDARD) == []


def test_corrector_service_can_be_disabled_explicitly() -> None:
    service = CorrectorService.from_environment({"SHUDDHO_CORRECTOR_ENABLED": "false"})
    status = service.runtime_status()

    assert service.is_loaded() is False
    assert service.is_enabled() is False
    assert status.status == "disabled"
    assert status.reason == "SHUDDHO_CORRECTOR_ENABLED=false disabled corrector startup."


def test_analysis_pipeline_accepts_local_corrector_suggestions(tmp_path: Path) -> None:
    pipeline = AnalysisPipeline(
        normalizer=BanglaNormalizer(),
        spell_engine=SpellEngine(runtime_csv_path=_write_clean_csv_fixture(tmp_path)),
        rule_engine=RuleEngine(),
        suggestion_manager=SuggestionManager(),
        detector_service=StubReadyDetectorService(),
        corrector_service=StubReadyCorrectorService(),
    )

    response = pipeline.analyze("আমি বাংলা লিখি", mode=AnalyzeMode.STRICT)
    rule_ids = [suggestion.rule_id for suggestion in response.suggestions]

    assert response.analysis_profile == "full_local"
    assert response.used_detector is True
    assert response.used_corrector is True
    assert "COR_001" in rule_ids


class StubReadyDetectorService:
    checkpoint_path = "artifacts/detector/detector-base"

    def is_loaded(self) -> bool:
        return True

    def detect(self, *, text, normalized, rule_suggestions, spell_suggestions=None):  # type: ignore[override]
        del text, normalized, rule_suggestions, spell_suggestions
        return []

    def runtime_status(self):
        return type(
            "DetectorStatus",
            (),
            {
                "enabled": True,
                "loaded": True,
                "status": "ready",
                "reason": None,
                "checkpoint": self.checkpoint_path,
                "checkpoint_exists": True,
                "backend_name": "stub_detector",
                "threshold": 0.92,
            },
        )()


class StubReadyCorrectorService:
    checkpoint_path = "artifacts/corrector/corrector-base"

    def is_loaded(self) -> bool:
        return True

    def suggest(self, text: str, *, mode: AnalyzeMode, personal_dictionary=None):  # type: ignore[override]
        del mode, personal_dictionary
        return [
            Suggestion(
                id="cor_001",
                rule_id="COR_001",
                category=SuggestionCategory.PUNCTUATION,
                subtype="corrector_inline_punctuation",
                span_start=len(text) - 4,
                span_end=len(text),
                original_text=text[-4:],
                replacement_options=[f"{text[-4:]}।"],
                confidence=0.95,
                explanation_bn="স্থানীয় corrector বাক্যের শেষে যতিচিহ্ন যোগ করার পরামর্শ দিচ্ছে।",
                explanation_en="The local corrector recommends adding punctuation at the end of the sentence.",
                source=SuggestionSource.MODEL,
                severity=SuggestionSeverity.MEDIUM,
                source_trace=["exact_unique_match"],
            )
        ]

    def runtime_status(self):
        return type(
            "CorrectorStatus",
            (),
            {
                "enabled": True,
                "loaded": True,
                "status": "ready",
                "reason": None,
                "checkpoint": self.checkpoint_path,
                "checkpoint_exists": True,
                "backend_name": "stub_corrector",
                "threshold": 0.86,
            },
        )()


def _write_clean_csv_fixture(base_dir: Path) -> Path:
    runtime_csv_path = base_dir / "words_clean.csv"
    runtime_csv_path.write_text(
        "\n".join(
            [
                "word,normalized_word,source,is_trusted,is_common,is_active",
                "আমি,আমি,fixture.csv,1,1,1",
                "স্কুলে,স্কুলে,fixture.csv,1,1,1",
                "যাই,যাই,fixture.csv,1,1,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return runtime_csv_path
