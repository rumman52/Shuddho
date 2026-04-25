from __future__ import annotations

from services.feedback.shuddho_feedback.store import FeedbackStore
from ml.ranking.pipeline import NeuralRankerInterface
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionKind, SuggestionSource


class SuggestionRankingPipeline:
    def __init__(
        self,
        ranker: NeuralRankerInterface | None = None,
        *,
        feedback_store: FeedbackStore | None = None,
    ) -> None:
        self.ranker = ranker or NeuralRankerInterface()
        self.feedback_store = feedback_store

    def rank(
        self,
        suggestions: list[Suggestion],
        *,
        text: str,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> list[Suggestion]:
        feedback_index = self.feedback_store.load_signal_index(suggestions) if self.feedback_store is not None else None
        ranked = self.ranker.rank(
            list(suggestions),
            text=text,
            feedback_index=feedback_index,
            mode=mode,
        )
        ranked.sort(
            key=lambda item: (
                _actionability_sort_bucket(item.suggestion),
                -item.score,
                _conservative_sort_bucket(item.suggestion),
                item.suggestion.span_start,
                item.suggestion.span_end,
                item.suggestion.rule_id,
            )
        )
        return [
            item.suggestion.model_copy(update={"ranking_score": item.score})
            for item in ranked
        ]


def _actionability_sort_bucket(suggestion: Suggestion) -> int:
    return 0 if suggestion.replacement_options else 1


def _conservative_sort_bucket(suggestion: Suggestion) -> tuple[int, int]:
    kind_rank = {
        SuggestionKind.GRAMMAR_ERROR: 0,
        SuggestionKind.PUNCTUATION_ERROR: 1,
        SuggestionKind.SPACING_ERROR: 1,
        SuggestionKind.TRUE_SPELLING_ERROR: 2,
        SuggestionKind.ORTHOGRAPHY_VARIANT: 3,
        SuggestionKind.STYLE_SUGGESTION: 4,
        SuggestionKind.NAMED_ENTITY_OR_USER_WORD: 5,
        SuggestionKind.NO_SUGGESTION: 6,
        None: 6,
    }[suggestion.suggestion_kind]
    source_rank = {
        SuggestionSource.RULE: 0,
        SuggestionSource.SPELL: 1,
        SuggestionSource.HYBRID: 1,
        SuggestionSource.MODEL: 2,
    }[suggestion.source]
    return kind_rank, source_rank
