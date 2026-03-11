from __future__ import annotations

from dataclasses import dataclass

from shared.schemas.python_models import Suggestion


@dataclass
class RankedSuggestion:
    suggestion: Suggestion
    score: float


class NeuralRankerInterface:
    def rank(self, suggestions: list[Suggestion]) -> list[RankedSuggestion]:
        return [RankedSuggestion(suggestion=suggestion, score=suggestion.confidence) for suggestion in suggestions]

