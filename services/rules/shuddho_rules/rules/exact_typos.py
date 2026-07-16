from __future__ import annotations

import re

from shared.constants.bangla import SAFE_EXACT_TYPOS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, TOKEN_BOUNDARY_CHARS


EXTRA_SAFE_EXACT_TYPOS = {
    "অবশই": "অবশ্যই",
    "নিশ্চই": "নিশ্চয়ই",
    "ব্যাবসা": "ব্যবসা",
    "অবস্তা": "অবস্থা",
    "গুরুত্তপূর্ণ": "গুরুত্বপূর্ণ",
    "সর্ম্পক": "সম্পর্ক",
    "অভিজ্ঞ্যতা": "অভিজ্ঞতা",
    "উদ্দ্যোগ": "উদ্যোগ",
    "বাক্তি": "ব্যক্তি",
    "বিদ্যলয়": "বিদ্যালয়",
    "সম্বভ": "সম্ভব",
    "দারুন": "দারুণ",
    "সাহায্য্য": "সাহায্য",
    "বংগালি": "বাঙালি",
    "অপরুপ": "অপরূপ",
    "অত্যাধিক": "অত্যধিক",
    "গান গাচ্ছে": "গান গাইছে",
}

ALL_SAFE_EXACT_TYPOS = {
    **SAFE_EXACT_TYPOS,
    **EXTRA_SAFE_EXACT_TYPOS,
}


def exact_typo_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for typo, replacement in ALL_SAFE_EXACT_TYPOS.items():
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
                    source_trace=["rule_engine", "exact_typo_map"],
                )
            )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("exact_typos", "Apply exact typo corrections from curated maps.", exact_typo_rule),
    )
