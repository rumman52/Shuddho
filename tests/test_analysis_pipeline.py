from pathlib import Path

from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.models import DetectorFinding
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, SuggestionCategory, SuggestionSeverity, SuggestionSource


class StubDetectorService(DetectorService):
    def detect(self, *, text, normalized, rule_suggestions, spell_suggestions=None):  # type: ignore[override]
        del normalized, rule_suggestions, spell_suggestions
        if "শুদ্ধ" not in text:
            return []

        return [
            DetectorFinding(
                rule_id="DET_001",
                category=SuggestionCategory.STYLE,
                subtype="detector_stub",
                span_start=0,
                span_end=5,
                original_text=text[0:5],
                replacement_options=("শুদ্ধ",),
                confidence=0.8,
                explanation_bn="ডিটেক্টর স্টাব এই অংশটি ধরেছে।",
                explanation_en="The detector stub flagged this span.",
                severity=SuggestionSeverity.LOW,
                source=SuggestionSource.MODEL,
            )
        ]


def test_analysis_pipeline_preserves_existing_rule_and_spell_behavior(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("কিন্ত", "কিন্তু", "fixture.csv", "1", "0", "1"),
            ("কিন্তু", "কিন্তু", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)

    response = pipeline.analyze("আমি আমি কিন্ত স্কুলে যাই।।")
    by_rule_id = {suggestion.rule_id: suggestion for suggestion in response.suggestions}

    assert by_rule_id["REP_001"].original_text == "আমি আমি"
    assert by_rule_id["SPELL_002"].replacement_options == ["কিন্তু"]
    assert by_rule_id["PUNC_001"].original_text == "।।"
    assert response.normalized_text == "আমি আমি কিন্ত স্কুলে যাই।।"


def test_analysis_pipeline_merges_detector_findings_without_breaking_response_ids(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("শুদ্ধ", "শুদ্ধ", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path, detector_service=StubDetectorService())

    response = pipeline.analyze("শুদ্ধ বাংলা")

    detector_suggestion = next(suggestion for suggestion in response.suggestions if suggestion.rule_id == "DET_001")
    assert detector_suggestion.id.startswith("s_")
    assert detector_suggestion.source == SuggestionSource.MODEL
    assert detector_suggestion.original_text == "শুদ্ধ"
    assert detector_suggestion.replacement_options == ["শুদ্ধ"]


def test_analysis_pipeline_standard_mode_filters_weak_style_only_warnings(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("আমি", "আমি", "fixture.csv", "1", "1", "1"),
            ("আগামীকাল", "আগামীকাল", "fixture.csv", "1", "1", "1"),
            ("সকালে", "সকালে", "fixture.csv", "1", "1", "1"),
            ("তোমাদের", "তোমাদের", "fixture.csv", "1", "1", "1"),
            ("সাথে", "সাথে", "fixture.csv", "1", "1", "1"),
            ("আসব", "আসব", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "আমি আগামীকাল সকালে তোমাদের সাথে tomorrow আসব।"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)
    strict_response = pipeline.analyze(text, mode=AnalyzeMode.STRICT)
    formal_response = pipeline.analyze(text, mode=AnalyzeMode.FORMAL)

    assert "code_mixed_latin" not in {suggestion.subtype for suggestion in standard_response.suggestions}
    assert "code_mixed_latin" in {suggestion.subtype for suggestion in strict_response.suggestions}
    assert "code_mixed_latin" in {suggestion.subtype for suggestion in formal_response.suggestions}


def test_analysis_pipeline_standard_mode_keeps_actionable_style_suggestions(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("চাল", "চাল", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)

    response = pipeline.analyze("৫কেজি চাল", mode=AnalyzeMode.STANDARD)

    assert "number_unit_spacing" in {suggestion.subtype for suggestion in response.suggestions}


def _build_pipeline(runtime_csv_path: Path, detector_service: DetectorService | None = None) -> AnalysisPipeline:
    return AnalysisPipeline(
        normalizer=BanglaNormalizer(),
        spell_engine=SpellEngine(runtime_csv_path=runtime_csv_path),
        rule_engine=RuleEngine(),
        suggestion_manager=SuggestionManager(),
        detector_service=detector_service,
    )


def _write_clean_csv_fixture(
    base_dir: Path,
    *,
    rows: list[tuple[str, str, str, str, str, str]],
) -> Path:
    runtime_csv_path = base_dir / "words_clean.csv"
    lines = ["word,normalized_word,source,is_trusted,is_common,is_active"]
    lines.extend(",".join(row) for row in rows)
    runtime_csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_csv_path
