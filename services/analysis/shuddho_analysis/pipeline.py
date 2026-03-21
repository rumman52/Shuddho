from __future__ import annotations

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeResponse

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
        self.candidate_generator = candidate_generator or CandidateGenerator()
        self.ranking_pipeline = ranking_pipeline or SuggestionRankingPipeline()

    def analyze(self, text: str, personal_dictionary: list[str] | None = None) -> AnalyzeResponse:
        artifacts = self.analyze_artifacts(text, personal_dictionary)
        return AnalyzeResponse(
            text=text,
            normalized_text=artifacts.normalized.text,
            suggestions=artifacts.merged_suggestions,
        )

    def analyze_artifacts(self, text: str, personal_dictionary: list[str] | None = None) -> AnalysisArtifacts:
        normalized = self.normalizer.normalize(text)
        rule_suggestions = self.rule_engine.analyze(text)
        detector_findings = self.detector_service.detect(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
        )
        spell_suggestions = self.spell_engine.analyze(normalized.text, personal_dictionary)
        candidates = self.candidate_generator.generate(
            spell_suggestions=spell_suggestions,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            model_suggestions=[],
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
        merged_suggestions = self.suggestion_manager.finalize_ranked(ranked_suggestions)
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
