from pathlib import Path

from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.models import DetectorFinding
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, SuggestionCategory, SuggestionKind, SuggestionSeverity, SuggestionSource


class StubDetectorService(DetectorService):
    def detect(self, *, text, normalized, rule_suggestions, spell_suggestions=None):  # type: ignore[override]
        del normalized, rule_suggestions, spell_suggestions
        if "\u09b6\u09c1\u09a6\u09cd\u09a7" not in text:
            return []

        return [
            DetectorFinding(
                rule_id="DET_001",
                category=SuggestionCategory.STYLE,
                subtype="detector_stub",
                span_start=0,
                span_end=5,
                original_text=text[0:5],
                replacement_options=("\u09b6\u09c1\u09a6\u09cd\u09a7",),
                confidence=0.93,
                explanation_bn="Detector stub highlighted this span.",
                explanation_en="The detector stub flagged this span.",
                severity=SuggestionSeverity.LOW,
                source=SuggestionSource.MODEL,
            )
        ]


def test_analysis_pipeline_preserves_hard_errors_while_hiding_variant_only_spelling_in_standard_mode(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0995\u09bf\u09a8\u09cd\u09a4", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "0", "1"),
            ("\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964\u0964"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)
    strict_response = pipeline.analyze(text, mode=AnalyzeMode.STRICT)

    standard_rule_ids = {suggestion.rule_id for suggestion in standard_response.suggestions}
    assert "REP_001" in standard_rule_ids
    assert "PUNC_001" in standard_rule_ids
    assert "SPELL_002" not in standard_rule_ids

    spell_variant = next(suggestion for suggestion in strict_response.suggestions if suggestion.rule_id == "SPELL_002")
    assert spell_variant.replacement_options == ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]
    assert spell_variant.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT
    assert spell_variant.is_variant_only is True
    assert strict_response.normalized_text == text


def test_analysis_pipeline_merges_detector_findings_without_breaking_response_ids(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u09b6\u09c1\u09a6\u09cd\u09a7", "\u09b6\u09c1\u09a6\u09cd\u09a7", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path, detector_service=StubDetectorService())

    response = pipeline.analyze("\u09b6\u09c1\u09a6\u09cd\u09a7 \u09ac\u09be\u0982\u09b2\u09be", mode=AnalyzeMode.STRICT)

    detector_suggestion = next(suggestion for suggestion in response.suggestions if suggestion.rule_id == "DET_001")
    assert detector_suggestion.id.startswith("s_")
    assert detector_suggestion.source == SuggestionSource.MODEL
    assert detector_suggestion.original_text == "\u09b6\u09c1\u09a6\u09cd\u09a7"
    assert detector_suggestion.replacement_options == ["\u09b6\u09c1\u09a6\u09cd\u09a7"]


def test_analysis_pipeline_filters_low_confidence_code_mix_warnings_even_in_formal_mode(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u0986\u0997\u09be\u09ae\u09c0\u0995\u09be\u09b2", "\u0986\u0997\u09be\u09ae\u09c0\u0995\u09be\u09b2", "fixture.csv", "1", "1", "1"),
            ("\u09b8\u0995\u09be\u09b2\u09c7", "\u09b8\u0995\u09be\u09b2\u09c7", "fixture.csv", "1", "1", "1"),
            ("\u09a4\u09cb\u09ae\u09be\u09a6\u09c7\u09b0", "\u09a4\u09cb\u09ae\u09be\u09a6\u09c7\u09b0", "fixture.csv", "1", "1", "1"),
            ("\u09b8\u09be\u09a5\u09c7", "\u09b8\u09be\u09a5\u09c7", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09b8\u09ac", "\u0986\u09b8\u09ac", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "\u0986\u09ae\u09bf \u0986\u0997\u09be\u09ae\u09c0\u0995\u09be\u09b2 \u09b8\u0995\u09be\u09b2\u09c7 \u09a4\u09cb\u09ae\u09be\u09a6\u09c7\u09b0 \u09b8\u09be\u09a5\u09c7 tomorrow \u0986\u09b8\u09ac\u0964"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)
    strict_response = pipeline.analyze(text, mode=AnalyzeMode.STRICT)
    formal_response = pipeline.analyze(text, mode=AnalyzeMode.FORMAL)

    assert "code_mixed_latin" not in {suggestion.subtype for suggestion in standard_response.suggestions}
    assert "code_mixed_latin" not in {suggestion.subtype for suggestion in strict_response.suggestions}
    assert "code_mixed_latin" not in {suggestion.subtype for suggestion in formal_response.suggestions}


def test_analysis_pipeline_standard_mode_keeps_actionable_style_suggestions(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u099a\u09be\u09b2", "\u099a\u09be\u09b2", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)

    response = pipeline.analyze("\u09eb\u0995\u09c7\u099c\u09bf \u099a\u09be\u09b2", mode=AnalyzeMode.STANDARD)

    assert "number_unit_spacing" in {suggestion.subtype for suggestion in response.suggestions}


def test_analysis_pipeline_strict_and_formal_modes_surface_variant_only_suggestions_hidden_in_standard(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0995\u09bf\u09a8\u09cd\u09a4", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "0", "1"),
            ("\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09b8\u09ac", "\u0986\u09b8\u09ac", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "\u0995\u09bf\u09a8\u09cd\u09a4 \u0986\u09ae\u09bf \u0986\u09b8\u09ac"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)
    strict_response = pipeline.analyze(text, mode=AnalyzeMode.STRICT)
    formal_response = pipeline.analyze(text, mode=AnalyzeMode.FORMAL)

    assert "orthography_variant" not in {suggestion.subtype for suggestion in standard_response.suggestions}
    assert "orthography_variant" in {suggestion.subtype for suggestion in strict_response.suggestions}
    assert "orthography_variant" in {suggestion.subtype for suggestion in formal_response.suggestions}


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
