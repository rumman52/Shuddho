from __future__ import annotations

from shared.constants.bangla import (
    AGREEMENT_QUOTE_PAIRS,
    AGREEMENT_SENTENCE_BREAKS,
    EXPLICIT_FIRST_PERSON_PRONOUNS,
    EXPLICIT_HONORIFIC_PRONOUNS,
    EXPLICIT_SECOND_PERSON_PRONOUNS,
    EXPLICIT_THIRD_PERSON_PRONOUNS,
    FIRST_PERSON_CONTEXTUAL_VERB_MAP,
    HONORIFIC_DECLARATIVE_VERB_MAP,
    HONORIFIC_IMPERATIVE_VERB_MAP,
    HONORIFIC_REQUEST_MARKERS,
    SECOND_PERSON_CONTEXTUAL_VERB_MAP,
    THIRD_PERSON_CONTEXTUAL_VERB_MAP,
)
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, TokenSpan, token_spans


MAX_AGREEMENT_LOOKAHEAD_WORDS = 4


def honorific_and_casual_pronoun_verb_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    suggestions: list[Suggestion] = []

    for index, token in enumerate(tokens):
        if token.text in EXPLICIT_HONORIFIC_PRONOUNS:
            suggestions.extend(
                _agreement_suggestions(
                    text=text,
                    tokens=tokens,
                    subject_index=index,
                    subject_token=token,
                    rule_id="GRAM_003",
                    subtype="honorific_pronoun_verb_mismatch",
                )
            )
            continue

        if token.text in EXPLICIT_SECOND_PERSON_PRONOUNS:
            suggestions.extend(
                _agreement_suggestions(
                    text=text,
                    tokens=tokens,
                    subject_index=index,
                    subject_token=token,
                    replacement_map=SECOND_PERSON_CONTEXTUAL_VERB_MAP,
                    rule_id="GRAM_004",
                    subtype="casual_pronoun_verb_mismatch",
                    confidence=0.94,
                )
            )

    return suggestions


def first_person_verb_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    suggestions: list[Suggestion] = []

    for index, token in enumerate(tokens):
        if token.text not in EXPLICIT_FIRST_PERSON_PRONOUNS:
            continue
        suggestions.extend(
            _agreement_suggestions(
                text=text,
                tokens=tokens,
                subject_index=index,
                subject_token=token,
                replacement_map=FIRST_PERSON_CONTEXTUAL_VERB_MAP,
                rule_id="GRAM_005",
                subtype="first_person_verb_mismatch",
                confidence=0.95,
            )
        )

    return suggestions


def third_person_verb_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    suggestions: list[Suggestion] = []

    for index, token in enumerate(tokens):
        if token.text not in EXPLICIT_THIRD_PERSON_PRONOUNS:
            continue
        suggestions.extend(
            _agreement_suggestions(
                text=text,
                tokens=tokens,
                subject_index=index,
                subject_token=token,
                replacement_map=THIRD_PERSON_CONTEXTUAL_VERB_MAP,
                rule_id="GRAM_010",
                subtype="third_person_verb_mismatch",
                confidence=0.95,
            )
        )

    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("pronoun_verb_agreement", "Detect honorific and familiar pronoun-verb mismatches.", honorific_and_casual_pronoun_verb_rule),
        RuleDefinition("first_person_verb_mismatch", "Detect first-person Bengali verb mismatches.", first_person_verb_rule),
        RuleDefinition("third_person_verb_mismatch", "Detect third-person Bengali verb mismatches.", third_person_verb_rule),
    )


