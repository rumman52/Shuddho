from __future__ import annotations

import re

from shared.constants.bangla import (
    BANGLA_TO_LATIN_DIGITS,
    CODE_MIX_REPLACEMENTS,
    LATIN_TO_BANGLA_DIGITS,
    POLITE_PRONOUNS,
    CASUAL_PRONOUNS,
)
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, is_bangla_dominant, token_spans


LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{2,}")


def mixed_address_register_rule(text: str) -> list[Suggestion]:
    tokens = token_spans(text)
    seen_polite = next((token for token in tokens if token.text in POLITE_PRONOUNS), None)
    seen_casual = next((token for token in tokens if token.text in CASUAL_PRONOUNS), None)

    if not seen_polite or not seen_casual:
        return []

    later = seen_casual if seen_casual.start > seen_polite.start else seen_polite
    return [
        Suggestion(
            id=stable_id("rule", f"mixed-address:{seen_polite.start}:{seen_casual.end}"),
            rule_id="GRAM_006",
            category=SuggestionCategory.GRAMMAR,
            subtype="mixed_address_register",
            span_start=later.start,
            span_end=later.end,
            original_text=later.text,
            replacement_options=[],
            confidence=0.7,
            explanation_bn="একই বাক্যে ভিন্ন সম্বোধন-স্তর মিশেছে; সম্বোধন একরকম রাখুন।",
            explanation_en="This sentence mixes different address levels; keep the register consistent.",
            source=SuggestionSource.RULE,
            severity=SuggestionSeverity.MEDIUM,
        )
    ]


def mixed_digit_style_rule(text: str) -> list[Suggestion]:
    if not re.search(r"[0-9]", text) or not re.search(r"[০-৯]", text):
        return []

    bangla_digits = text.translate(LATIN_TO_BANGLA_DIGITS)
    latin_digits = text.translate(BANGLA_TO_LATIN_DIGITS)
    replacements = []
    if bangla_digits != text:
        replacements.append(bangla_digits)
    if latin_digits != text:
        replacements.append(latin_digits)

    return [
        Suggestion(
            id=stable_id("rule", f"mixed-digits:{len(text)}:{text}"),
            rule_id="STYLE_001",
            category=SuggestionCategory.STYLE,
            subtype="mixed_digit_style",
            span_start=0,
            span_end=len(text),
            original_text=text,
            replacement_options=replacements,
            confidence=0.7,
            explanation_bn="একই লেখায় বাংলা ও ইংরেজি অঙ্ক মিশেছে; একরকম অঙ্ক ব্যবহার করুন।",
            explanation_en="This text mixes Bengali and Latin digits; use one digit style consistently.",
            source=SuggestionSource.RULE,
            severity=SuggestionSeverity.LOW,
        )
    ]


def code_mixed_latin_rule(text: str) -> list[Suggestion]:
    if not is_bangla_dominant(text, minimum_ratio=0.7):
        return []

    suggestions: list[Suggestion] = []
    for match in LATIN_WORD_PATTERN.finditer(text):
        token = match.group(0)
        replacement = CODE_MIX_REPLACEMENTS.get(token.lower())
        replacement_options = [replacement] if replacement else []
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"code-mix:{match.start()}:{match.end()}:{token.lower()}"),
                rule_id="STYLE_003",
                category=SuggestionCategory.STYLE,
                subtype="code_mixed_latin",
                span_start=match.start(),
                span_end=match.end(),
                original_text=token,
                replacement_options=replacement_options,
                confidence=0.5,
                explanation_bn="বাংলা বাক্যে ইংরেজি শব্দ মিশেছে।",
                explanation_en="This Bangla sentence contains a mixed-in Latin word.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
            )
        )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("mixed_address_register", "Detect mixed address registers.", mixed_address_register_rule, noisy=True),
        RuleDefinition("mixed_digit_style", "Detect mixed Bengali and Latin digits.", mixed_digit_style_rule),
        RuleDefinition("code_mixed_latin", "Detect code-mixed Latin words.", code_mixed_latin_rule, noisy=True),
    )
