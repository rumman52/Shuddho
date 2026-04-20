from __future__ import annotations

from shared.constants.bangla import (
    BANGLA_WORD_PATTERN,
    COMMON_POSTPOSITIONS,
    GENITIVE_MARKERS,
    POSTPOSITION_EXCEPTIONS,
)
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, join_genitive, token_spans


def fused_postposition_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    tokens = token_spans(text)

    for token in tokens:
        if not BANGLA_WORD_PATTERN.fullmatch(token.text):
            continue
        if token.text in POSTPOSITION_EXCEPTIONS:
            continue

        for suffix in COMMON_POSTPOSITIONS:
            if not token.text.endswith(suffix) or len(token.text) <= len(suffix) + 1:
                continue

            stem = token.text[: -len(suffix)]
            if not BANGLA_WORD_PATTERN.fullmatch(stem) or stem.endswith("্"):
                continue

            confidence = 0.9 if len(stem) >= 2 else 0.7
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"postposition-split:{token.start}:{token.end}:{suffix}"),
                    rule_id="GRAM_007",
                    category=SuggestionCategory.GRAMMAR,
                    subtype="fused_postposition",
                    span_start=token.start,
                    span_end=token.end,
                    original_text=token.text,
                    replacement_options=[f"{stem} {suffix}"],
                    confidence=confidence,
                    explanation_bn=f"'{suffix}' এর আগে সাধারণত একটি ফাঁকা থাকে।",
                    explanation_en=f"'{suffix}' is usually written with a preceding space.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )
            break

    return suggestions


def genitive_spacing_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    tokens = token_spans(text)

    for index in range(len(tokens) - 1):
        noun = tokens[index]
        marker = tokens[index + 1]
        if marker.text not in GENITIVE_MARKERS:
            continue
        if not BANGLA_WORD_PATTERN.fullmatch(noun.text):
            continue

        replacement = join_genitive(noun.text, marker.text)
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"genitive-join:{noun.start}:{marker.end}:{marker.text}"),
                rule_id="GRAM_008",
                category=SuggestionCategory.GRAMMAR,
                subtype="genitive_spacing",
                span_start=noun.start,
                span_end=marker.end,
                original_text=text[noun.start:marker.end],
                replacement_options=[replacement],
                confidence=0.62,
                explanation_bn="সম্বন্ধসূচক রূপটি এখানে আলাদা না লিখে যুক্তভাবে লেখা ভালো।",
                explanation_en="The genitive form is usually written joined here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        )

    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("fused_postposition", "Split fused postpositions.", fused_postposition_rule),
        RuleDefinition("genitive_spacing", "Join separated genitive markers when appropriate.", genitive_spacing_rule, noisy=True),
    )
