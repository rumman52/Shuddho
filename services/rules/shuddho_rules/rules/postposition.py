from __future__ import annotations

from shared.constants.bangla import BANGLA_WORD_PATTERN, COMMON_POSTPOSITIONS, GENITIVE_MARKERS, POSTPOSITION_EXCEPTIONS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, join_genitive, token_spans


SAFE_POSTPOSITION_SUFFIXES = frozenset({"সাথে", "থেকে", "জন্য", *COMMON_POSTPOSITIONS})


def fused_postposition_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    tokens = token_spans(text)

    for token in tokens:
        if not BANGLA_WORD_PATTERN.fullmatch(token.text):
            continue
        if token.text in POSTPOSITION_EXCEPTIONS:
            continue

        for suffix in SAFE_POSTPOSITION_SUFFIXES:
            if not token.text.endswith(suffix) or len(token.text) <= len(suffix) + 1:
                continue

            stem = token.text[: -len(suffix)]
            if not BANGLA_WORD_PATTERN.fullmatch(stem) or stem.endswith("্"):
                continue

            replacement = f"{stem} {suffix}"
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"postposition-split:{token.start}:{token.end}:{suffix}"),
                    rule_id="SPACE_004",
                    category=SuggestionCategory.SPACING,
                    subtype="fused_postposition",
                    span_start=token.start,
                    span_end=token.end,
                    original_text=token.text,
                    replacement_options=[replacement],
                    confidence=0.95 if len(stem) >= 2 else 0.9,
                    explanation_bn=f"এখানে '{suffix}' আলাদা করে লেখা উচিত: '{replacement}'।",
                    explanation_en=f"Write '{suffix}' with a preceding space here: '{replacement}'.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                    source_trace=["rule_engine", "postposition_spacing"],
                )
            )
            break

    return suggestions


def genitive_spacing_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    tokens = token_spans(text)
    for left, right in zip(tokens, tokens[1:]):
        if right.text not in GENITIVE_MARKERS:
            continue
        if not BANGLA_WORD_PATTERN.fullmatch(left.text):
            continue
        between = text[left.end:right.start]
        if not between.isspace():
            continue
        replacement = join_genitive(left.text, right.text)
        original = text[left.start:right.end]
        if replacement == original:
            continue
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"genitive-spacing:{left.start}:{right.end}:{left.text}:{right.text}"),
                rule_id="SPACE_006",
                category=SuggestionCategory.SPACING,
                subtype="genitive_spacing",
                span_start=left.start,
                span_end=right.end,
                original_text=original,
                replacement_options=[replacement],
                confidence=0.91,
                explanation_bn="সম্বন্ধসূচক বিভক্তিটি আগের শব্দের সঙ্গে যুক্ত হবে।",
                explanation_en="The genitive marker should attach to the previous word here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                source_trace=["rule_engine", "genitive_spacing"],
            )
        )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("fused_postposition", "Split fused postpositions when the boundary is safe.", fused_postposition_rule),
        RuleDefinition("genitive_spacing", "Join separated genitive markers when the boundary is safe.", genitive_spacing_rule),
    )
