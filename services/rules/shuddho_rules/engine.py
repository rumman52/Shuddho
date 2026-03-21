from __future__ import annotations

import re

from shared.constants.bangla import PUNCTUATION_CHARS, SAFE_EXACT_TYPOS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id


TOKEN_BOUNDARY_CHARS = r"\u0980-\u09FFA-Za-z0-9"


class RuleEngine:
    repeated_word_pattern = re.compile(
        rf"(?<![{TOKEN_BOUNDARY_CHARS}])(?P<word>[\u0980-\u09FFA-Za-z]+)(?P<space>\s+)(?P=word)(?![{TOKEN_BOUNDARY_CHARS}])"
    )
    duplicate_punctuation_pattern = re.compile(rf"([{re.escape(PUNCTUATION_CHARS)}])\1+")
    extra_whitespace_pattern = re.compile(rf"(?<=[{TOKEN_BOUNDARY_CHARS}])[^\S\r\n]{{2,}}(?=[{TOKEN_BOUNDARY_CHARS}])")
    whitespace_before_punctuation_pattern = re.compile(rf"\s+([{re.escape(PUNCTUATION_CHARS)}])")

    def analyze(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        suggestions.extend(self._repeated_word_suggestions(text))
        suggestions.extend(self._duplicate_punctuation_suggestions(text))
        suggestions.extend(self._extra_whitespace_suggestions(text))
        suggestions.extend(self._whitespace_before_punctuation_suggestions(text))
        suggestions.extend(self._exact_typo_suggestions(text))
        return suggestions

    def _repeated_word_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.repeated_word_pattern.finditer(text):
            word = match.group("word")
            span_start = match.start()
            span_end = match.end()
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"repeat:{span_start}:{span_end}:{word}"),
                    category=SuggestionCategory.GRAMMAR,
                    subtype="repeated_word",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[word],
                    confidence=0.98,
                    explanation_bn=f"একই শব্দ '{word}' পরপর দুইবার এসেছে।",
                    explanation_en=f"The word '{word}' appears twice in a row.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM,
                )
            )
        return suggestions

    def _duplicate_punctuation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.duplicate_punctuation_pattern.finditer(text):
            characters = match.group(0)
            replacement = characters[0]
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"punctuation:{match.start()}:{match.end()}:{characters}"),
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

    def _extra_whitespace_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.extra_whitespace_pattern.finditer(text):
            span_start = match.start()
            span_end = match.end()
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"extra-space:{span_start}:{span_end}"),
                    category=SuggestionCategory.GRAMMAR,
                    subtype="extra_whitespace",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[" "],
                    confidence=0.97,
                    explanation_bn="দুইটি শব্দের মাঝে অতিরিক্ত ফাঁকা আছে।",
                    explanation_en="There is extra whitespace between these words.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _whitespace_before_punctuation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.whitespace_before_punctuation_pattern.finditer(text):
            punctuation = match.group(1)
            span_start = match.start()
            span_end = match.end()
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"spacing:{span_start}:{span_end}:{punctuation}"),
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="space_before_punctuation",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[punctuation],
                    confidence=0.95,
                    explanation_bn=f"যতিচিহ্ন '{punctuation}' এর আগে অপ্রয়োজনীয় ফাঁকা আছে।",
                    explanation_en=f"There is unnecessary whitespace before '{punctuation}'.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW,
                )
            )
        return suggestions

    def _exact_typo_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for typo, replacement in SAFE_EXACT_TYPOS.items():
            typo_pattern = re.compile(rf"(?<![{TOKEN_BOUNDARY_CHARS}]){re.escape(typo)}(?![{TOKEN_BOUNDARY_CHARS}])")
            for match in typo_pattern.finditer(text):
                original_text = match.group(0)
                suggestions.append(
                    Suggestion(
                        id=stable_id("rule", f"typo:{match.start()}:{match.end()}:{typo}->{replacement}"),
                        category=SuggestionCategory.CORRECTNESS,
                        subtype="safe_exact_typo",
                        span_start=match.start(),
                        span_end=match.end(),
                        original_text=original_text,
                        replacement_options=[replacement],
                        confidence=0.98,
                        explanation_bn=f"এখানে '{original_text}' এর বদলে '{replacement}' লেখা উচিত।",
                        explanation_en=f"Replace '{original_text}' with '{replacement}' here.",
                        source=SuggestionSource.RULE,
                        severity=SuggestionSeverity.MEDIUM,
                    )
                )
        return suggestions
