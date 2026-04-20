from __future__ import annotations

import re

from shared.constants.bangla import SAFE_EXACT_TYPOS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, TOKEN_BOUNDARY_CHARS


def exact_typo_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for typo, replacement in SAFE_EXACT_TYPOS.items():
        typo_pattern = re.compile(rf"(?<![{TOKEN_BOUNDARY_CHARS}]){re.escape(typo)}(?![{TOKEN_BOUNDARY_CHARS}])")
        for match in typo_pattern.finditer(text):
            original_text = match.group(0)
            category = SuggestionCategory.SPELLING if " " not in replacement and " " not in original_text else SuggestionCategory.GRAMMAR
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"typo:{match.start()}:{match.end()}:{typo}->{replacement}"),
                    rule_id="SPELL_001" if category == SuggestionCategory.SPELLING else "GRAM_009",
                    category=category,
                    subtype="spelling_error" if category == SuggestionCategory.SPELLING else "safe_exact_correction",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=original_text,
                    replacement_options=[replacement],
                    confidence=0.98,
                    explanation_bn=f"এখানে '{original_text}' এর বদলে '{replacement}' লেখা উচিত।",
                    explanation_en=f"Replace '{original_text}' with '{replacement}' here.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM if category == SuggestionCategory.SPELLING else SuggestionSeverity.LOW,
                )
            )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("exact_typos", "Apply exact typo corrections from curated maps.", exact_typo_rule),
    )
