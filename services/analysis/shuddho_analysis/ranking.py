from __future__ import annotations

from services.feedback.shuddho_feedback.store import FeedbackStore
from ml.ranking.pipeline import NeuralRankerInterface
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionSource


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
                -item.score,
                1 if item.suggestion.source == SuggestionSource.MODEL else 0,
                item.suggestion.span_start,
                item.suggestion.span_end,
                item.suggestion.rule_id,
            )
        )
        return [
            item.suggestion.model_copy(update={"ranking_score": item.score})
            for item in ranked
        ]
