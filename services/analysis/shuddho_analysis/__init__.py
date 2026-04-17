from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = [
    "AnalysisPipeline",
    "CandidateGenerator",
    "DetectorService",
    "SuggestionRankingPipeline",
]


def __getattr__(name: str) -> Any:
    if name == "AnalysisPipeline":
        return import_module(".pipeline", __name__).AnalysisPipeline
    if name == "CandidateGenerator":
        return import_module(".candidate_generator", __name__).CandidateGenerator
    if name == "DetectorService":
        return import_module(".detector", __name__).DetectorService
    if name == "SuggestionRankingPipeline":
        return import_module(".ranking", __name__).SuggestionRankingPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
