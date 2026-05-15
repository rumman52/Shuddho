from pathlib import Path

from services.analysis.shuddho_analysis.corrector_service import CorrectorService
from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.models import DetectorFinding
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionKind, SuggestionSeverity, SuggestionSource


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


def test_analysis_pipeline_preserves_hard_errors_and_keeps_curated_hard_spelling_in_standard_mode(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "1", "1"),
            ("\u09b8\u09cd\u0995\u09c1\u09b2\u09c7", "\u09b8\u09cd\u0995\u09c1\u09b2\u09c7", "fixture.csv", "1", "1", "1"),
            ("\u09af\u09be\u0987", "\u09af\u09be\u0987", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964\u0964"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)

    standard_rule_ids = {suggestion.rule_id for suggestion in standard_response.suggestions}
    assert "REP_001" in standard_rule_ids
    assert "PUNC_001" in standard_rule_ids
    assert "SPELL_001" in standard_rule_ids or "SPELL_002" in standard_rule_ids or "SPELL_003" in standard_rule_ids
    assert standard_response.normalized_text == text
    assert standard_response.corrected_text == "\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4\u09c1 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"


def test_analysis_pipeline_drops_detector_findings_that_do_not_change_the_text(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u09b6\u09c1\u09a6\u09cd\u09a7", "\u09b6\u09c1\u09a6\u09cd\u09a7", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path, detector_service=StubDetectorService())

    response = pipeline.analyze("\u09b6\u09c1\u09a6\u09cd\u09a7 \u09ac\u09be\u0982\u09b2\u09be", mode=AnalyzeMode.STRICT)

    assert all(suggestion.rule_id != "DET_001" for suggestion in response.suggestions)
    assert response.corrected_text == "\u09b6\u09c1\u09a6\u09cd\u09a7 \u09ac\u09be\u0982\u09b2\u09be"


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


def test_analysis_pipeline_standard_mode_keeps_safe_exact_phrase_corrections(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u098f\u09b0\u09aa\u09b0", "\u098f\u09b0\u09aa\u09b0", "fixture.csv", "1", "1", "1"),
            ("\u09af\u09a6\u09bf\u0993", "\u09af\u09a6\u09bf\u0993", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09b8\u09cb", "\u0986\u09b8\u09cb", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)

    response = pipeline.analyze("\u098f\u09b0 \u09aa\u09b0 \u09af\u09a6\u09bf \u0993 \u0986\u09b8\u09cb\u0964", mode=AnalyzeMode.STANDARD)
    replacements = {replacement for suggestion in response.suggestions for replacement in suggestion.replacement_options}

    assert "\u098f\u09b0\u09aa\u09b0" in replacements
    assert "\u09af\u09a6\u09bf\u0993" in replacements


def test_analysis_pipeline_strict_and_formal_modes_surface_variant_only_suggestions_hidden_in_standard(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u09a8\u09bf\u09df\u09c7", "\u09a8\u09bf\u09df\u09c7", "fixture.csv", "1", "1", "1"),
            ("\u09a8\u09bf\u09af\u09bc\u09c7", "\u09a8\u09bf\u09af\u09bc\u09c7", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09b8\u09ac", "\u0986\u09b8\u09ac", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "\u09a8\u09bf\u09df\u09c7 \u0986\u09ae\u09bf \u0986\u09b8\u09ac"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)
    strict_response = pipeline.analyze(text, mode=AnalyzeMode.STRICT)
    formal_response = pipeline.analyze(text, mode=AnalyzeMode.FORMAL)

    assert "orthography_variant" not in {suggestion.subtype for suggestion in standard_response.suggestions}
    assert "orthography_variant" in {suggestion.subtype for suggestion in strict_response.suggestions}
    assert "orthography_variant" in {suggestion.subtype for suggestion in formal_response.suggestions}


def test_analysis_pipeline_hides_runtime_variant_normalization_in_standard_mode(tmp_path: Path) -> None:
    runtime_csv_path = _write_runtime_words_fixture(
        tmp_path,
        rows=[
            ("যায়", "যায়", "fixture.csv", "1", "0", "1", "accepted_variants", "1", "1", "normalized_surface_variant"),
            ("যায়", "যায়", "fixture.csv", "1", "1", "1", "core_formal_words", "1", "1", "common_runtime_word"),
            ("সে", "সে", "fixture.csv", "1", "1", "1", "core_formal_words", "1", "1", "common_runtime_word"),
            ("স্কুলে", "স্কুলে", "fixture.csv", "1", "1", "1", "core_formal_words", "1", "1", "common_runtime_word"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)
    text = "সে স্কুলে যায়।"

    standard_response = pipeline.analyze(text, mode=AnalyzeMode.STANDARD)
    strict_response = pipeline.analyze(text, mode=AnalyzeMode.STRICT)

    assert "orthography_variant" not in {suggestion.subtype for suggestion in standard_response.suggestions}
    strict_variant = next(suggestion for suggestion in strict_response.suggestions if suggestion.subtype == "orthography_variant")
    assert strict_variant.original_text == "যায়"
    assert strict_variant.replacement_options == ["যায়"]
    assert standard_response.corrected_text == text
    assert strict_response.corrected_text == text


def test_analysis_pipeline_returns_runtime_metadata_and_safe_corrected_text(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "1", "1"),
            ("\u09ac\u09be\u0982\u09b2\u09be", "\u09ac\u09be\u0982\u09b2\u09be", "fixture.csv", "1", "1", "1"),
        ],
    )
    pipeline = _build_pipeline(runtime_csv_path)

    response = pipeline.analyze("\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09ac\u09be\u0982\u09b2\u09be\u0964", mode=AnalyzeMode.STANDARD)

    assert response.analysis_profile == "backend_rules_and_spell_only"
    assert response.runtime_source == "backend_rules_and_spell_only"
    assert response.used_detector is False
    assert response.used_corrector is False
    assert response.lexicon_source == "words_clean.csv"
    assert response.lexicon_version
    assert response.sentence_count == 1
    assert response.request_mode_applied == AnalyzeMode.STANDARD
    assert response.corrected_text == "\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4\u09c1 \u09ac\u09be\u0982\u09b2\u09be\u0964"


def test_analysis_pipeline_prefers_same_span_grammar_primary_over_spelling_variant(tmp_path: Path) -> None:
    pipeline = _build_pipeline(_write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()))

    response = pipeline.analyze("আমি ভাত খায়।", mode=AnalyzeMode.STANDARD)

    verb_suggestion = next(suggestion for suggestion in response.suggestions if suggestion.original_text == "খায়")

    assert verb_suggestion.subtype == "first_person_verb_mismatch"
    assert verb_suggestion.replacement_options == ["খাই"]
    assert response.corrected_text == "আমি ভাত খাই।"
    assert verb_suggestion.conflict_group_id is not None
    assert verb_suggestion.primary_reason is not None
    assert any(alternative.replacement_options == ["খায়"] for alternative in verb_suggestion.alternatives)
    assert all(
        suggestion.replacement_options != ["খায়"] or suggestion.span_start != verb_suggestion.span_start
        for suggestion in response.suggestions
    )


def test_analysis_pipeline_covers_requested_agreement_regressions(tmp_path: Path) -> None:
    pipeline = _build_pipeline(_write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()))

    assert pipeline.analyze("আমি স্কুলে যায়।", mode=AnalyzeMode.STANDARD).corrected_text == "আমি স্কুলে যাই।"
    assert pipeline.analyze("তুমি ভাত খায়।", mode=AnalyzeMode.STANDARD).corrected_text == "তুমি ভাত খাও।"
    assert pipeline.analyze("তুমি স্কুলে যায়।", mode=AnalyzeMode.STANDARD).corrected_text == "তুমি স্কুলে যাও।"

    honorific_response = pipeline.analyze("আপনি স্কুলে যায়।", mode=AnalyzeMode.STANDARD)
    honorific_suggestion = next(suggestion for suggestion in honorific_response.suggestions if suggestion.original_text == "যায়")
    assert honorific_response.corrected_text == "আপনি স্কুলে যান।"
    assert honorific_suggestion.subtype == "honorific_pronoun_verb_mismatch"
    assert honorific_suggestion.replacement_options == ["যান"]

    third_person_response = pipeline.analyze("সে স্কুলে যাই।", mode=AnalyzeMode.STANDARD)
    assert third_person_response.corrected_text == "সে স্কুলে যায়।"
    assert any(suggestion.subtype == "third_person_verb_mismatch" for suggestion in third_person_response.suggestions)


def test_analysis_pipeline_fixes_mid_sentence_repeated_word_safely(tmp_path: Path) -> None:
    pipeline = _build_pipeline(_write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()))

    response = pipeline.analyze("সে বাংলা বাংলা লিখে।", mode=AnalyzeMode.STANDARD)

    repeated_word = next(suggestion for suggestion in response.suggestions if suggestion.subtype == "repeated_word")

    assert repeated_word.original_text == "বাংলা বাংলা"
    assert repeated_word.replacement_options == ["বাংলা"]
    assert response.corrected_text == "সে বাংলা লিখে।"


def test_analysis_pipeline_composes_overlapping_safe_punctuation_spacing_and_repeat_fixes(tmp_path: Path) -> None:
    pipeline = _build_pipeline(_write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()))

    response = pipeline.analyze("আমি  বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!", mode=AnalyzeMode.STANDARD)

    assert response.corrected_text == "আমি বাংলা লিখি। বাংলা ভাষা খুব সুন্দর!"
    assert "।।" not in response.corrected_text
    assert " !!" not in response.corrected_text


def test_analysis_pipeline_keeps_localized_fixes_without_generic_rewrite(tmp_path: Path) -> None:
    pipeline = _build_pipeline(_write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()))

    response = pipeline.analyze("শুদ্ধ বাংলা ব্যকরণ আর বংলা বানানভুল ঠিক করা দরকার।", mode=AnalyzeMode.STANDARD)

    assert response.corrected_text == "শুদ্ধ বাংলা ব্যাকরণ আর বাংলা বানান ভুল ঠিক করা দরকার।"
    assert all(suggestion.source != SuggestionSource.MODEL for suggestion in response.suggestions)
    assert all((suggestion.span_end - suggestion.span_start) < len(response.text) for suggestion in response.suggestions if suggestion.replacement_options)


def test_analysis_pipeline_returns_zero_corrections_for_valid_sentence(tmp_path: Path) -> None:
    pipeline = _build_pipeline(_write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()))

    response = pipeline.analyze("আমি আজ স্কুলে যাই।", mode=AnalyzeMode.STANDARD)

    assert response.corrected_text == "আমি আজ স্কুলে যাই।"
    assert response.suggestions == []


