from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from shared.constants.bangla import BANGLA_LETTER_PATTERN, PUNCTUATION_CHARS
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionKind, SuggestionSource


PUNCTUATION_OR_SPACE_RE = re.compile(rf"^[\s{re.escape(PUNCTUATION_CHARS)}]+$")
LATIN_RE = re.compile(r"[A-Za-z]")
GENERIC_EXPLANATION_MARKERS = {
    "আরও স্বাভাবিক",
    "আরও ভালো",
    "আরও পরিষ্কার",
    "আরও প্রাকৃতিক",
    "make it better",
    "clearer",
    "more natural",
    "more useful",
}
SPECIFIC_EXPLANATION_MARKERS = {
    "কর্তা",
    "ক্রিয়া",
    "সম্বোধন",
    "যতিচিহ্ন",
    "ফাঁকা",
    "শব্দ",
    "বানান",
    "অভিধান",
    "পুনরাবৃত্তি",
    "মানক রূপ",
    "সম্মানসূচক",
    "সংখ্যা",
    "একক",
}
DETERMINISTIC_RULE_EXPLANATION_SUBTYPES = {
    "extra_whitespace",
    "space_before_punctuation",
    "space_after_punctuation",
    "duplicate_punctuation",
    "repeated_word",
    "number_unit_spacing",
    "fused_postposition",
    "duplicate_negation",
    "first_person_verb_mismatch",
    "third_person_verb_mismatch",
    "casual_pronoun_verb_mismatch",
    "honorific_pronoun_verb_mismatch",
    "formal_lexical_replacement",
    "formal_pronoun_replacement",
}
MODEL_REQUIRED_SOURCE_TRACE = {
    "exact_unique_match",
    "occurrence_index",
    "anchor_triplet",
    "detector_exact_span_support",
}


def validate_suggestions(
    text: str,
    suggestions: Sequence[Suggestion],
    *,
    mode: AnalyzeMode,
    logger: logging.Logger | None = None,
) -> list[Suggestion]:
    validated: list[Suggestion] = []
    for suggestion in suggestions:
        rejection_reason = validate_suggestion(text, suggestion, mode=mode)
        if rejection_reason is not None:
            if logger is not None:
                logger.info(
                    "Dropped suggestion rule_id=%s subtype=%s span=%s:%s reason=%s",
                    suggestion.rule_id,
                    suggestion.subtype,
                    suggestion.span_start,
                    suggestion.span_end,
                    rejection_reason,
                )
            continue

        validated_alternatives = []
        for alternative in suggestion.alternatives:
            alternative_suggestion = suggestion.model_copy(
                update={
                    "id": alternative.id,
                    "rule_id": alternative.rule_id,
                    "category": alternative.category,
                    "subtype": alternative.subtype,
                    "original_text": alternative.original_text,
                    "replacement_options": list(alternative.replacement_options),
                    "confidence": alternative.confidence,
                    "explanation_bn": alternative.explanation_bn,
                    "explanation_en": alternative.explanation_en,
                    "source": alternative.source,
                    "severity": alternative.severity,
                    "feedback_key": alternative.feedback_key,
                    "suggestion_kind": alternative.suggestion_kind,
                    "suppression_key": alternative.suppression_key,
                    "is_variant_only": alternative.is_variant_only,
                    "source_trace": list(alternative.source_trace or suggestion.source_trace or []),
                    "alternatives": [],
                }
            )
            if validate_suggestion(text, alternative_suggestion, mode=mode) is None:
                validated_alternatives.append(alternative)

        validated.append(suggestion.model_copy(update={"alternatives": validated_alternatives}))
    return validated


