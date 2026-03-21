from __future__ import annotations

from services.feedback.shuddho_feedback.store import FeedbackStore
from ml.ranking.pipeline import NeuralRankerInterface
from shared.schemas.python_models import Suggestion


class SuggestionRankingPipeline:
    def __init__(
        self,
        ranker: NeuralRankerInterface | None = None,
        *,
        feedback_store: FeedbackStore | None = None,
    ) -> None:
        self.ranker = ranker or NeuralRankerInterface()
        self.feedback_store = feedback_store

    def rank(self, suggestions: list[Suggestion], *, text: str) -> list[Suggestion]:
        feedback_index = self.feedback_store.load_signal_index(suggestions) if self.feedback_store is not None else None
        ranked = self.ranker.rank(list(suggestions), text=text, feedback_index=feedback_index)
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.suggestion.span_start,
                item.suggestion.span_end,
                item.suggestion.rule_id,
            )
        )
        return [item.suggestion for item in ranked]
