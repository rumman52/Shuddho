from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations, permutations

from shared.schemas.python_models import Suggestion, SuggestionAlternative, SuggestionKind, SuggestionSource
from shared.utils.text import stable_id


MAX_COMPOSITE_CLUSTER_SIZE = 5
MULTISPACE_PATTERN = re.compile(r"[^\S\r\n]{2,}")
SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"\s+([,.;:!?।])")
DUPLICATE_PUNCTUATION_PATTERN = re.compile(r"([,.;:!?।])\1+")
REPEATED_WORD_PATTERN = re.compile(r"(?<![\u0980-\u09FFA-Za-z])([\u0980-\u09FF]{2,})\s+\1(?![\u0980-\u09FFA-Za-z])")


@dataclass(frozen=True)
class EditCandidate:
    start: int
    end: int
    replacement: str
    score: float


def resolve_same_span_conflicts(suggestions: Sequence[Suggestion]) -> list[Suggestion]:
    if not suggestions:
        return []

    grouped: dict[tuple[int, int], list[tuple[int, Suggestion]]] = defaultdict(list)
    for index, suggestion in enumerate(suggestions):
        grouped[(suggestion.span_start, suggestion.span_end)].append((index, suggestion))

    resolved: list[tuple[int, Suggestion]] = []
    for (span_start, span_end), indexed_group in grouped.items():
        ordered_group = [
            suggestion
            for _, suggestion in sorted(
                indexed_group,
                key=lambda item: (_same_span_priority_key(item[1]), item[0]),
            )
        ]
        primary = ordered_group[0]
        primary_replacements = tuple(primary.replacement_options)
        alternatives: list[SuggestionAlternative] = []
        seen_alternatives: set[tuple[str, ...]] = {primary_replacements}

        for alternative in ordered_group[1:]:
            alternative_key = tuple(alternative.replacement_options)
            if alternative_key in seen_alternatives:
                continue
            seen_alternatives.add(alternative_key)
            alternatives.append(_to_alternative(alternative))

        resolved.append(
            (
                min(index for index, _ in indexed_group),
                primary.model_copy(
                    update={
                        "conflict_group_id": stable_id("conflict", f"{span_start}:{span_end}:{primary.original_text}"),
                        "is_primary": True,
                        "primary_reason": _primary_reason(primary, ordered_group) if alternatives else None,
                        "alternatives": alternatives,
                    }
                ),
            )
        )

    return [suggestion for _, suggestion in sorted(resolved, key=lambda item: item[0])]


def build_best_corrected_text(
    text: str,
    suggestions: Sequence[Suggestion],
    *,
    is_safe_auto_apply_suggestion: Callable[[str, Suggestion], bool],
) -> str:
    safe_suggestions = sorted(
        (
            suggestion
            for suggestion in suggestions
            if suggestion.is_primary and is_safe_auto_apply_suggestion(text, suggestion)
        ),
        key=lambda suggestion: (suggestion.span_start, suggestion.span_end, suggestion.rule_id),
    )
    if not safe_suggestions:
        return text

    candidates = _build_edit_candidates(text, safe_suggestions)
    if not candidates:
        return text

    selected = _weighted_interval_selection(candidates)
    if not selected:
        return text

    parts: list[str] = []
    cursor = 0
    for candidate in sorted(selected, key=lambda item: (item.start, item.end)):
        if candidate.start < cursor:
            continue
        parts.append(text[cursor:candidate.start])
        parts.append(candidate.replacement)
        cursor = candidate.end

    parts.append(text[cursor:])
    corrected_text = "".join(parts)
    return corrected_text if corrected_text else text


def _build_edit_candidates(text: str, suggestions: Sequence[Suggestion]) -> list[EditCandidate]:
    candidates: dict[tuple[int, int, str], EditCandidate] = {}

    for suggestion in suggestions:
        replacement = suggestion.replacement_options[0]
        candidate = EditCandidate(
            start=suggestion.span_start,
            end=suggestion.span_end,
            replacement=replacement,
            score=_safe_edit_weight(suggestion),
        )
        candidates[(candidate.start, candidate.end, candidate.replacement)] = candidate

    for cluster in _overlap_clusters(suggestions):
        if len(cluster) <= 1 or len(cluster) > MAX_COMPOSITE_CLUSTER_SIZE:
            continue
        for candidate in _composite_candidates_for_cluster(text, cluster):
            key = (candidate.start, candidate.end, candidate.replacement)
            existing = candidates.get(key)
            if existing is None or candidate.score > existing.score:
                candidates[key] = candidate

    return sorted(candidates.values(), key=lambda candidate: (candidate.end, candidate.start, -candidate.score))