def validate_suggestion(
    text: str,
    suggestion: Suggestion,
    *,
    mode: AnalyzeMode,
) -> str | None:
    if suggestion.category == SuggestionCategory.REWRITE_ONLY:
        return "rewrite_only_not_allowed"

    if suggestion.span_start < 0 or suggestion.span_end > len(text) or suggestion.span_start >= suggestion.span_end:
        return "invalid_span"

    original_span_text = text[suggestion.span_start : suggestion.span_end]
    if original_span_text != suggestion.original_text:
        return "original_text_mismatch"

    if not suggestion.source_trace:
        return "missing_source_trace"

    if not suggestion.replacement_options:
        return "missing_replacement_options"

    primary_replacement = suggestion.replacement_options[0]
    if not primary_replacement:
        return "empty_primary_replacement"

    if primary_replacement == suggestion.original_text and suggestion.suggestion_kind not in {
        SuggestionKind.NO_SUGGESTION,
        SuggestionKind.NAMED_ENTITY_OR_USER_WORD,
    }:
        return "noop_replacement"

    if suggestion.confidence < minimum_confidence_for_suggestion(suggestion, mode=mode):
        return "below_confidence_threshold"

    if not _replacement_preserves_local_boundaries(suggestion, primary_replacement):
        return "unsafe_boundary_change"

    if not _replacement_is_language_safe(suggestion, primary_replacement):
        return "unsafe_replacement_language"

    if looks_generic_explanation(suggestion.explanation_bn or suggestion.explanation_en, suggestion):
        return "generic_explanation"

    if suggestion.source == SuggestionSource.SPELL and suggestion.rule_id == "SPELL_003":
        if "generic_high_margin" not in suggestion.source_trace:
            return "weak_lexicon_guess"

    if suggestion.source == SuggestionSource.HYBRID and "detector_contextual_support" in suggestion.source_trace:
        if "detector_exact_span_support" not in suggestion.source_trace:
            return "hybrid_missing_exact_support"

    if _depends_on_model_anchor(suggestion):
        if "anchor_nearest_safe" in suggestion.source_trace:
            return "model_nearest_anchor_rejected"
        if not any(marker in suggestion.source_trace for marker in MODEL_REQUIRED_SOURCE_TRACE):
            return "model_missing_exact_anchor"

    if _replacement_changes_meaning_too_much(text, suggestion, primary_replacement, mode=mode):
        return "meaning_shift_too_large"

    return None


def minimum_confidence_for_suggestion(
    suggestion: Suggestion,
    *,
    mode: AnalyzeMode,
) -> float:
    thresholds = {
        AnalyzeMode.STANDARD: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.94,
            SuggestionKind.GRAMMAR_ERROR: 0.88,
            SuggestionKind.PUNCTUATION_ERROR: 0.88,
            SuggestionKind.SPACING_ERROR: 0.9,
            SuggestionKind.STYLE_SUGGESTION: 0.9,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.95,
            SuggestionKind.NAMED_ENTITY_OR_USER_WORD: 1.0,
            SuggestionKind.NO_SUGGESTION: 1.0,
            None: 0.97,
        },
        AnalyzeMode.STRICT: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.92,
            SuggestionKind.GRAMMAR_ERROR: 0.84,
            SuggestionKind.PUNCTUATION_ERROR: 0.84,
            SuggestionKind.SPACING_ERROR: 0.84,
            SuggestionKind.STYLE_SUGGESTION: 0.84,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.84,
            SuggestionKind.NAMED_ENTITY_OR_USER_WORD: 1.0,
            SuggestionKind.NO_SUGGESTION: 1.0,
            None: 0.95,
        },
        AnalyzeMode.FORMAL: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.92,
            SuggestionKind.GRAMMAR_ERROR: 0.84,
            SuggestionKind.PUNCTUATION_ERROR: 0.84,
            SuggestionKind.SPACING_ERROR: 0.84,
            SuggestionKind.STYLE_SUGGESTION: 0.82,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.84,
            SuggestionKind.NAMED_ENTITY_OR_USER_WORD: 1.0,
            SuggestionKind.NO_SUGGESTION: 1.0,
            None: 0.95,
        },
    }

    threshold = thresholds[mode].get(suggestion.suggestion_kind, thresholds[mode][None])
    if suggestion.source == SuggestionSource.MODEL:
        threshold += 0.05
    elif suggestion.source == SuggestionSource.HYBRID and suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR:
        threshold += 0.03
    if suggestion.is_variant_only and mode == AnalyzeMode.STANDARD:
        threshold += 0.02
    return min(round(threshold, 2), 0.99)


