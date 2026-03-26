from __future__ import annotations

from dataclasses import dataclass

from shared.schemas.python_models import Suggestion, SuggestionSeverity, SuggestionSource


@dataclass(frozen=True)
class RankedSuggestion:
    suggestion: Suggestion
    score: float


class SuggestionRanker:
    def rank(
        self,
        suggestions: list[Suggestion],
        *,
        text: str = "",
        feedback_index=None,
    ) -> list[RankedSuggestion]:
        raise NotImplementedError


class NeuralRankerInterface(SuggestionRanker):
    def rank(
        self,
        suggestions: list[Suggestion],
        *,
        text: str = "",
        feedback_index=None,
    ) -> list[RankedSuggestion]:
        candidate_support = _count_candidate_support(suggestions)
        exact_span_conflicts = _count_exact_span_conflicts(suggestions)
        overlap_conflicts = _count_partial_overlaps(suggestions)

        return [
            RankedSuggestion(
                suggestion=suggestion,
                score=self._score(
                    suggestion,
                    candidate_support=candidate_support.get(_candidate_group_key(suggestion), 1),
                    exact_span_conflicts=exact_span_conflicts.get(suggestion.id, 0),
                    overlap_conflicts=overlap_conflicts.get(suggestion.id, 0),
                    text=text,
                    feedback_index=feedback_index,
                ),
            )
            for suggestion in suggestions
        ]

    def _score(
        self,
        suggestion: Suggestion,
        *,
        candidate_support: int,
        exact_span_conflicts: int,
        overlap_conflicts: int,
        text: str,
        feedback_index,
    ) -> float:
        source_bonus = {
            SuggestionSource.RULE: 0.1,
            SuggestionSource.HYBRID: 0.13,
            SuggestionSource.SPELL: 0.05,
            SuggestionSource.MODEL: 0.0,
        }[suggestion.source]
        severity_bonus = {
            SuggestionSeverity.HIGH: 0.04,
            SuggestionSeverity.MEDIUM: 0.02,
            SuggestionSeverity.LOW: 0.0,
        }[suggestion.severity]

        replacement_penalty = 0.12 if not suggestion.replacement_options else 0.0
        fusion_bonus = min(max(candidate_support - 1, 0), 2) * 0.04
        exact_conflict_penalty = min(exact_span_conflicts, 3) * 0.05
        overlap_penalty = min(overlap_conflicts, 4) * 0.02

        context_bonus = self._text_context_bonus(suggestion, text=text)
        feedback_bonus = self._feedback_bonus(suggestion, feedback_index)

        score = (
            suggestion.confidence
            + source_bonus
            + severity_bonus
            + fusion_bonus
            + context_bonus
            + feedback_bonus
            - replacement_penalty
            - exact_conflict_penalty
            - overlap_penalty
        )
        return round(max(score, 0.0), 4)

    def _text_context_bonus(self, suggestion: Suggestion, *, text: str) -> float:
        bonus = 0.0
        if suggestion.subtype in {
            "repeated_word",
            "duplicate_punctuation",
            "space_before_punctuation",
            "extra_whitespace",
            "dictionary_variant",
            "safe_exact_typo",
            "detector_spelling",
        }:
            bonus += 0.04

        if suggestion.category.value == "punctuation" and any(character in suggestion.original_text for character in ",.;:!?।"):
            bonus += 0.03
        if suggestion.category.value == "spelling" and len(suggestion.replacement_options) == 1 and len(suggestion.original_text) >= 3:
            bonus += 0.03
        if suggestion.category.value == "grammar" and " " in suggestion.original_text and suggestion.replacement_options:
            bonus += 0.025
        if suggestion.subtype == "extra_whitespace" and suggestion.original_text.strip() == "":
            bonus += 0.02
        if text and "\n" in text and "\n" in suggestion.original_text:
            bonus -= 0.01
        if suggestion.replacement_options:
            bonus += 0.03
            if len(suggestion.replacement_options) == 1:
                bonus += 0.02
            if any(any("\u0980" <= character <= "\u09ff" for character in option) for option in suggestion.replacement_options):
                bonus += 0.03
            if len(suggestion.original_text) <= 12:
                bonus += 0.01
        elif suggestion.source == SuggestionSource.MODEL:
            bonus -= 0.03

        return bonus

    def _feedback_bonus(self, suggestion: Suggestion, feedback_index) -> float:
        if feedback_index is None:
            return 0.0

        exact_stats = feedback_index.by_feedback_key.get(suggestion.feedback_key or "")
        rule_stats = feedback_index.by_rule_id.get(suggestion.rule_id)
        subtype_stats = feedback_index.by_subtype.get(suggestion.subtype)

        bonus = 0.0
        if exact_stats is not None:
            bonus += exact_stats.balance * min(exact_stats.total, 5) / 5 * 0.18
        if rule_stats is not None:
            bonus += rule_stats.balance * min(rule_stats.total, 5) / 5 * 0.08
        if subtype_stats is not None:
            bonus += subtype_stats.balance * min(subtype_stats.total, 5) / 5 * 0.05
        return bonus


def _candidate_group_key(suggestion: Suggestion) -> tuple[int, int, str, tuple[str, ...]]:
    return (
        suggestion.span_start,
        suggestion.span_end,
        suggestion.feedback_key or "",
        tuple(suggestion.replacement_options),
    )


def _count_candidate_support(suggestions: list[Suggestion]) -> dict[tuple[int, int, str, tuple[str, ...]], int]:
    support: dict[tuple[int, int, str, tuple[str, ...]], set[SuggestionSource]] = {}
    for suggestion in suggestions:
        support.setdefault(_candidate_group_key(suggestion), set()).add(suggestion.source)
    return {key: len(sources) for key, sources in support.items()}


def _count_exact_span_conflicts(suggestions: list[Suggestion]) -> dict[str, int]:
    conflicts: dict[str, int] = {suggestion.id: 0 for suggestion in suggestions}
    for index, left in enumerate(suggestions):
        for right in suggestions[index + 1 :]:
            if left.span_start == right.span_start and left.span_end == right.span_end:
                if tuple(left.replacement_options) != tuple(right.replacement_options):
                    conflicts[left.id] += 1
                    conflicts[right.id] += 1
    return conflicts


def _count_partial_overlaps(suggestions: list[Suggestion]) -> dict[str, int]:
    overlaps: dict[str, int] = {suggestion.id: 0 for suggestion in suggestions}
    for index, left in enumerate(suggestions):
        for right in suggestions[index + 1 :]:
            if left.span_start < right.span_end and right.span_start < left.span_end:
                if left.span_start == right.span_start and left.span_end == right.span_end:
                    continue
                overlaps[left.id] += 1
                overlaps[right.id] += 1
    return overlaps
