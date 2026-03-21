from __future__ import annotations

from dataclasses import dataclass, field

from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource


@dataclass(frozen=True)
class DetectorFinding:
    rule_id: str
    category: SuggestionCategory
    subtype: str
    span_start: int
    span_end: int
    original_text: str
    replacement_options: tuple[str, ...] = ()
    confidence: float = 0.0
    explanation_bn: str = ""
    explanation_en: str = ""
    severity: SuggestionSeverity = SuggestionSeverity.LOW
    source: SuggestionSource = SuggestionSource.MODEL


@dataclass
class CandidateBundle:
    spell_suggestions: list[Suggestion] = field(default_factory=list)
    rule_suggestions: list[Suggestion] = field(default_factory=list)
    detector_suggestions: list[Suggestion] = field(default_factory=list)
    model_suggestions: list[Suggestion] = field(default_factory=list)


@dataclass
class AnalysisArtifacts:
    text: str
    normalized: NormalizedText
    rule_suggestions: list[Suggestion]
    detector_findings: list[DetectorFinding]
    spell_suggestions: list[Suggestion]
    candidates: CandidateBundle
    prepared_suggestions: list[Suggestion]
    ranked_suggestions: list[Suggestion]
    merged_suggestions: list[Suggestion]
