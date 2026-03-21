from __future__ import annotations

import time

from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import Suggestion, SuggestionSource
from shared.utils.suggestions import ensure_feedback_key


SOURCE_PRIORITY = {
    SuggestionSource.RULE: 0,
    SuggestionSource.HYBRID: 1,
    SuggestionSource.SPELL: 2,
    SuggestionSource.MODEL: 3
}


class SuggestionManager:
    def prepare_candidates(
        self,
        *,
        original_text: str,
        normalized: NormalizedText,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion],
        detector_suggestions: list[Suggestion] | None = None,
        model_suggestions: list[Suggestion] | None = None,
    ) -> list[Suggestion]:
        mapped_spell = [self._map_to_original(suggestion, original_text, normalized) for suggestion in spell_suggestions]
        combined = list(rule_suggestions)
        if detector_suggestions:
            combined.extend(detector_suggestions)
        if model_suggestions:
            combined.extend(model_suggestions)
        combined.extend(mapped_spell)
        return [ensure_feedback_key(suggestion) for suggestion in combined]

    def finalize_ranked(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        filtered = [suggestion for suggestion in suggestions if self._keep_confident(suggestion)]
        deduped = self._dedupe(filtered)
        deduped.sort(key=self._sort_key)
        return self._assign_response_ids(deduped)

    def merge(
        self,
        original_text: str,
        normalized: NormalizedText,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion],
        detector_suggestions: list[Suggestion] | None = None,
        model_suggestions: list[Suggestion] | None = None,
    ) -> list[Suggestion]:
        prepared = self.prepare_candidates(
            original_text=original_text,
            normalized=normalized,
            spell_suggestions=spell_suggestions,
            rule_suggestions=rule_suggestions,
            detector_suggestions=detector_suggestions,
            model_suggestions=model_suggestions,
        )
        prepared.sort(key=self._sort_key)
        return self.finalize_ranked(prepared)

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
                suggestion.category.value,
                tuple(suggestion.replacement_options)
            )
            if key in seen_keys:
                continue
            if deduped and self._should_resolve_overlap(deduped[-1], suggestion):
                previous = deduped[-1]
                if previous.replacement_options == suggestion.replacement_options:
                    continue
                if previous.source == SuggestionSource.RULE and suggestion.source in {SuggestionSource.SPELL, SuggestionSource.MODEL}:
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

    def _should_resolve_overlap(self, left: Suggestion, right: Suggestion) -> bool:
        if not self._overlaps(left, right):
            return False
        return left.span_start == right.span_start and left.span_end == right.span_end

    def _assign_response_ids(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        batch_timestamp = int(time.time() * 1000)
        return [
            suggestion.model_copy(update={"id": f"s_{batch_timestamp}_{index}"})
            for index, suggestion in enumerate(suggestions, start=1)
        ]
