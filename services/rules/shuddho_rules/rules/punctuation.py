from __future__ import annotations

import re

from shared.constants.bangla import PUNCTUATION_CHARS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, is_bangla_dominant


DUPLICATE_PUNCTUATION_PATTERN = re.compile(rf"([{re.escape(PUNCTUATION_CHARS)}])\1+")
BANGLA_FULL_STOP_PATTERN = re.compile(r"(?<![.\d])\.(?!\.)(?=\s|$)")
SPACE_AFTER_TERMINATOR_PATTERN = re.compile(r"([।!?])([^\s\"'”’)\]}])")


def duplicate_punctuation_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in DUPLICATE_PUNCTUATION_PATTERN.finditer(text):
        characters = match.group(0)
        replacement = characters[0]
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"punctuation:{match.start()}:{match.end()}:{characters}"),
                rule_id="PUNC_001",
                category=SuggestionCategory.PUNCTUATION,
                subtype="duplicate_punctuation",
                span_start=match.start(),
                span_end=match.end(),
                original_text=characters,
                replacement_options=[replacement],
                confidence=0.99,
                explanation_bn=f"এখানে '{replacement}' একবারই যথেষ্ট।",
                explanation_en=f"Use '{replacement}' only once here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                source_trace=["rule_engine", "punctuation_rule"],
            )
        )
    return suggestions


def bangla_full_stop_rule(text: str) -> list[Suggestion]:
    if not is_bangla_dominant(text, minimum_ratio=0.6):
        return []

    suggestions: list[Suggestion] = []
    for match in BANGLA_FULL_STOP_PATTERN.finditer(text):
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"bangla-full-stop:{match.start()}:{match.end()}"),
                rule_id="PUNC_003",
                category=SuggestionCategory.PUNCTUATION,
                subtype="bangla_full_stop",
                span_start=match.start(),
                span_end=match.end(),
                original_text=match.group(0),
                replacement_options=["।"],
                confidence=0.95,
                explanation_bn="বাংলা বাক্যের শেষে '.' এর বদলে '।' ব্যবহার করা উচিত।",
                explanation_en="Use '।' instead of '.' at the end of a Bangla sentence.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                source_trace=["rule_engine", "punctuation_rule"],
            )
        )
    return suggestions


def space_after_terminator_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in SPACE_AFTER_TERMINATOR_PATTERN.finditer(text):
        punctuation = match.group(1)
        next_character = match.group(2)
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"spacing-after:{match.start()}:{match.end()}:{punctuation}"),
                rule_id="SPACE_005",
                category=SuggestionCategory.SPACING,
                subtype="space_after_punctuation",
                span_start=match.start(),
                span_end=match.end(),
                original_text=match.group(0),
                replacement_options=[f"{punctuation} {next_character}"],
                confidence=0.91,
                explanation_bn=f"যতিচিহ্ন '{punctuation}'-এর পরে একটি ফাঁকা থাকা উচিত।",
                explanation_en=f"'{punctuation}' should be followed by a space here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                source_trace=["rule_engine", "spacing_rule"],
            )
        )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("duplicate_punctuation", "Detect duplicate punctuation.", duplicate_punctuation_rule),
        RuleDefinition("bangla_full_stop", "Prefer Bangla full stops in Bangla text.", bangla_full_stop_rule),
        RuleDefinition("space_after_punctuation", "Insert a missing space after a terminator.", space_after_terminator_rule),
    )
