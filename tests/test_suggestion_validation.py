from services.analysis.shuddho_analysis.suggestion_validation import validate_suggestion, validate_suggestions
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource


def test_validate_suggestion_rejects_wrong_span_and_original_text() -> None:
    suggestion = Suggestion(
        id="bad-span",
        rule_id="GRAM_001",
        category=SuggestionCategory.GRAMMAR,
        subtype="first_person_verb_mismatch",
        span_start=0,
        span_end=2,
        original_text="সে",
        replacement_options=["আমি"],
        confidence=0.96,
        explanation_bn="কর্তা ‘আমি’ হলে ক্রিয়াটি ‘আমি’ হওয়া উচিত।",
        explanation_en="",
        source=SuggestionSource.RULE,
        severity=SuggestionSeverity.MEDIUM,
        source_trace=["rule_engine", "explicit_pronoun_agreement"],
    )

    assert validate_suggestion("আমি স্কুলে যাই।", suggestion, mode=AnalyzeMode.STANDARD) == "original_text_mismatch"


def test_validate_suggestion_rejects_model_without_exact_anchor() -> None:
    text = "আমি স্কুলে যায়।"
    span_start = text.index("যায়")
    span_end = span_start + len("যায়")
    suggestion = Suggestion(
        id="bad-model",
        rule_id="COR_GRAM_001",
        category=SuggestionCategory.GRAMMAR,
        subtype="corrector_sentence_fix",
        span_start=span_start,
        span_end=span_end,
        original_text="যায়",
        replacement_options=["যাই"],
        confidence=0.96,
        explanation_bn="কর্তা ‘আমি’ হলে ক্রিয়াটি ‘যাই’ হওয়া উচিত।",
        explanation_en="",
        source=SuggestionSource.MODEL,
        severity=SuggestionSeverity.MEDIUM,
        source_trace=["model_runtime"],
    )

    assert validate_suggestion(text, suggestion, mode=AnalyzeMode.STANDARD) == "model_missing_exact_anchor"


def test_validate_suggestions_keeps_only_high_confidence_contextual_edits() -> None:
    text = "আমি স্কুলে যায়।"
    span_start = text.index("যায়")
    span_end = span_start + len("যায়")
    valid = Suggestion(
        id="good-rule",
        rule_id="GRAM_005",
        category=SuggestionCategory.GRAMMAR,
        subtype="first_person_verb_mismatch",
        span_start=span_start,
        span_end=span_end,
        original_text="যায়",
        replacement_options=["যাই"],
        confidence=0.95,
        explanation_bn="কর্তা ‘আমি’ হলে ক্রিয়াটি ‘যাই’ হওয়া উচিত।",
        explanation_en="",
        source=SuggestionSource.RULE,
        severity=SuggestionSeverity.MEDIUM,
        source_trace=["rule_engine", "explicit_pronoun_agreement"],
    )
    generic = Suggestion(
        id="generic-model",
        rule_id="COR_GRAM_001",
        category=SuggestionCategory.GRAMMAR,
        subtype="corrector_sentence_fix",
        span_start=span_start,
        span_end=span_end,
        original_text="যায়",
        replacement_options=["যাই"],
        confidence=0.92,
        explanation_bn="আরও স্বাভাবিক লাগবে।",
        explanation_en="",
        source=SuggestionSource.MODEL,
        severity=SuggestionSeverity.MEDIUM,
        source_trace=["corrector_seq2seq", "exact_unique_match"],
    )

    validated = validate_suggestions(text, [valid, generic], mode=AnalyzeMode.STANDARD)

    assert [suggestion.id for suggestion in validated] == ["good-rule"]


def test_ai_original_not_found_rejected_count_warning() -> None:
    from services.api.shuddho_api.suggestion_merge import validate_ai_suggestions
    valid, warnings = validate_ai_suggestions("আমি ভাত খাই।", [{"id":"ai1","sentenceId":"s_0","original":"ডাল","replacement":"ভাত","confidence":0.8}])
    assert valid == []
    assert "ai_suggestion_original_not_found" in warnings
    assert len(warnings) == 1


def test_ai_exact_substring_resolves_span() -> None:
    from services.api.shuddho_api.suggestion_merge import validate_ai_suggestions
    valid, warnings = validate_ai_suggestions("আমি ভাত খাই।", [{"id":"ai1","sentenceId":"s_0","original":"ভাত","replacement":"ডাল","confidence":0.8}])
    assert warnings == []
    assert valid[0]["span_start"] == 4
    assert valid[0]["span_end"] == 7