def looks_generic_explanation(explanation: str, suggestion: Suggestion) -> bool:
    normalized = " ".join(explanation.split()).strip()
    if not normalized:
        return True
    if len(normalized.split()) <= 3:
        return True
    lowered = normalized.lower()
    if any(marker in lowered for marker in {marker.lower() for marker in GENERIC_EXPLANATION_MARKERS}):
        return True
    if suggestion.source == SuggestionSource.RULE and suggestion.subtype in DETERMINISTIC_RULE_EXPLANATION_SUBTYPES:
        return False
    if suggestion.original_text in normalized:
        return False
    if any(replacement in normalized for replacement in suggestion.replacement_options):
        return False
    return not any(marker in normalized for marker in SPECIFIC_EXPLANATION_MARKERS)


def _replacement_preserves_local_boundaries(suggestion: Suggestion, replacement: str) -> bool:
    if "\n" in replacement:
        return False

    original = suggestion.original_text
    if suggestion.category in {SuggestionCategory.PUNCTUATION, SuggestionCategory.SPACING}:
        return len(replacement) <= max(len(original) + 3, 12)

    if replacement[:1].isspace() or replacement[-1:].isspace():
        return False
    if original[:1].isspace() != replacement[:1].isspace():
        return False
    if original[-1:].isspace() != replacement[-1:].isspace():
        return False
    if original and original[0] in PUNCTUATION_CHARS and replacement[0] not in PUNCTUATION_CHARS:
        return False
    if original and original[-1] in PUNCTUATION_CHARS and replacement[-1] not in PUNCTUATION_CHARS:
        return False
    return True


def _replacement_is_language_safe(suggestion: Suggestion, replacement: str) -> bool:
    if suggestion.subtype == "code_mixed_latin":
        return True

    if suggestion.category in {SuggestionCategory.PUNCTUATION, SuggestionCategory.SPACING}:
        return all(
            character.isspace()
            or character in PUNCTUATION_CHARS
            or bool(BANGLA_LETTER_PATTERN.search(character))
            for character in replacement
        )

    if LATIN_RE.search(replacement):
        return False
    if PUNCTUATION_OR_SPACE_RE.fullmatch(replacement):
        return False
    return bool(BANGLA_LETTER_PATTERN.search(replacement))


def _depends_on_model_anchor(suggestion: Suggestion) -> bool:
    if suggestion.source == SuggestionSource.MODEL:
        return True
    if suggestion.source != SuggestionSource.HYBRID:
        return False
    return any(
        marker in (suggestion.source_trace or [])
        for marker in {"detector_contextual_support", "corrector_seq2seq"}
    )


def _replacement_changes_meaning_too_much(
    text: str,
    suggestion: Suggestion,
    replacement: str,
    *,
    mode: AnalyzeMode,
) -> bool:
    original = suggestion.original_text.strip()
    replacement = replacement.strip()
    if not original or not replacement:
        return True
    if suggestion.category in {SuggestionCategory.PUNCTUATION, SuggestionCategory.SPACING}:
        return False
    if replacement == text.strip() and original != text.strip():
        return True

    original_tokens = len(original.split())
    replacement_tokens = len(replacement.split())
    token_limit = 4 if suggestion.category == SuggestionCategory.REGISTER else 6
    char_limit = (
        max(int(len(original) * 2.1), len(original) + 6, 18)
        if mode == AnalyzeMode.STANDARD
        else max(int(len(original) * 2.4), len(original) + 8, 22)
    )
    if replacement_tokens > token_limit:
        return True
    if len(replacement) > char_limit:
        return True
    if original_tokens <= 2 and replacement_tokens >= original_tokens + 2:
        return True
    if suggestion.source in {SuggestionSource.MODEL, SuggestionSource.HYBRID}:
        if replacement_tokens >= max(original_tokens + 2, 4):
            return True
        if len(replacement) >= max(len(original) * 2.4, len(original) + 12):
            return True
    return False
