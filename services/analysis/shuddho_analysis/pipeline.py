from __future__ import annotations

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, AnalyzeResponse, Suggestion, SuggestionCategory, SuggestionSeverity

from .candidate_generator import CandidateGenerator
from .detector import DetectorService
from .models import AnalysisArtifacts
from .ranking import SuggestionRankingPipeline


class AnalysisPipeline:
    def __init__(
        self,
        *,
        normalizer: BanglaNormalizer,
        spell_engine: SpellEngine,
        rule_engine: RuleEngine,
        suggestion_manager: SuggestionManager,
        detector_service: DetectorService | None = None,
        candidate_generator: CandidateGenerator | None = None,
        ranking_pipeline: SuggestionRankingPipeline | None = None,
    ) -> None:
        self.normalizer = normalizer
        self.spell_engine = spell_engine
        self.rule_engine = rule_engine
        self.suggestion_manager = suggestion_manager
        self.detector_service = detector_service or DetectorService()
        self.candidate_generator = candidate_generator or CandidateGenerator(spell_engine=spell_engine)
        if getattr(self.candidate_generator, "spell_engine", None) is None:
            self.candidate_generator.spell_engine = spell_engine
        self.ranking_pipeline = ranking_pipeline or SuggestionRankingPipeline()

    def analyze(
        self,
        text: str,
        personal_dictionary: list[str] | None = None,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> AnalyzeResponse:
        artifacts = self.analyze_artifacts(text, personal_dictionary, mode=mode)
        return AnalyzeResponse(
            text=text,
            normalized_text=artifacts.normalized.text,
            suggestions=artifacts.merged_suggestions,
        )

    def analyze_artifacts(
        self,
        text: str,
        personal_dictionary: list[str] | None = None,
        *,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> AnalysisArtifacts:
        normalized = self.normalizer.normalize(text)
        rule_suggestions = self.rule_engine.analyze(text)
        spell_suggestions = self.spell_engine.analyze(normalized.text, personal_dictionary)
        detector_findings = self.detector_service.detect(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
            spell_suggestions=spell_suggestions,
        )
        candidates = self.candidate_generator.generate(
            spell_suggestions=spell_suggestions,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            model_suggestions=[],
            text=text,
        )
        prepared_suggestions = self.suggestion_manager.prepare_candidates(
            original_text=text,
            normalized=normalized,
            spell_suggestions=candidates.spell_suggestions,
            rule_suggestions=candidates.rule_suggestions,
            detector_suggestions=candidates.detector_suggestions,
            model_suggestions=candidates.model_suggestions,
        )
        ranked_suggestions = self.ranking_pipeline.rank(prepared_suggestions, text=text)
        merged_suggestions = _apply_request_mode(
            self.suggestion_manager.finalize_ranked(ranked_suggestions),
            mode=mode,
        )
        return AnalysisArtifacts(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            spell_suggestions=spell_suggestions,
            candidates=candidates,
            prepared_suggestions=prepared_suggestions,
            ranked_suggestions=ranked_suggestions,
            merged_suggestions=merged_suggestions,
        )


def _apply_request_mode(suggestions: list[Suggestion], *, mode: AnalyzeMode) -> list[Suggestion]:
    if mode == AnalyzeMode.STRICT:
        return list(suggestions)

    hard_suggestions = [suggestion for suggestion in suggestions if suggestion.category != SuggestionCategory.STYLE]
    style_suggestions = [suggestion for suggestion in suggestions if suggestion.category == SuggestionCategory.STYLE]

    if mode == AnalyzeMode.STANDARD:
        style_suggestions = [suggestion for suggestion in style_suggestions if _keep_standard_style_suggestion(suggestion)]
    else:
        style_suggestions = sorted(style_suggestions, key=_formal_style_sort_key)

    return [*hard_suggestions, *style_suggestions]


def _keep_standard_style_suggestion(suggestion: Suggestion) -> bool:
    if suggestion.severity != SuggestionSeverity.LOW:
        return True
    return bool(suggestion.replacement_options) and suggestion.confidence >= 0.8


def _formal_style_sort_key(suggestion: Suggestion) -> tuple[int, int, float, int]:
    return (
        0 if suggestion.replacement_options else 1,
        0 if suggestion.severity != SuggestionSeverity.LOW else 1,
        -suggestion.confidence,
        suggestion.span_start,
    )
