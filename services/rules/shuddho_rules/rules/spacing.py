from __future__ import annotations

import re

from shared.constants.bangla import COMMON_UNITS, PUNCTUATION_CHARS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, TOKEN_BOUNDARY_CHARS


EXTRA_WHITESPACE_PATTERN = re.compile(rf"(?<=[{TOKEN_BOUNDARY_CHARS}])[^\S\r\n]{{2,}}(?=[{TOKEN_BOUNDARY_CHARS}])")
WHITESPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(rf"\s+([{re.escape(PUNCTUATION_CHARS)}])")
NUMBER_UNIT_SPACING_PATTERN = re.compile(r"([0-9০-৯]+)(কেজি|কিমি|মিটার|ঘণ্টা|টাকা|জন)")


def extra_whitespace_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in EXTRA_WHITESPACE_PATTERN.finditer(text):
        span_start = match.start()
        span_end = match.end()
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"extra-space:{span_start}:{span_end}"),
                rule_id="SPACE_001",
                category=SuggestionCategory.GRAMMAR,
                subtype="extra_whitespace",
                span_start=span_start,
                span_end=span_end,
                original_text=text[span_start:span_end],
                replacement_options=[" "],
                confidence=0.99,
                explanation_bn="দুইটি শব্দের মাঝে অতিরিক্ত ফাঁকা আছে।",
                explanation_en="There is extra whitespace between these words.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        )
    return suggestions


def whitespace_before_punctuation_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in WHITESPACE_BEFORE_PUNCTUATION_PATTERN.finditer(text):
        punctuation = match.group(1)
        span_start = match.start()
        span_end = match.end()
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"spacing-before:{span_start}:{span_end}:{punctuation}"),
                rule_id="PUNC_002",
                category=SuggestionCategory.PUNCTUATION,
                subtype="space_before_punctuation",
                span_start=span_start,
                span_end=span_end,
                original_text=text[span_start:span_end],
                replacement_options=[punctuation],
                confidence=0.98,
                explanation_bn=f"যতিচিহ্ন '{punctuation}' এর আগে অপ্রয়োজনীয় ফাঁকা আছে।",
                explanation_en=f"There is unnecessary whitespace before '{punctuation}'.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        )
    return suggestions


def number_unit_spacing_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in NUMBER_UNIT_SPACING_PATTERN.finditer(text):
        number = match.group(1)
        unit = match.group(2)
        if unit not in COMMON_UNITS:
            continue
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"unit-spacing:{match.start()}:{match.end()}:{unit}"),
                rule_id="STYLE_002",
                category=SuggestionCategory.STYLE,
                subtype="number_unit_spacing",
                span_start=match.start(),
                span_end=match.end(),
                original_text=match.group(0),
                replacement_options=[f"{number} {unit}"],
                confidence=0.85,
                explanation_bn=f"সংখ্যার পরে একক '{unit}' হলে সাধারণত একটি ফাঁকা থাকে।",
                explanation_en=f"A space is usually written before the unit '{unit}'.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("extra_whitespace", "Collapse extra whitespace between words.", extra_whitespace_rule),
        RuleDefinition("space_before_punctuation", "Remove spaces before punctuation.", whitespace_before_punctuation_rule),
        RuleDefinition("number_unit_spacing", "Insert a space between numbers and units.", number_unit_spacing_rule),
    )
