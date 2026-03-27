from shared.schemas.python_models import (
    AnalyzeMode,
    AnalyzeRequest,
    Suggestion,
    SuggestionCategory,
    SuggestionKind,
    SuggestionSeverity,
    SuggestionSource,
)


def test_analyze_request_normalizes_personal_dictionary_entries() -> None:
    request = AnalyzeRequest(
        text="\u09ac\u09be\u0982\u09b2\u09be",
        personal_dictionary=["  \u09b6\u09ac\u09cd\u09a6  ", "", "\u09b6\u09ac\u09cd\u09a6", "\u09ac\u09cd\u09af\u0995\u09cd\u09a4\u09bf\u0997\u09a4   \u09b6\u09ac\u09cd\u09a6  "],
    )

    assert request.personal_dictionary == ["\u09b6\u09ac\u09cd\u09a6", "\u09ac\u09cd\u09af\u0995\u09cd\u09a4\u09bf\u0997\u09a4 \u09b6\u09ac\u09cd\u09a6"]
    assert request.mode == AnalyzeMode.STANDARD


def test_analyze_request_accepts_explicit_mode() -> None:
    request = AnalyzeRequest(text="\u09ac\u09be\u0982\u09b2\u09be", mode=AnalyzeMode.FORMAL)

    assert request.mode == AnalyzeMode.FORMAL


def test_suggestion_infers_variant_metadata_for_optional_orthography_forms() -> None:
    suggestion = Suggestion(
        id="spell_002",
        rule_id="SPELL_002",
        category=SuggestionCategory.STYLE,
        subtype="orthography_variant",
        span_start=0,
        span_end=5,
        original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
        replacement_options=["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"],
        confidence=0.84,
        explanation_bn="",
        explanation_en="",
        source=SuggestionSource.SPELL,
        severity=SuggestionSeverity.LOW,
    )

    assert suggestion.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT
    assert suggestion.is_variant_only is True
    assert suggestion.optional_mode_visibility == [AnalyzeMode.STRICT, AnalyzeMode.FORMAL]
    assert suggestion.is_contextual is False
    assert suggestion.suppression_key is not None


def test_suggestion_preserves_whitespace_only_replacements_for_spacing_fixes() -> None:
    suggestion = Suggestion(
        id="space_001",
        rule_id="SPACE_001",
        category=SuggestionCategory.GRAMMAR,
        subtype="extra_whitespace",
        span_start=2,
        span_end=4,
        original_text="  ",
        replacement_options=[" "],
        confidence=0.99,
        explanation_bn="",
        explanation_en="",
        source=SuggestionSource.RULE,
        severity=SuggestionSeverity.LOW,
    )

    assert suggestion.replacement_options == [" "]
    assert suggestion.suggestion_kind == SuggestionKind.SPACING_ERROR