def _overlap_clusters(suggestions: Sequence[Suggestion]) -> list[list[Suggestion]]:
    clusters: list[list[Suggestion]] = []
    current: list[Suggestion] = []
    current_end = -1

    for suggestion in sorted(suggestions, key=lambda item: (item.span_start, item.span_end)):
        if not current or suggestion.span_start >= current_end:
            if current:
                clusters.append(current)
            current = [suggestion]
            current_end = suggestion.span_end
            continue

        current.append(suggestion)
        current_end = max(current_end, suggestion.span_end)

    if current:
        clusters.append(current)

    return clusters


def _composite_candidates_for_cluster(text: str, cluster: Sequence[Suggestion]) -> Iterable[EditCandidate]:
    cluster_start = min(suggestion.span_start for suggestion in cluster)
    cluster_end = max(suggestion.span_end for suggestion in cluster)
    cluster_text = text[cluster_start:cluster_end]
    generated: dict[str, EditCandidate] = {}

    for subset_size in range(2, len(cluster) + 1):
        for subset in combinations(cluster, subset_size):
            if not _subset_contains_overlap(subset):
                continue
            for replacement in _compose_subset(cluster_text, cluster_start, subset):
                if replacement == cluster_text:
                    continue
                score = sum(_safe_edit_weight(suggestion) for suggestion in subset)
                score += _cleanup_bonus(cluster_text, replacement)
                candidate = EditCandidate(
                    start=cluster_start,
                    end=cluster_end,
                    replacement=replacement,
                    score=round(score, 4),
                )
                existing = generated.get(replacement)
                if existing is None or candidate.score > existing.score:
                    generated[replacement] = candidate

    return generated.values()


def _compose_subset(cluster_text: str, cluster_start: int, subset: Sequence[Suggestion]) -> set[str]:
    composed: set[str] = set()
    for ordering in permutations(subset):
        candidate = _apply_order(cluster_text, cluster_start, ordering)
        if candidate is not None:
            composed.add(candidate)
    return composed


def _apply_order(cluster_text: str, cluster_start: int, ordering: Sequence[Suggestion]) -> str | None:
    current = cluster_text
    prior_edits: list[tuple[int, int, int]] = []

    for suggestion in ordering:
        needle = suggestion.original_text
        replacement = suggestion.replacement_options[0]
        if not needle:
            return None

        expected_index = _expected_current_index(suggestion, cluster_start, prior_edits)
        occurrences = _find_occurrences(current, needle)
        if not occurrences:
            return None

        selected_index = min(occurrences, key=lambda occurrence: (abs(occurrence - expected_index), occurrence))
        current = f"{current[:selected_index]}{replacement}{current[selected_index + len(needle):]}"
        prior_edits.append(
            (
                suggestion.span_start - cluster_start,
                suggestion.span_end - cluster_start,
                len(replacement) - len(needle),
            )
        )

    return current


def _expected_current_index(
    suggestion: Suggestion,
    cluster_start: int,
    prior_edits: Sequence[tuple[int, int, int]],
) -> int:
    relative_start = suggestion.span_start - cluster_start
    shift = sum(delta for start, end, delta in prior_edits if end <= relative_start)
    return max(relative_start + shift, 0)


def _find_occurrences(text: str, needle: str) -> list[int]:
    occurrences: list[int] = []
    cursor = 0
    while True:
        index = text.find(needle, cursor)
        if index < 0:
            break
        occurrences.append(index)
        cursor = index + 1
    return occurrences


def _weighted_interval_selection(candidates: Sequence[EditCandidate]) -> list[EditCandidate]:
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda candidate: (candidate.end, candidate.start, -candidate.score))
    predecessors = [_predecessor_index(ordered, index) for index in range(len(ordered))]
    best_scores = [0.0] * (len(ordered) + 1)
    take = [False] * len(ordered)

    for index, candidate in enumerate(ordered, start=1):
        include_score = candidate.score + best_scores[predecessors[index - 1] + 1]
        exclude_score = best_scores[index - 1]
        if include_score > exclude_score:
            best_scores[index] = include_score
            take[index - 1] = True
        else:
            best_scores[index] = exclude_score

    selected: list[EditCandidate] = []
    index = len(ordered)
    while index > 0:
        candidate = ordered[index - 1]
        predecessor = predecessors[index - 1]
        include_score = candidate.score + best_scores[predecessor + 1]
        if take[index - 1] and include_score >= best_scores[index - 1]:
            selected.append(candidate)
            index = predecessor + 1
        else:
            index -= 1

    selected.reverse()
    return selected


def _predecessor_index(candidates: Sequence[EditCandidate], index: int) -> int:
    candidate = candidates[index]
    left = 0
    right = index - 1
    result = -1

    while left <= right:
        middle = (left + right) // 2
        if candidates[middle].end <= candidate.start:
            result = middle
            left = middle + 1
        else:
            right = middle - 1

    return result


def _cleanup_bonus(original_text: str, replacement: str) -> float:
    before = _local_error_count(original_text)
    after = _local_error_count(replacement)
    return round((before - after) * 0.12, 4)


