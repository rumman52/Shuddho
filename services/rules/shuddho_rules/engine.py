from __future__ import annotations

import re

from shared.constants.bangla import PUNCTUATION_CHARS, SAFE_EXACT_TYPOS
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id


class RuleEngine:
    repeated_word_pattern = re.compile(r"(?P<word>[\u0980-\u09FFA-Za-z]+)(?P<space>\s+)(?P=word)")
    duplicate_punctuation_pattern = re.compile(rf"([{re.escape(PUNCTUATION_CHARS)}])\1+")
    whitespace_before_punctuation_pattern = re.compile(rf"\s+([{re.escape(PUNCTUATION_CHARS)}])")

    def analyze(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        suggestions.extend(self._repeated_word_suggestions(text))
        suggestions.extend(self._duplicate_punctuation_suggestions(text))
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
                    confidence=0.96,
                    explanation_bn="একই শব্দ পরপর দুবার এসেছে। একটি রাখাই যথেষ্ট।",
                    explanation_en="The same word appears consecutively. Keeping one instance is usually correct.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.MEDIUM
                )
            )
        return suggestions

    def _duplicate_punctuation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.duplicate_punctuation_pattern.finditer(text):
            characters = match.group(0)
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"punctuation:{match.start()}:{match.end()}:{characters}"),
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="duplicate_punctuation",
                    span_start=match.start(),
                    span_end=match.end(),
                    original_text=characters,
                    replacement_options=[characters[0]],
                    confidence=0.97,
                    explanation_bn="একাধিক একই চিহ্ন একসাথে এসেছে। সাধারণত একটি চিহ্নই যথেষ্ট।",
                    explanation_en="The same punctuation mark appears multiple times. A single mark is usually enough.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW
                )
            )
        return suggestions

    def _whitespace_before_punctuation_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for match in self.whitespace_before_punctuation_pattern.finditer(text):
            punctuation = match.group(1)
            span_start = match.start()
            span_end = match.end()
            replacement = punctuation
            suggestions.append(
                Suggestion(
                    id=stable_id("rule", f"spacing:{span_start}:{span_end}:{punctuation}"),
                    category=SuggestionCategory.PUNCTUATION,
                    subtype="space_before_punctuation",
                    span_start=span_start,
                    span_end=span_end,
                    original_text=text[span_start:span_end],
                    replacement_options=[replacement],
                    confidence=0.95,
                    explanation_bn="বিরামচিহ্নের আগে অতিরিক্ত ফাঁকা আছে।",
                    explanation_en="There is unnecessary whitespace before punctuation.",
                    source=SuggestionSource.RULE,
                    severity=SuggestionSeverity.LOW
                )
            )
        return suggestions

    def _exact_typo_suggestions(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for typo, replacement in SAFE_EXACT_TYPOS.items():
            for match in re.finditer(re.escape(typo), text):
                suggestions.append(
                    Suggestion(
                        id=stable_id("rule", f"typo:{match.start()}:{match.end()}:{typo}->{replacement}"),
                        category=SuggestionCategory.CORRECTNESS,
                        subtype="safe_exact_typo",
                        span_start=match.start(),
                        span_end=match.end(),
                        original_text=match.group(0),
                        replacement_options=[replacement],
                        confidence=0.98,
                        explanation_bn="এটি একটি পরিচিত ও নিরাপদ সংশোধন।",
                        explanation_en="This is a known conservative correction.",
                        source=SuggestionSource.RULE,
                        severity=SuggestionSeverity.MEDIUM
                    )
                )
        return suggestions

