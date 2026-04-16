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
        spell_suggestions=[_suggestion("SPELL_002", SuggestionSource.SPELL, 0.96, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"])],
        rule_suggestions=[_suggestion("REP_001", SuggestionSource.RULE, 0.95, "\u0986\u09ae\u09bf \u0986\u09ae\u09bf", ["\u0986\u09ae\u09bf"])],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_GRAMMAR",
                category=SuggestionCategory.GRAMMAR,
                subtype="detector_grammar",
                span_start=0,
                span_end=7,
                original_text="\u0986\u09ae\u09bf \u0986\u09ae\u09bf",
                confidence=0.83,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        model_suggestions=[_suggestion("ML_001", SuggestionSource.MODEL, 0.9, "\u0986\u09ae\u09bf \u0986\u09ae\u09bf", ["\u0986\u09ae\u09bf"])],
    )

    assert len(bundle.rule_suggestions) == 1
    assert len(bundle.spell_suggestions) == 1
    assert len(bundle.detector_suggestions) == 1
    assert len(bundle.model_suggestions) == 1


def test_candidate_generator_drops_unsafe_model_candidates() -> None:
    generator = CandidateGenerator()

    bundle = generator.generate(
        spell_suggestions=[],
        rule_suggestions=[],
        detector_findings=[],
        model_suggestions=[
            _suggestion("ML_001", SuggestionSource.MODEL, 0.79, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]),
            _suggestion("ML_002", SuggestionSource.MODEL, 0.9, "\u0995\u09bf\u09a8\u09cd\u09a4", []),
        ],
    )

    assert bundle.model_suggestions == []


def test_candidate_generator_turns_detector_spelling_into_actionable_bengali_candidate_when_direct_spell_mapping_exists(
    tmp_path: Path,
) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df", "\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc", "fixture.csv", "1", "0", "1"),
            ("\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc", "\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc", "fixture.csv", "1", "1", "1"),
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
                span_end=9,
                original_text="\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df",
                confidence=0.9,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df",
    )

    assert bundle.detector_suggestions[0].replacement_options == ["\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc"]
    assert bundle.detector_suggestions[0].source == SuggestionSource.HYBRID


def test_candidate_generator_drops_detector_spelling_when_no_safe_replacement_exists(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u09b0\u09be\u09b9\u09c1\u09b2", "\u09b0\u09be\u09b9\u09c1\u09b2", "fixture.csv", "1", "1", "1"),
        ],
    )
    generator = CandidateGenerator(spell_engine=SpellEngine(runtime_csv_path=runtime_csv_path))
    generator.spell_engine.generate_candidates = lambda token: []  # type: ignore[method-assign]

    bundle = generator.generate(
        spell_suggestions=[],
        rule_suggestions=[],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_SPELLING",
                category=SuggestionCategory.SPELLING,
                subtype="detector_spelling",
                span_start=0,
                span_end=6,
                original_text="\u09b0\u09be\u09b9\u09c1\u09b2\u09b2",
                confidence=0.84,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="\u09b0\u09be\u09b9\u09c1\u09b2\u09b2",
    )

    assert bundle.detector_suggestions == []


def test_candidate_generator_prefers_contextual_spell_support_for_detector_span() -> None:
    generator = CandidateGenerator()

    bundle = generator.generate(
        spell_suggestions=[_suggestion("SPELL_002", SuggestionSource.SPELL, 0.95, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"])],
        rule_suggestions=[],
        detector_findings=[
            DetectorFinding(
                rule_id="DET_SPELLING",
                category=SuggestionCategory.SPELLING,
                subtype="detector_spelling",
                span_start=0,
                span_end=5,
                original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
                confidence=0.83,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="\u0995\u09bf\u09a8\u09cd\u09a4",
    )

    detector_suggestion = bundle.detector_suggestions[0]
    assert detector_suggestion.replacement_options == ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]
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
                original_text="\u0964\u0964",
                confidence=0.83,
                explanation_bn="",
                explanation_en="",
                source=SuggestionSource.MODEL,
            )
        ],
        text="\u09b8\u09c7 \u09af\u09be\u09df\u0964\u0964",
    )

    assert bundle.detector_suggestions[0].replacement_options == ["\u0964"]
    assert bundle.detector_suggestions[0].source == SuggestionSource.HYBRID


def test_ranking_pipeline_prefers_conservative_candidates() -> None:
    ranking = SuggestionRankingPipeline(ranker=NeuralRankerInterface())
    ranked = ranking.rank(
        [
            _suggestion("ML_001", SuggestionSource.MODEL, 0.88, "\u0995\u09bf\u09a8\u09cd\u09a4", []),
            _suggestion("SPELL_002", SuggestionSource.SPELL, 0.86, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]),
            _suggestion("REP_001", SuggestionSource.RULE, 0.8, "\u0986\u09ae\u09bf \u0986\u09ae\u09bf", ["\u0986\u09ae\u09bf"]),
        ],
        text="\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b2\u09bf\u0996\u09bf",
    )

    assert ranked[0].rule_id in {"SPELL_002", "REP_001"}
    assert {suggestion.rule_id for suggestion in ranked[:2]} == {"SPELL_002", "REP_001"}
    assert ranked[-1].rule_id == "ML_001"


def test_heuristic_ranker_scores_rule_candidates_above_model_candidates() -> None:
    ranker = NeuralRankerInterface()
    ranked = ranker.rank(
        [
            _suggestion("ML_001", SuggestionSource.MODEL, 0.88, "\u0995\u09bf\u09a8\u09cd\u09a4", []),
            _suggestion("REP_001", SuggestionSource.RULE, 0.88, "\u0986\u09ae\u09bf \u0986\u09ae\u09bf", ["\u0986\u09ae\u09bf"]),
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