def _local_error_count(text: str) -> int:
    return sum(
        len(pattern.findall(text))
        for pattern in (
            MULTISPACE_PATTERN,
            SPACE_BEFORE_PUNCTUATION_PATTERN,
            DUPLICATE_PUNCTUATION_PATTERN,
            REPEATED_WORD_PATTERN,
        )
    )


def _subset_contains_overlap(suggestions: Sequence[Suggestion]) -> bool:
    for index, left in enumerate(suggestions):
        for right in suggestions[index + 1 :]:
            if left.span_start < right.span_end and right.span_start < left.span_end:
                return True
    return False


def _safe_edit_weight(suggestion: Suggestion) -> float:
    kind = suggestion.suggestion_kind or SuggestionKind.NO_SUGGESTION
    kind_bonus = {
        SuggestionKind.GRAMMAR_ERROR: 1.18,
        SuggestionKind.PUNCTUATION_ERROR: 1.1,
        SuggestionKind.SPACING_ERROR: 1.1,
        SuggestionKind.TRUE_SPELLING_ERROR: 1.0,
        SuggestionKind.ORTHOGRAPHY_VARIANT: 0.6,
        SuggestionKind.STYLE_SUGGESTION: 0.4,
        SuggestionKind.NAMED_ENTITY_OR_USER_WORD: 0.2,
        SuggestionKind.NO_SUGGESTION: 0.2,
    }[kind]
    source_bonus = {
        SuggestionSource.HYBRID: 0.08,
        SuggestionSource.RULE: 0.06,
        SuggestionSource.SPELL: 0.04,
        SuggestionSource.MODEL: 0.0,
    }[suggestion.source]
    contextual_bonus = 0.04 if suggestion.is_contextual else 0.0
    return round(kind_bonus + source_bonus + contextual_bonus + suggestion.confidence, 4)


def _same_span_priority_key(suggestion: Suggestion) -> tuple[int, int, int, int, float, str]:
    kind = suggestion.suggestion_kind or SuggestionKind.NO_SUGGESTION
    kind_rank = {
        SuggestionKind.GRAMMAR_ERROR: 0,
        SuggestionKind.PUNCTUATION_ERROR: 1,
        SuggestionKind.SPACING_ERROR: 1,
        SuggestionKind.TRUE_SPELLING_ERROR: 2,
        SuggestionKind.ORTHOGRAPHY_VARIANT: 3,
        SuggestionKind.STYLE_SUGGESTION: 4,
        SuggestionKind.NAMED_ENTITY_OR_USER_WORD: 5,
        SuggestionKind.NO_SUGGESTION: 6,
    }[kind]
    source_rank = {
        SuggestionSource.HYBRID: 0,
        SuggestionSource.RULE: 1,
        SuggestionSource.SPELL: 2,
        SuggestionSource.MODEL: 3,
    }[suggestion.source]
    return (
        kind_rank,
        0 if suggestion.replacement_options else 1,
        0 if suggestion.is_contextual else 1,
        source_rank,
        -suggestion.confidence,
        suggestion.rule_id,
    )


def _primary_reason(primary: Suggestion, group: Sequence[Suggestion]) -> str | None:
    if len(group) <= 1:
        return None

    competing_kinds = {suggestion.suggestion_kind for suggestion in group[1:]}
    if primary.suggestion_kind == SuggestionKind.GRAMMAR_ERROR and competing_kinds & {
        SuggestionKind.TRUE_SPELLING_ERROR,
        SuggestionKind.ORTHOGRAPHY_VARIANT,
    }:
        return "Context here supports the agreement fix, so spelling-only variants stay as alternatives."
    if primary.suggestion_kind in {SuggestionKind.PUNCTUATION_ERROR, SuggestionKind.SPACING_ERROR}:
        return "This localized punctuation fix is the cleanest primary correction for this span."
    if primary.suggestion_kind == SuggestionKind.TRUE_SPELLING_ERROR and SuggestionKind.ORTHOGRAPHY_VARIANT in competing_kinds:
        return "The dictionary-backed spelling fix is stronger here than the orthography-only variant."
    return "This is the strongest localized correction for this exact span."


def _to_alternative(suggestion: Suggestion) -> SuggestionAlternative:
    return SuggestionAlternative(
        id=suggestion.id,
        rule_id=suggestion.rule_id,
        category=suggestion.category,
        subtype=suggestion.subtype,
        original_text=suggestion.original_text,
        replacement_options=list(suggestion.replacement_options),
        confidence=suggestion.confidence,
        explanation_bn=suggestion.explanation_bn,
        explanation_en=suggestion.explanation_en,
        source=suggestion.source,
        severity=suggestion.severity,
        feedback_key=suggestion.feedback_key,
        suggestion_kind=suggestion.suggestion_kind,
        suppression_key=suggestion.suppression_key,
        is_variant_only=suggestion.is_variant_only,
        source_trace=list(suggestion.source_trace or []),
    )