def test_analysis_pipeline_drops_model_suggestion_with_wrong_original_text_anchor(tmp_path: Path) -> None:
    class StubCorrectorService:
        def is_loaded(self) -> bool:
            return True

        def suggest(self, text: str, *, mode: AnalyzeMode, personal_dictionary=None) -> list[Suggestion]:
            del text, mode, personal_dictionary
            return [
                Suggestion(
                    id="cor_invalid",
                    rule_id="COR_GRAM_001",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="corrector_sentence_fix",
                    span_start=0,
                    span_end=3,
                    original_text="তিনি",
                    replacement_options=["আমি"],
                    confidence=0.96,
                    explanation_bn="কর্তা ‘আমি’ হলে এই স্থানে ‘আমি’ হওয়া উচিত।",
                    explanation_en="",
                    source=SuggestionSource.MODEL,
                    severity=SuggestionSeverity.MEDIUM,
                    source_trace=["corrector_seq2seq", "exact_unique_match"],
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
                    "checkpoint": "artifacts/corrector/corrector-base",
                    "checkpoint_exists": True,
                    "backend_name": "stub_corrector",
                    "threshold": 0.86,
                },
            )()

    pipeline = _build_pipeline(
        _write_clean_csv_fixture(tmp_path, rows=_regression_runtime_rows()),
        corrector_service=StubCorrectorService(),
    )

    response = pipeline.analyze("আমি আজ স্কুলে যাই।", mode=AnalyzeMode.STANDARD)

    assert response.corrected_text == "আমি আজ স্কুলে যাই।"
    assert response.suggestions == []


