from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionKind, SuggestionSeverity, SuggestionSource


BANGLA_WORD_RE = re.compile(r"[\u0980-\u09FF]{2,}")


@dataclass(frozen=True)
class RankedSuggestion:
    suggestion: Suggestion
    score: float


@dataclass(frozen=True)
class RankingSignals:
    candidate_support: int
    rule_precision_bonus: float
    spell_certainty_bonus: float
    detector_confidence_bonus: float
    contextual_support: float
    ambiguity_penalty: float
    variant_penalty: float
    exact_span_conflicts: int
    overlap_conflicts: int
    feedback_bonus: float


class SuggestionRanker:
    def rank(
        self,
        suggestions: list[Suggestion],
        *,
        text: str = "",
        feedback_index=None,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> list[RankedSuggestion]:
        raise NotImplementedError


class HeuristicContextualReranker:
    def score(self, suggestion: Suggestion, *, signals: RankingSignals, text: str, mode: AnalyzeMode) -> float:
        del text, mode
        source_bonus = {
            SuggestionSource.RULE: 0.08,
            SuggestionSource.HYBRID: 0.15,
            SuggestionSource.SPELL: 0.04,
            SuggestionSource.MODEL: 0.01 if _is_short_localized_contextual_edit(suggestion) else -0.01,
        }[suggestion.source]
        severity_bonus = {
            SuggestionSeverity.HIGH: 0.04,
            SuggestionSeverity.MEDIUM: 0.02,
            SuggestionSeverity.LOW: 0.0,
        }[suggestion.severity]

        replacement_penalty = 0.12 if not suggestion.replacement_options else 0.0
        fusion_bonus = min(max(signals.candidate_support - 1, 0), 3) * 0.04
        exact_conflict_penalty = min(signals.exact_span_conflicts, 3) * 0.05
        overlap_penalty = min(signals.overlap_conflicts, 4) * 0.02

        score = (
            suggestion.confidence
            + source_bonus
            + severity_bonus
            + fusion_bonus
            + signals.rule_precision_bonus
            + signals.spell_certainty_bonus
            + signals.detector_confidence_bonus
            + signals.contextual_support
            + signals.feedback_bonus
            - replacement_penalty
            - signals.ambiguity_penalty
            - signals.variant_penalty
            - exact_conflict_penalty
            - overlap_penalty
        )
        return round(max(score, 0.0), 4)


class ContextualRerankerScaffold:
    def __init__(self, scorer: Callable[[Suggestion, RankingSignals, str, AnalyzeMode], float] | None = None) -> None:
        self.scorer = scorer

    def is_loaded(self) -> bool:
        return self.scorer is not None

    def score(
        self,
        suggestion: Suggestion,
        *,
        signals: RankingSignals,
        text: str,
        mode: AnalyzeMode,
    ) -> float | None:
        if self.scorer is None:
            return None
        return float(self.scorer(suggestion, signals, text, mode))


class NeuralRankerInterface(SuggestionRanker):
    def __init__(
        self,
        *,
        heuristic_reranker: HeuristicContextualReranker | None = None,
        reranker_scaffold: ContextualRerankerScaffold | None = None,
    ) -> None:
        self.heuristic_reranker = heuristic_reranker or HeuristicContextualReranker()
        self.reranker_scaffold = reranker_scaffold or ContextualRerankerScaffold()

    def rank(
        self,
        suggestions: list[Suggestion],
        *,
        text: str = "",
        feedback_index=None,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> list[RankedSuggestion]:
        candidate_support = _count_candidate_support(suggestions)
        exact_span_conflicts = _count_exact_span_conflicts(suggestions)
        overlap_conflicts = _count_partial_overlaps(suggestions)
        rule_precision_bonuses = _rule_precision_bonuses(suggestions)
        spell_certainty_bonuses = _spell_certainty_bonuses(suggestions)
        detector_confidence_bonuses = _detector_confidence_bonuses(suggestions)
        contextual_support = _contextual_support_scores(suggestions, text=text, mode=mode)
        ambiguity_penalties = _ambiguity_penalties(suggestions, mode=mode)
        variant_penalties = _variant_penalties(suggestions, mode=mode)
        feedback_bonuses = _feedback_bonuses(suggestions, feedback_index)

        ranked: list[RankedSuggestion] = []
        for suggestion in suggestions:
            signals = RankingSignals(
                candidate_support=candidate_support.get(_candidate_group_key(suggestion), 1),
                rule_precision_bonus=rule_precision_bonuses.get(suggestion.id, 0.0),
                spell_certainty_bonus=spell_certainty_bonuses.get(suggestion.id, 0.0),
                detector_confidence_bonus=detector_confidence_bonuses.get(suggestion.id, 0.0),
                contextual_support=contextual_support.get(suggestion.id, 0.0),
                ambiguity_penalty=ambiguity_penalties.get(suggestion.id, 0.0),
                variant_penalty=variant_penalties.get(suggestion.id, 0.0),
                exact_span_conflicts=exact_span_conflicts.get(suggestion.id, 0),
                overlap_conflicts=overlap_conflicts.get(suggestion.id, 0),
                feedback_bonus=feedback_bonuses.get(suggestion.id, 0.0),
            )
            scaffold_score = self.reranker_scaffold.score(
                suggestion,
                signals=signals,
                text=text,
                mode=mode,
            )
            score = scaffold_score
            if score is None:
                score = self.heuristic_reranker.score(
                    suggestion,
                    signals=signals,
                    text=text,
                    mode=mode,
                )
            ranked.append(RankedSuggestion(suggestion=suggestion, score=round(score, 4)))

        return ranked


def _candidate_group_key(suggestion: Suggestion) -> tuple[int, int, str, tuple[str, ...]]:
    return (
        suggestion.span_start,
        suggestion.span_end,
        suggestion.feedback_key or "",
        tuple(suggestion.replacement_options),
    )


def _count_candidate_support(suggestions: Sequence[Suggestion]) -> dict[tuple[int, int, str, tuple[str, ...]], int]:
    support: dict[tuple[int, int, str, tuple[str, ...]], set[SuggestionSource]] = {}
    for suggestion in suggestions:
        support.setdefault(_candidate_group_key(suggestion), set()).add(suggestion.source)
    return {key: len(sources) for key, sources in support.items()}


def _count_exact_span_conflicts(suggestions: Sequence[Suggestion]) -> dict[str, int]:
    conflicts: dict[str, int] = {suggestion.id: 0 for suggestion in suggestions}
    for index, left in enumerate(suggestions):
        for right in suggestions[index + 1 :]:
            if left.span_start == right.span_start and left.span_end == right.span_end:
                if tuple(left.replacement_options) != tuple(right.replacement_options):
                    conflicts[left.id] += 1
                    conflicts[right.id] += 1
    return conflicts


def _count_partial_overlaps(suggestions: Sequence[Suggestion]) -> dict[str, int]:
    overlaps: dict[str, int] = {suggestion.id: 0 for suggestion in suggestions}
    for index, left in enumerate(suggestions):
        for right in suggestions[index + 1 :]:
            if left.span_start < right.span_end and right.span_start < left.span_end:
                if left.span_start == right.span_start and left.span_end == right.span_end:
                    continue
                overlaps[left.id] += 1
                overlaps[right.id] += 1
    return overlaps


def _rule_precision_bonuses(suggestions: Sequence[Suggestion]) -> dict[str, float]:
    bonuses: dict[str, float] = {}
    for suggestion in suggestions:
        bonus = 0.0
        if suggestion.source == SuggestionSource.RULE:
            bonus += 0.08
        elif suggestion.source == SuggestionSource.HYBRID:
            bonus += 0.06
        elif suggestion.source == SuggestionSource.SPELL and suggestion.suggestion_kind == SuggestionKind.TRUE_SPELLING_ERROR:
            bonus += 0.04

        if suggestion.suggestion_kind in {
            SuggestionKind.PUNCTUATION_ERROR,
            SuggestionKind.SPACING_ERROR,
        }:
            bonus += 0.03
        elif suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR and suggestion.replacement_options:
            bonus += 0.02
        elif suggestion.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT:
            bonus -= 0.02

        bonuses[suggestion.id] = round(bonus, 4)
    return bonuses


def _spell_certainty_bonuses(suggestions: Sequence[Suggestion]) -> dict[str, float]:
    bonuses: dict[str, float] = {}
    for suggestion in suggestions:
        bonus = 0.0
        if suggestion.suggestion_kind == SuggestionKind.TRUE_SPELLING_ERROR and suggestion.source in {
            SuggestionSource.SPELL,
            SuggestionSource.HYBRID,
        }:
            bonus += 0.04
            if len(suggestion.replacement_options) == 1:
                bonus += 0.03
            if suggestion.confidence >= 0.98:
                bonus += 0.03
        if suggestion.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT:
            bonus -= 0.02
        bonuses[suggestion.id] = round(bonus, 4)
    return bonuses


def _detector_confidence_bonuses(suggestions: Sequence[Suggestion]) -> dict[str, float]:
    bonuses: dict[str, float] = {}
    for suggestion in suggestions:
        bonus = 0.0
        if suggestion.source in {SuggestionSource.MODEL, SuggestionSource.HYBRID}:
            if suggestion.is_contextual:
                bonus += 0.04
            if suggestion.confidence >= 0.9:
                bonus += 0.03
            if _is_short_localized_contextual_edit(suggestion):
                bonus += 0.03
            if not suggestion.replacement_options:
                bonus -= 0.04
        bonuses[suggestion.id] = round(bonus, 4)
    return bonuses


def _contextual_support_scores(
    suggestions: Sequence[Suggestion],
    *,
    text: str,
    mode: AnalyzeMode,
) -> dict[str, float]:
    support_scores: dict[str, float] = {}
    for suggestion in suggestions:
        bonus = 0.0
        if suggestion.is_contextual:
            bonus += 0.05
        if suggestion.suggestion_kind in {
            SuggestionKind.GRAMMAR_ERROR,
            SuggestionKind.PUNCTUATION_ERROR,
            SuggestionKind.SPACING_ERROR,
        }:
            bonus += 0.03
            if mode == AnalyzeMode.STANDARD and len(suggestion.replacement_options) == 1:
                bonus += 0.02
        if suggestion.suggestion_kind == SuggestionKind.TRUE_SPELLING_ERROR and len(suggestion.replacement_options) == 1:
            bonus += 0.04
        if suggestion.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT:
            bonus += 0.01 if mode == AnalyzeMode.FORMAL else 0.0

        if suggestion.category.value == "spelling" and BANGLA_WORD_RE.fullmatch(suggestion.original_text or ""):
            bonus += 0.02
        if suggestion.replacement_options:
            bonus += 0.02
            if len(suggestion.replacement_options) == 1:
                bonus += 0.02
            if any(any("\u0980" <= character <= "\u09ff" for character in option) for option in suggestion.replacement_options):
                bonus += 0.02
        elif suggestion.source == SuggestionSource.MODEL:
            bonus -= 0.04

        if text and "\n" in text and "\n" in suggestion.original_text:
            bonus -= 0.01

        if _has_nearby_supporting_candidate(suggestion, suggestions):
            bonus += 0.03

        support_scores[suggestion.id] = round(bonus, 4)
    return support_scores


def _has_nearby_supporting_candidate(target: Suggestion, suggestions: Sequence[Suggestion]) -> bool:
    target_replacements = tuple(target.replacement_options)
    if not target_replacements:
        return False

    for suggestion in suggestions:
        if suggestion.id == target.id:
            continue
        if tuple(suggestion.replacement_options) != target_replacements:
            continue
        if target.span_start < suggestion.span_end and suggestion.span_start < target.span_end:
            return True
        if abs(target.span_start - suggestion.span_start) <= 2 and abs(target.span_end - suggestion.span_end) <= 2:
            return True
    return False


def _ambiguity_penalties(suggestions: Sequence[Suggestion], *, mode: AnalyzeMode) -> dict[str, float]:
    penalties: dict[str, float] = {}
    for suggestion in suggestions:
        penalty = 0.0
        if len(suggestion.replacement_options) > 1:
            penalty += min(len(suggestion.replacement_options) - 1, 3) * 0.05
        if suggestion.source == SuggestionSource.MODEL and not suggestion.replacement_options:
            penalty += 0.08
        if suggestion.source == SuggestionSource.MODEL and len(suggestion.replacement_options) > 1:
            penalty += 0.04
        if suggestion.category.value == "spelling" and _has_same_span_competing_replacement(suggestion, suggestions):
            penalty += 0.05
        if suggestion.suggestion_kind == SuggestionKind.NO_SUGGESTION:
            penalty += 0.1
        if suggestion.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT and mode == AnalyzeMode.STANDARD:
            penalty += 0.04
        if (
            mode == AnalyzeMode.STANDARD
            and suggestion.is_contextual
            and suggestion.suggestion_kind in {
                SuggestionKind.GRAMMAR_ERROR,
                SuggestionKind.PUNCTUATION_ERROR,
                SuggestionKind.SPACING_ERROR,
            }
            and len(suggestion.replacement_options) == 1
        ):
            penalty = max(0.0, penalty - 0.03)
        penalties[suggestion.id] = round(penalty, 4)
    return penalties


def _variant_penalties(suggestions: Sequence[Suggestion], *, mode: AnalyzeMode) -> dict[str, float]:
    penalties: dict[str, float] = {}
    for suggestion in suggestions:
        penalty = 0.0
        if suggestion.suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT:
            penalty += {
                AnalyzeMode.STANDARD: 0.16,
                AnalyzeMode.STRICT: 0.05,
                AnalyzeMode.FORMAL: 0.0,
            }[mode]
        elif suggestion.suggestion_kind == SuggestionKind.STYLE_SUGGESTION:
            penalty += {
                AnalyzeMode.STANDARD: 0.08,
                AnalyzeMode.STRICT: 0.03,
                AnalyzeMode.FORMAL: 0.0,
            }[mode]

        if suggestion.is_variant_only and mode != AnalyzeMode.FORMAL:
            penalty += 0.02
        penalties[suggestion.id] = round(penalty, 4)
    return penalties


def _has_same_span_competing_replacement(target: Suggestion, suggestions: Sequence[Suggestion]) -> bool:
    for suggestion in suggestions:
        if suggestion.id == target.id:
            continue
        if suggestion.span_start != target.span_start or suggestion.span_end != target.span_end:
            continue
        if tuple(suggestion.replacement_options) != tuple(target.replacement_options):
            return True
    return False


def _feedback_bonuses(suggestions: Sequence[Suggestion], feedback_index) -> dict[str, float]:
    if feedback_index is None:
        return {suggestion.id: 0.0 for suggestion in suggestions}

    bonuses: dict[str, float] = {}
    for suggestion in suggestions:
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
        bonuses[suggestion.id] = round(bonus, 4)
    return bonuses


def _has_short_bengali_replacement(suggestion: Suggestion) -> bool:
    if len(suggestion.replacement_options) != 1:
        return False
    replacement = suggestion.replacement_options[0]
    if not replacement or len(replacement) > max(len(suggestion.original_text) * 2, 24):
        return False
    return any("\u0980" <= character <= "\u09ff" for character in replacement)


def _is_short_localized_contextual_edit(suggestion: Suggestion) -> bool:
    if suggestion.suggestion_kind not in {
        SuggestionKind.GRAMMAR_ERROR,
        SuggestionKind.PUNCTUATION_ERROR,
        SuggestionKind.SPACING_ERROR,
    }:
        return False
    return _has_short_bengali_replacement(suggestion)
