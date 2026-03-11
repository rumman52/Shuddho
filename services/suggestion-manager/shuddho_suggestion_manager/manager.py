from __future__ import annotations

from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import Suggestion, SuggestionSource


SOURCE_PRIORITY = {
    SuggestionSource.RULE: 0,
    SuggestionSource.HYBRID: 1,
    SuggestionSource.SPELL: 2,
    SuggestionSource.MODEL: 3
}


class SuggestionManager:
    def merge(
        self,
        original_text: str,
        normalized: NormalizedText,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion]
    ) -> list[Suggestion]:
        mapped_spell = [self._map_to_original(suggestion, original_text, normalized) for suggestion in spell_suggestions]
        combined = rule_suggestions + mapped_spell
        combined = [suggestion for suggestion in combined if self._keep_confident(suggestion)]
        combined.sort(key=self._sort_key)
        return self._dedupe(combined)

    def _map_to_original(self, suggestion: Suggestion, original_text: str, normalized: NormalizedText) -> Suggestion:
        span_start, span_end = normalized.to_original_span(suggestion.span_start, suggestion.span_end)
        return suggestion.model_copy(
            update={
                "span_start": span_start,
                "span_end": span_end,
                "original_text": original_text[span_start:span_end]
            }
        )

    def _keep_confident(self, suggestion: Suggestion) -> bool:
        if suggestion.source == SuggestionSource.RULE:
            return True
        return suggestion.confidence >= 0.78

    def _sort_key(self, suggestion: Suggestion) -> tuple[int, int, int, float]:
        return (
            suggestion.span_start,
            suggestion.span_end,
            SOURCE_PRIORITY[suggestion.source],
            -suggestion.confidence
        )

    def _dedupe(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        deduped: list[Suggestion] = []
        seen_keys: set[tuple[int, int, str, tuple[str, ...]]] = set()

        for suggestion in suggestions:
            key = (
                suggestion.span_start,
                suggestion.span_end,
                suggestion.subtype,
                tuple(suggestion.replacement_options)
            )
            if key in seen_keys:
                continue
            if deduped and self._overlaps(deduped[-1], suggestion):
                previous = deduped[-1]
                if previous.replacement_options == suggestion.replacement_options:
                    continue
                if previous.source == SuggestionSource.RULE and suggestion.source == SuggestionSource.SPELL:
                    continue
                if suggestion.confidence <= previous.confidence:
                    continue
                deduped[-1] = suggestion
                seen_keys.add(key)
                continue
            deduped.append(suggestion)
            seen_keys.add(key)

        return deduped

    def _overlaps(self, left: Suggestion, right: Suggestion) -> bool:
        return left.span_start < right.span_end and right.span_start < left.span_end

