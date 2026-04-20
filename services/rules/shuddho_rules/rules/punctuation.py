from __future__ import annotations

import re

from shared.constants.bangla import CLOSING_DELIMITERS, OPENING_DELIMITERS, PUNCTUATION_CHARS
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
                explanation_bn=f"এখানে '{characters}' এর বদলে '{replacement}' ব্যবহার করুন।",
                explanation_en=f"Replace '{characters}' with '{replacement}' here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
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
                confidence=0.9,
                explanation_bn="বাংলা বাক্যের শেষে '.' এর বদলে '।' ব্যবহার করুন।",
                explanation_en="Use '।' instead of '.' at the end of a Bangla sentence.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
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
                rule_id="PUNC_004",
                category=SuggestionCategory.PUNCTUATION,
                subtype="space_after_punctuation",
                span_start=match.start(),
                span_end=match.end(),
                original_text=match.group(0),
                replacement_options=[f"{punctuation} {next_character}"],
                confidence=0.85,
                explanation_bn=f"যতিচিহ্ন '{punctuation}' এর পরে সাধারণত একটি ফাঁকা থাকে।",
                explanation_en=f"'{punctuation}' is usually followed by a space here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        )
    return suggestions


def unbalanced_delimiter_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    stack: list[tuple[str, int]] = []

    for index, character in enumerate(text):
        if character in OPENING_DELIMITERS:
            stack.append((character, index))
            continue

        if character not in CLOSING_DELIMITERS:
            continue

        if stack and stack[-1][0] == CLOSING_DELIMITERS[character]:
            stack.pop()
            continue

        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"unbalanced-closing:{index}:{character}"),
                rule_id="PUNC_005",
                category=SuggestionCategory.PUNCTUATION,
                subtype="unbalanced_delimiter",
                span_start=index,
                span_end=index + 1,
                original_text=character,
                replacement_options=[],
                confidence=0.83,
                explanation_bn="বন্ধনী বা উদ্ধৃতি চিহ্নের জোড়া অসম্পূর্ণ।",
                explanation_en="This bracket or quote is unbalanced.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.MEDIUM,
            )
        )

    for character, index in stack:
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"unbalanced-opening:{index}:{character}"),
                rule_id="PUNC_005",
                category=SuggestionCategory.PUNCTUATION,
                subtype="unbalanced_delimiter",
                span_start=index,
                span_end=index + 1,
                original_text=character,
                replacement_options=[],
                confidence=0.7,
                explanation_bn="বন্ধনী বা উদ্ধৃতি চিহ্নের জোড়া অসম্পূর্ণ।",
                explanation_en="This bracket or quote is unbalanced.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.MEDIUM,
            )
        )

    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("duplicate_punctuation", "Detect duplicate punctuation.", duplicate_punctuation_rule),
        RuleDefinition("bangla_full_stop", "Prefer Bangla full stops in Bangla text.", bangla_full_stop_rule),
        RuleDefinition("space_after_punctuation", "Insert missing space after a terminator.", space_after_terminator_rule),
        RuleDefinition("unbalanced_delimiter", "Detect unbalanced delimiters.", unbalanced_delimiter_rule),
    )
