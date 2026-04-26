from __future__ import annotations

from dataclasses import dataclass, field

from services.normalizer.shuddho_normalizer.normalizer import NormalizedText
from shared.schemas.python_models import AnalysisProfile, Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource

from .span_resolution import SentenceSpan


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
    corrector_suggestions: list[Suggestion] = field(default_factory=list)


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
    sentence_spans: list[SentenceSpan] = field(default_factory=list)
    used_detector: bool = False
    used_corrector: bool = False
    backend_warning: str | None = None
    runtime_warnings: list[str] = field(default_factory=list)
    analysis_profile: AnalysisProfile = AnalysisProfile.BACKEND_RULES_AND_SPELL_ONLY
