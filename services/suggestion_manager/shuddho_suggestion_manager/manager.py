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
        fused = self._fuse_consensus_candidates(combined)
        return [ensure_feedback_key(suggestion) for suggestion in fused]

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
            conflict_index = self._find_conflict_index(deduped, suggestion)
            if conflict_index is not None:
                previous = deduped[conflict_index]
                if self._prefer_incoming(previous, suggestion):
                    deduped[conflict_index] = suggestion
                    seen_keys.add(key)
                continue
            deduped.append(suggestion)
            seen_keys.add(key)

        return deduped

    def _fuse_consensus_candidates(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        grouped: dict[tuple[int, int, str, tuple[str, ...]], list[Suggestion]] = {}
        for suggestion in suggestions:
            grouped.setdefault(
                (
                    suggestion.span_start,
                    suggestion.span_end,
                    suggestion.category.value,
                    tuple(suggestion.replacement_options),
                ),
                [],
            ).append(suggestion)

        fused: list[Suggestion] = []
        for group in grouped.values():
            if len(group) == 1:
                fused.append(group[0])
                continue

            best = min(group, key=self._fusion_priority_key)
            sources = {suggestion.source for suggestion in group}
            if len(sources) == 1:
                fused.append(best)
                continue

            explanation_bn = best.explanation_bn
            explanation_en = best.explanation_en
            if best.replacement_options:
                explanation_bn = f"একাধিক সিগন্যাল মিলিয়ে এখানে '{best.replacement_options[0]}' সবচেয়ে কার্যকর সংশোধন।"
                explanation_en = f"Multiple signals agree that '{best.replacement_options[0]}' is the most useful correction here."

            fused.append(
                best.model_copy(
                    update={
                        "source": SuggestionSource.HYBRID,
                        "confidence": min(0.99, round(max(item.confidence for item in group) + 0.04, 2)),
                        "explanation_bn": explanation_bn,
                        "explanation_en": explanation_en,
                    }
                )
            )

        return fused

    def _overlaps(self, left: Suggestion, right: Suggestion) -> bool:
        return left.span_start < right.span_end and right.span_start < left.span_end

    def _should_resolve_overlap(self, left: Suggestion, right: Suggestion) -> bool:
        if not self._overlaps(left, right):
            return False
        if left.category != right.category:
            return False
        if left.span_start == right.span_start and left.span_end == right.span_end:
            return True
        if left.replacement_options == right.replacement_options and self._contains(left, right):
            return True
        if (not left.replacement_options or not right.replacement_options) and self._contains(left, right):
            return True
        return False

    def _find_conflict_index(self, suggestions: list[Suggestion], suggestion: Suggestion) -> int | None:
        for index, existing in enumerate(suggestions):
            if self._should_resolve_overlap(existing, suggestion):
                return index
        return None

    def _prefer_incoming(self, existing: Suggestion, incoming: Suggestion) -> bool:
        if not existing.replacement_options and incoming.replacement_options:
            return True
        if existing.source != SuggestionSource.HYBRID and incoming.source == SuggestionSource.HYBRID:
            return True
        if self._contains(existing, incoming) and not self._contains(incoming, existing):
            return bool(incoming.replacement_options) and incoming.confidence >= existing.confidence - 0.06
        return incoming.confidence > existing.confidence

    def _contains(self, left: Suggestion, right: Suggestion) -> bool:
        return left.span_start <= right.span_start and left.span_end >= right.span_end

    def _fusion_priority_key(self, suggestion: Suggestion) -> tuple[int, int, float]:
        replacement_penalty = 0 if suggestion.replacement_options else 1
        return (
            replacement_penalty,
            SOURCE_PRIORITY[suggestion.source],
            -suggestion.confidence,
        )

    def _assign_response_ids(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        batch_timestamp = int(time.time() * 1000)
        return [
            suggestion.model_copy(update={"id": f"s_{batch_timestamp}_{index}"})
            for index, suggestion in enumerate(suggestions, start=1)
        ]