def _build_pipeline(
    runtime_csv_path: Path,
    detector_service: DetectorService | None = None,
    corrector_service=None,
) -> AnalysisPipeline:
    if corrector_service is None:
        corrector_service = CorrectorService(
            enabled=False,
            status="disabled",
            reason="disabled in analysis pipeline unit test fixture",
        )
    return AnalysisPipeline(
        normalizer=BanglaNormalizer(),
        spell_engine=SpellEngine(runtime_csv_path=runtime_csv_path),
        rule_engine=RuleEngine(),
        suggestion_manager=SuggestionManager(),
        detector_service=detector_service,
        corrector_service=corrector_service,
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


def _write_runtime_words_fixture(
    base_dir: Path,
    *,
    rows: list[tuple[str, str, str, str, str, str, str, str, str, str]],
) -> Path:
    runtime_csv_path = base_dir / "runtime_words.csv"
    lines = [
        "word,normalized_word,source,is_trusted,is_common,is_active,layer,include_in_runtime,include_as_candidate,review_state"
    ]
    lines.extend(",".join(row) for row in rows)
    runtime_csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_csv_path


def _regression_runtime_rows() -> list[tuple[str, str, str, str, str, str]]:
    return [
        ("আমি", "আমি", "fixture.csv", "1", "1", "1"),
        ("তুমি", "তুমি", "fixture.csv", "1", "1", "1"),
        ("আপনি", "আপনি", "fixture.csv", "1", "1", "1"),
        ("সে", "সে", "fixture.csv", "1", "1", "1"),
        ("ভাত", "ভাত", "fixture.csv", "1", "1", "1"),
        ("স্কুলে", "স্কুলে", "fixture.csv", "1", "1", "1"),
        ("বাংলা", "বাংলা", "fixture.csv", "1", "1", "1"),
        ("ভাষা", "ভাষা", "fixture.csv", "1", "1", "1"),
        ("খুব", "খুব", "fixture.csv", "1", "1", "1"),
        ("সুন্দর", "সুন্দর", "fixture.csv", "1", "1", "1"),
        ("লিখি", "লিখি", "fixture.csv", "1", "1", "1"),
        ("লিখে", "লিখে", "fixture.csv", "1", "1", "1"),
        ("যাই", "যাই", "fixture.csv", "1", "1", "1"),
        ("যাও", "যাও", "fixture.csv", "1", "1", "1"),
        ("যান", "যান", "fixture.csv", "1", "1", "1"),
        ("যায়", "যায়", "fixture.csv", "1", "1", "1"),
        ("খাই", "খাই", "fixture.csv", "1", "1", "1"),
        ("খাও", "খাও", "fixture.csv", "1", "1", "1"),
        ("খান", "খান", "fixture.csv", "1", "1", "1"),
        ("খায়", "খায়", "fixture.csv", "1", "1", "1"),
        ("শুদ্ধ", "শুদ্ধ", "fixture.csv", "1", "1", "1"),
        ("ব্যাকরণ", "ব্যাকরণ", "fixture.csv", "1", "1", "1"),
        ("ঠিক", "ঠিক", "fixture.csv", "1", "1", "1"),
        ("করা", "করা", "fixture.csv", "1", "1", "1"),
        ("দরকার", "দরকার", "fixture.csv", "1", "1", "1"),
        ("যায়", "যায়", "fixture.csv", "1", "0", "1"),
        ("খায়", "খায়", "fixture.csv", "1", "0", "1"),
        ("বংলা", "বাংলা", "fixture.csv", "1", "0", "1"),
    ]