def _agreement_suggestions(
    *,
    text: str,
    tokens: list[TokenSpan],
    subject_index: int,
    subject_token: TokenSpan,
    rule_id: str,
    subtype: str,
    replacement_map: dict[str, str] | None = None,
    confidence: float = 0.92,
) -> list[Suggestion]:
    if _is_inside_quotes(text, subject_token.start, subject_token.end):
        return []

    looked_ahead_words = 0
    for candidate in tokens[subject_index + 1 :]:
        if candidate.text in AGREEMENT_SENTENCE_BREAKS:
            break
        if not _is_bangla_word(candidate.text):
            continue
        if _is_inside_quotes(text, candidate.start, candidate.end):
            break

        looked_ahead_words += 1
        if looked_ahead_words > MAX_AGREEMENT_LOOKAHEAD_WORDS:
            break

        replacement = (
            _resolve_honorific_replacement(text, tokens, subject_index, candidate)
            if subject_token.text in EXPLICIT_HONORIFIC_PRONOUNS
            else (replacement_map or {}).get(candidate.text)
        )
        if not replacement or replacement == candidate.text:
            continue

        return [
            Suggestion(
                id=stable_id("rule", f"{subtype}:{candidate.start}:{candidate.end}:{candidate.text}->{replacement}"),
                rule_id=rule_id,
                category=SuggestionCategory.GRAMMAR,
                subtype=subtype,
                span_start=candidate.start,
                span_end=candidate.end,
                original_text=candidate.text,
                replacement_options=[replacement],
                confidence=confidence if subject_token.text not in EXPLICIT_HONORIFIC_PRONOUNS else 0.92,
                explanation_bn=_agreement_explanation(subject_token.text, replacement),
                explanation_en=_agreement_explanation_en(subject_token.text, replacement),
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.MEDIUM,
                source_trace=["rule_engine", "explicit_pronoun_agreement"],
            )
        ]

    return []


def _resolve_honorific_replacement(
    text: str,
    tokens: list[TokenSpan],
    subject_index: int,
    candidate: TokenSpan,
) -> str | None:
    imperative_replacement = HONORIFIC_IMPERATIVE_VERB_MAP.get(candidate.text)
    declarative_replacement = HONORIFIC_DECLARATIVE_VERB_MAP.get(candidate.text)

    if imperative_replacement is None and declarative_replacement is None:
        return None
    if imperative_replacement is None:
        return declarative_replacement
    if declarative_replacement is None:
        return imperative_replacement
    if _looks_like_honorific_imperative(text, tokens, subject_index=subject_index, candidate=candidate):
        return imperative_replacement
    return declarative_replacement


def _looks_like_honorific_imperative(
    text: str,
    tokens: list[TokenSpan],
    *,
    subject_index: int,
    candidate: TokenSpan,
) -> bool:
    sentence_end = len(text)
    for token in tokens[subject_index + 1 :]:
        if token.start < candidate.end:
            continue
        if token.text in AGREEMENT_SENTENCE_BREAKS:
            sentence_end = token.end
            break

    sentence_slice = text[tokens[subject_index].start:sentence_end]
    if any(marker in sentence_slice for marker in HONORIFIC_REQUEST_MARKERS):
        return True
    return sentence_slice.rstrip().endswith("!")


def _agreement_explanation(subject: str, replacement: str) -> str:
    if subject == "আমি":
        return f"কর্তা ‘আমি’ হলে ক্রিয়াটি ‘{replacement}’ হওয়া উচিত।"
    if subject == "সে":
        return f"কর্তা ‘সে’ হলে ক্রিয়াটি ‘{replacement}’ হওয়া উচিত।"
    if subject == "তুমি":
        return f"কর্তা ‘তুমি’ হলে ক্রিয়াটি ‘{replacement}’ হওয়া উচিত।"
    if subject == "আপনি":
        return f"সম্বোধন ‘আপনি’ হলে সম্মানসূচক ক্রিয়া ‘{replacement}’ ব্যবহার করা উচিত।"
    if subject == "তিনি":
        return f"কর্তা ‘তিনি’ হলে সম্মানসূচক ক্রিয়া ‘{replacement}’ ব্যবহার করা উচিত।"
    return f"কর্তা ‘{subject}’ হলে ক্রিয়াটি ‘{replacement}’ হওয়া উচিত।"


def _agreement_explanation_en(subject: str, replacement: str) -> str:
    if subject in {"আপনি", "তিনি"}:
        return f"With '{subject}', an honorific verb such as '{replacement}' is expected here."
    return f"With '{subject}', the verb should be '{replacement}' here."


def _is_inside_quotes(text: str, start: int, end: int) -> bool:
    for opening, closing in AGREEMENT_QUOTE_PAIRS.items():
        opening_index = text.rfind(opening, 0, start)
        if opening_index < 0:
            continue
        closing_index = text.find(closing, end)
        if closing_index < 0:
            continue
        if opening_index < start < closing_index:
            return True
    return False


def _is_bangla_word(token: str) -> bool:
    return any("\u0980" <= character <= "\u09ff" for character in token)
