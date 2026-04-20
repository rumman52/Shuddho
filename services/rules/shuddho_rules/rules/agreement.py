from __future__ import annotations

from shared.constants.bangla import (
    CASUAL_PRONOUNS,
    CASUAL_VERB_MAP,
    FIRST_PERSON_PRONOUNS,
    FIRST_PERSON_VERB_MAP,
    HONORIFIC_VERB_MAP,
    POLITE_PRONOUNS,
    THIRD_PERSON_PRONOUNS,
    THIRD_PERSON_VERB_MAP,
)
from shared.schemas.python_models import Suggestion

from .base import RuleDefinition, agreement_suggestions, token_spans


def honorific_and_casual_pronoun_verb_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    suggestions: list[Suggestion] = []

    for index, token in enumerate(tokens):
        if token.text in POLITE_PRONOUNS:
            suggestions.extend(
                agreement_suggestions(
                    tokens=tokens,
                    subject_token=token,
                    subject_index=index,
                    replacement_map=HONORIFIC_VERB_MAP,
                    rule_id="GRAM_003",
                    subtype="honorific_pronoun_verb_mismatch",
                    confidence=0.85,
                )
            )
            continue

        if token.text in CASUAL_PRONOUNS:
            suggestions.extend(
                agreement_suggestions(
                    tokens=tokens,
                    subject_token=token,
                    subject_index=index,
                    replacement_map=CASUAL_VERB_MAP,
                    rule_id="GRAM_004",
                    subtype="casual_pronoun_verb_mismatch",
                    confidence=0.85,
                )
            )

    return suggestions


def first_person_verb_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    suggestions: list[Suggestion] = []

    for index, token in enumerate(tokens):
        if token.text not in FIRST_PERSON_PRONOUNS:
            continue
        suggestions.extend(
            agreement_suggestions(
                tokens=tokens,
                subject_token=token,
                subject_index=index,
                replacement_map=FIRST_PERSON_VERB_MAP,
                rule_id="GRAM_005",
                subtype="first_person_verb_mismatch",
                confidence=0.82,
            )
        )

    return suggestions


def third_person_verb_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    suggestions: list[Suggestion] = []

    for index, token in enumerate(tokens):
        if token.text not in THIRD_PERSON_PRONOUNS:
            continue
        suggestions.extend(
            agreement_suggestions(
                tokens=tokens,
                subject_token=token,
                subject_index=index,
                replacement_map=THIRD_PERSON_VERB_MAP,
                rule_id="GRAM_010",
                subtype="third_person_verb_mismatch",
                confidence=0.84,
            )
        )

    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("pronoun_verb_agreement", "Detect honorific and casual pronoun-verb mismatches.", honorific_and_casual_pronoun_verb_rule),
        RuleDefinition("first_person_verb_mismatch", "Detect first-person verb mismatches.", first_person_verb_rule),
        RuleDefinition("third_person_verb_mismatch", "Detect third-person verb mismatches.", third_person_verb_rule),
    )
