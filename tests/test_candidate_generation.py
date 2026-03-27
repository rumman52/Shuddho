from pathlib import Path

from ml.ranking.pipeline import NeuralRankerInterface
from services.analysis.shuddho_analysis.candidate_generator import CandidateGenerator
from services.analysis.shuddho_analysis.models import DetectorFinding
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.spell.shuddho_spell.engine import SpellEngine
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


def test_candidate_generator_turns_detector_spelling_into_actionable_bengali_candidate(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("কিন্তু", "কিন্তু", "fixture.csv", "1", "1", "1"),
        ],
    )
    generator = CandidateGenerator(spell_engine=SpellEngine(runtime_csv_path=runtime_csv_path))

    bundle = generator.generate(
        spell_suggestions=[],
        rule_suggestions=[],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_SPELLING",
                category=SuggestionCategory.SPELLING,
                subtype="detector_spelling",
                span_start=0,
                span_end=5,
                original_text="কিন্ত",
                confidence=0.84,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="কিন্ত",
    )

    assert bundle.detector_suggestions[0].replacement_options == ["কিন্তু"]
    assert bundle.detector_suggestions[0].source == SuggestionSource.HYBRID


def test_candidate_generator_prefers_contextual_spell_support_for_detector_span() -> None:
    generator = CandidateGenerator()

    bundle = generator.generate(
        spell_suggestions=[_suggestion("SPELL_002", SuggestionSource.SPELL, 0.95, "কিন্ত", ["কিন্তু"])],
        rule_suggestions=[],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_SPELLING",
                category=SuggestionCategory.SPELLING,
                subtype="detector_spelling",
                span_start=0,
                span_end=5,
                original_text="কিন্ত",
                confidence=0.83,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="কিন্ত",
    )

    detector_suggestion = bundle.detector_suggestions[0]
    assert detector_suggestion.replacement_options == ["কিন্তু"]
    assert detector_suggestion.source == SuggestionSource.HYBRID
    assert detector_suggestion.confidence > 0.83


def test_candidate_generator_turns_detector_punctuation_into_actionable_fix() -> None:
    generator = CandidateGenerator()

    bundle = generator.generate(
        spell_suggestions=[],
        rule_suggestions=[],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_PUNCTUATION",
                category=SuggestionCategory.PUNCTUATION,
                subtype="detector_punctuation",
                span_start=0,
                span_end=2,
                original_text="।।",
                confidence=0.83,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="সে যায়।।",
    )

    assert bundle.detector_suggestions[0].replacement_options == ["।"]
    assert bundle.detector_suggestions[0].source == SuggestionSource.HYBRID


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
    category = SuggestionCategory.SPELLING if rule_id.startswith("SPELL") or rule_id.startswith("DET_SPELLING") else SuggestionCategory.GRAMMAR
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


def _write_clean_csv_fixture(
    base_dir: Path,
    *,
    rows: list[tuple[str, str, str, str, str, str]],
) -> Path:
    runtime_csv_path = base_dir / "words_clean.csv"
    lines = ["word,normalized_word,source,is_trusted,is_common,is_active"]
    lines.extend(",".join(row) for row in rows)
    runtime_csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_csv_path
