from ml.ranking.pipeline import NeuralRankerInterface
from services.analysis.shuddho_analysis.candidate_generator import CandidateGenerator
from services.analysis.shuddho_analysis.models import DetectorFinding
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from shared.schemas.python_models import Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource


def test_candidate_generator_combines_rule_spell_detector_and_model_candidates() -> None:
    generator = CandidateGenerator()
    bundle = generator.generate(
        spell_suggestions=[_suggestion("SPELL_002", SuggestionSource.SPELL, 0.96, "কিন্ত", ["কিন্তু"])],
        rule_suggestions=[_suggestion("REP_001", SuggestionSource.RULE, 0.95, "আমি আমি", ["আমি"])],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_GRAMMAR",
                category=SuggestionCategory.GRAMMAR,
                subtype="detector_grammar",
                span_start=0,
                span_end=7,
                original_text="আমি আমি",
                confidence=0.83,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        model_suggestions=[_suggestion("ML_001", SuggestionSource.MODEL, 0.8, "কিন্ত", [])],
    )

    assert len(bundle.rule_suggestions) == 1
    assert len(bundle.spell_suggestions) == 1
    assert len(bundle.detector_suggestions) == 1
    assert len(bundle.model_suggestions) == 1


def test_ranking_pipeline_prefers_conservative_candidates() -> None:
    ranking = SuggestionRankingPipeline(ranker=NeuralRankerInterface())
    ranked = ranking.rank(
        [
            _suggestion("ML_001", SuggestionSource.MODEL, 0.88, "কিন্ত", []),
            _suggestion("SPELL_002", SuggestionSource.SPELL, 0.86, "কিন্ত", ["কিন্তু"]),
            _suggestion("REP_001", SuggestionSource.RULE, 0.8, "আমি আমি", ["আমি"]),
        ],
        text="আমি কিন্ত লিখি",
    )

    assert ranked[0].rule_id in {"SPELL_002", "REP_001"}
    assert {suggestion.rule_id for suggestion in ranked[:2]} == {"SPELL_002", "REP_001"}
    assert ranked[-1].rule_id == "ML_001"


def test_heuristic_ranker_scores_rule_candidates_above_model_candidates() -> None:
    ranker = NeuralRankerInterface()
    ranked = ranker.rank(
        [
            _suggestion("ML_001", SuggestionSource.MODEL, 0.88, "কিন্ত", []),
            _suggestion("REP_001", SuggestionSource.RULE, 0.88, "আমি আমি", ["আমি"]),
        ]
    )

    by_rule_id = {item.suggestion.rule_id: item.score for item in ranked}
    assert by_rule_id["REP_001"] > by_rule_id["ML_001"]


def _suggestion(
    rule_id: str,
    source: SuggestionSource,
    confidence: float,
    original_text: str,
    replacements: list[str],
) -> Suggestion:
    category = SuggestionCategory.SPELLING if rule_id.startswith("SPELL") else SuggestionCategory.GRAMMAR
    return Suggestion(
        id=rule_id.lower(),
        rule_id=rule_id,
        category=category,
        subtype=rule_id.lower(),
        span_start=0,
        span_end=len(original_text),
        original_text=original_text,
        replacement_options=replacements,
        confidence=confidence,
        explanation_bn="",
        explanation_en="",
        source=source,
        severity=SuggestionSeverity.MEDIUM,
    )
