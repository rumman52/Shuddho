from __future__ import annotations

import re

from shared.constants.bangla import COORDINATORS, REDUPLICATION_WHITELIST
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, TOKEN_BOUNDARY_CHARS, next_non_space_character, token_spans


REPEATED_WORD_PATTERN = re.compile(
    rf"(?<![{TOKEN_BOUNDARY_CHARS}])(?P<word>[\u0980-\u09FFA-Za-z]+)(?P<space>\s+)(?P=word)(?![{TOKEN_BOUNDARY_CHARS}])"
)
DUPLICATE_NEGATION_PATTERN = re.compile(r"(?<![\u0980-\u09FFA-Za-z])না(?P<space>\s+)না(?![\u0980-\u09FFA-Za-z])")
FILLER_PATTERN = re.compile(r"(?<![\u0980-\u09FFA-Za-z])(?P<word>আসলে|মানে|মূলত)(?P<space>\s+)(?P=word)(?![\u0980-\u09FFA-Za-z])")


def repeated_word_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in REPEATED_WORD_PATTERN.finditer(text):
        word = match.group("word")
        normalized_bigram = f"{word} {word}"
        if normalized_bigram in REDUPLICATION_WHITELIST or len(word) < 2:
            continue

        span_start = match.start()
        span_end = match.end()
        confidence = 0.97 if word in {"আমি", "সে", "এই", "ওই", "যে", "না"} else 0.92
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"repeat:{span_start}:{span_end}:{word}"),
                rule_id="REP_001",
                category=SuggestionCategory.GRAMMAR,
                subtype="repeated_word",
                span_start=span_start,
                span_end=span_end,
                original_text=text[span_start:span_end],
                replacement_options=[word],
                confidence=confidence,
                explanation_bn=f"একই শব্দ '{word}' পরপর দুইবার এসেছে।",
                explanation_en=f"The word '{word}' appears twice in a row.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.MEDIUM,
                source_trace=["rule_engine", "exact_repetition"],
            )
        )
    return suggestions


def duplicate_negation_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in DUPLICATE_NEGATION_PATTERN.finditer(text):
        if next_non_space_character(text, match.end()) == "!":
            continue

        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"duplicate-negation:{match.start()}:{match.end()}"),
                rule_id="GRAM_001",
                category=SuggestionCategory.GRAMMAR,
                subtype="duplicate_negation",
                span_start=match.start(),
                span_end=match.end(),
                original_text=match.group(0),
                replacement_options=["না"],
                confidence=0.9,
                explanation_bn="এখানে 'না' শব্দটি অপ্রয়োজনীয়ভাবে দুইবার এসেছে।",
                explanation_en="The word 'না' is repeated unnecessarily here.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.MEDIUM,
                source_trace=["rule_engine", "exact_repetition"],
            )
        )
    return suggestions


def repeated_coordinator_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    tokens = token_spans(text)

    for index in range(len(tokens) - 1):
        left = tokens[index]
        right = tokens[index + 1]
        if left.text != right.text or left.text not in COORDINATORS:
            continue

        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"coordinator-repeat:{left.start}:{right.end}:{left.text}"),
                rule_id="CLEAR_002",
                category=SuggestionCategory.CLARITY,
                subtype="repeated_coordinator",
                span_start=left.start,
                span_end=right.end,
                original_text=text[left.start:right.end],
                replacement_options=[left.text],
                confidence=0.91,
                explanation_bn=f"সংযোজক '{left.text}' পরপর দুইবার এসেছে।",
                explanation_en=f"The connector '{left.text}' appears twice in a row.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                source_trace=["rule_engine", "exact_repetition"],
            )
        )

    return suggestions


def repeated_filler_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for match in FILLER_PATTERN.finditer(text):
        filler = match.group("word")
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"filler-repeat:{match.start()}:{match.end()}:{filler}"),
                rule_id="CLEAR_003",
                category=SuggestionCategory.CLARITY,
                subtype="repeated_filler",
                span_start=match.start(),
                span_end=match.end(),
                original_text=match.group(0),
                replacement_options=[filler],
                confidence=0.9,
                explanation_bn=f"ফিলার শব্দ '{filler}' পরপর দুইবার এসেছে।",
                explanation_en=f"The filler word '{filler}' appears twice in a row.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                source_trace=["rule_engine", "exact_repetition"],
            )
        )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("repeated_word", "Detect accidental repeated words.", repeated_word_rule),
        RuleDefinition("duplicate_negation", "Detect repeated negation.", duplicate_negation_rule),
        RuleDefinition("repeated_coordinator", "Detect repeated connectors.", repeated_coordinator_rule),
        RuleDefinition("repeated_filler", "Detect repeated filler words.", repeated_filler_rule),
    )
