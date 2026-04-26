from __future__ import annotations

import re

from shared.constants.bangla import CODE_MIX_REPLACEMENTS
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id

from .base import RuleDefinition, is_bangla_dominant, token_spans


LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{2,}")
FORMAL_LEXICAL_REPLACEMENTS = {
    "প্লিজ": "অনুগ্রহ করে",
    "ওকে": "ঠিক আছে",
}
FORMAL_CONTEXT_MARKERS = frozenset(
    {
        "অনুগ্রহ",
        "রিপোর্ট",
        "প্রতিবেদন",
        "নথি",
        "দলিল",
        "মেইল",
        "ইমেইল",
        "পাঠান",
        "জমা",
        "অনুমোদন",
        "অফিস",
        "আবেদন",
    }
)


def formal_lexical_replacement_rule(text: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for token in token_spans(text):
        replacement = FORMAL_LEXICAL_REPLACEMENTS.get(token.text)
        if replacement is None or _is_inside_quotes(text, token.start, token.end):
            continue
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"formal-lexical:{token.start}:{token.end}:{token.text}->{replacement}"),
                rule_id="REG_001",
                category=SuggestionCategory.REGISTER,
                subtype="formal_lexical_replacement",
                span_start=token.start,
                span_end=token.end,
                original_text=token.text,
                replacement_options=[replacement],
                confidence=0.94,
                explanation_bn=f"আনুষ্ঠানিক লেখায় '{token.text}' এর বদলে '{replacement}' বেশি উপযুক্ত।",
                explanation_en=f"In formal writing, '{replacement}' is more appropriate than '{token.text}'.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                optional_mode_visibility=[AnalyzeMode.FORMAL],
                source_trace=["rule_engine", "formal_mode_only"],
            )
        )
    return suggestions


def formal_pronoun_rule(text: str) -> list[Suggestion]:
    if not _looks_formal_professional_sentence(text):
        return []

    suggestions: list[Suggestion] = []
    for token in token_spans(text):
        if token.text != "তুমি" or _is_inside_quotes(text, token.start, token.end):
            continue
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"formal-pronoun:{token.start}:{token.end}"),
                rule_id="REG_002",
                category=SuggestionCategory.REGISTER,
                subtype="formal_pronoun_replacement",
                span_start=token.start,
                span_end=token.end,
                original_text=token.text,
                replacement_options=["আপনি"],
                confidence=0.92,
                explanation_bn="আনুষ্ঠানিক বা পেশাদার বাক্যে 'তুমি' এর বদলে 'আপনি' বেশি উপযুক্ত।",
                explanation_en="In a formal or professional sentence, 'আপনি' is more appropriate than 'তুমি'.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                optional_mode_visibility=[AnalyzeMode.FORMAL],
                source_trace=["rule_engine", "formal_mode_only"],
            )
        )
    return suggestions


def code_mixed_latin_rule(text: str) -> list[Suggestion]:
    if not is_bangla_dominant(text, minimum_ratio=0.7):
        return []

    suggestions: list[Suggestion] = []
    for match in LATIN_WORD_PATTERN.finditer(text):
        token = match.group(0)
        replacement = CODE_MIX_REPLACEMENTS.get(token.lower())
        if not replacement:
            continue
        suggestions.append(
            Suggestion(
                id=stable_id("rule", f"code-mix:{match.start()}:{match.end()}:{token.lower()}"),
                rule_id="CLEAR_001",
                category=SuggestionCategory.CLARITY,
                subtype="code_mixed_latin",
                span_start=match.start(),
                span_end=match.end(),
                original_text=token,
                replacement_options=[replacement],
                confidence=0.9,
                explanation_bn=f"বাংলা বাক্যে '{token}' এর বদলে '{replacement}' ব্যবহার করলে ভাষা একরকম থাকে।",
                explanation_en=f"Replacing '{token}' with '{replacement}' keeps the sentence in Bangla.",
                source=SuggestionSource.RULE,
                severity=SuggestionSeverity.LOW,
                optional_mode_visibility=[AnalyzeMode.STRICT, AnalyzeMode.FORMAL],
                source_trace=["rule_engine", "exact_code_mix_map"],
            )
        )
    return suggestions


def build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("formal_lexical_replacement", "Offer safe formal word replacements in formal mode.", formal_lexical_replacement_rule),
        RuleDefinition("formal_pronoun_replacement", "Offer 'তুমি' -> 'আপনি' only in clearly formal sentences.", formal_pronoun_rule),
        RuleDefinition("code_mixed_latin", "Offer exact Bangla replacements for a small safe code-mix map.", code_mixed_latin_rule, noisy=True),
    )


def _looks_formal_professional_sentence(text: str) -> bool:
    tokens = {token.text for token in token_spans(text)}
    return bool(tokens & FORMAL_CONTEXT_MARKERS)


def _is_inside_quotes(text: str, start: int, end: int) -> bool:
    for opening, closing in {'"': '"', "“": "”", "‘": "’"}.items():
        opening_index = text.rfind(opening, 0, start)
        if opening_index < 0:
            continue
        closing_index = text.find(closing, end)
        if closing_index < 0:
            continue
        if opening_index < start < closing_index:
            return True
    return False
