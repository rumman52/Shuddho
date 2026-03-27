from pathlib import Path

from ml.ranking.pipeline import NeuralRankerInterface
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.feedback.shuddho_feedback.store import FeedbackStore
from shared.schemas.python_models import (
    FeedbackAction,
    FeedbackRequest,
    Suggestion,
    SuggestionCategory,
    SuggestionSeverity,
    SuggestionSource,
)


def test_ranking_pipeline_uses_feedback_history_when_available(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    store.save(
        FeedbackRequest(
            suggestion_id="s_1",
            action=FeedbackAction.ACCEPTED,
            text="আমি কিন্ত স্কুলে যাই।",
            replacement="কিন্তু",
            feedback_key="fbk_accept",
            rule_id="SPELL_002",
            subtype="orthography_variant",
            source=SuggestionSource.SPELL,
            original_text="কিন্ত",
        )
    )
    store.save(
        FeedbackRequest(
            suggestion_id="s_2",
            action=FeedbackAction.DISMISSED,
            text="আমি কিন্ত স্কুলে যাই।",
            replacement="কিন্তু",
            feedback_key="fbk_dismiss",
            rule_id="SPELL_003",
            subtype="spelling_error",
            source=SuggestionSource.MODEL,
            original_text="কিন্ত",
        )
    )

    ranking = SuggestionRankingPipeline(ranker=NeuralRankerInterface(), feedback_store=store)
    ranked = ranking.rank(
        [
            _suggestion("SPELL_003", "spelling_error", SuggestionSource.MODEL, "কিন্ত", ["কিন্তু"], feedback_key="fbk_dismiss"),
            _suggestion("SPELL_002", "orthography_variant", SuggestionSource.SPELL, "কিন্ত", ["কিন্তু"], feedback_key="fbk_accept"),
        ],
        text="আমি কিন্ত স্কুলে যাই।",
    )

    assert ranked[0].rule_id == "SPELL_002"


def test_ranker_penalizes_exact_span_conflicts_and_prefers_conservative_fix() -> None:
    ranker = NeuralRankerInterface()
    ranked = ranker.rank(
        [
            _suggestion("ML_001", "model_guess", SuggestionSource.MODEL, "কিন্ত", ["কিন্তু"]),
            _suggestion("SPELL_002", "orthography_variant", SuggestionSource.SPELL, "কিন্ত", ["কিন্তু"]),
            _suggestion("SPELL_004", "spelling_error", SuggestionSource.MODEL, "কিন্ত", ["কিন্তুঈ"]),
        ],
        text="আমি কিন্ত স্কুলে যাই।",
    )

    scores = {item.suggestion.rule_id: item.score for item in ranked}
    assert scores["SPELL_002"] > scores["ML_001"]
    assert scores["SPELL_002"] > scores["SPELL_004"]


def test_ranking_pipeline_with_empty_feedback_store_keeps_analyze_safe(tmp_path: Path) -> None:
    ranking = SuggestionRankingPipeline(
        ranker=NeuralRankerInterface(),
        feedback_store=FeedbackStore(database_path=tmp_path / "feedback.db"),
    )
    ranked = ranking.rank(
        [
            _suggestion("PUNC_002", "space_before_punctuation", SuggestionSource.RULE, " ।", ["।"], category=SuggestionCategory.PUNCTUATION),
            _suggestion("DET_PUNCT", "detector_punctuation", SuggestionSource.MODEL, " ।", [], category=SuggestionCategory.PUNCTUATION),
        ],
        text="সে যায় ।",
    )

    assert ranked[0].rule_id == "PUNC_002"
    assert len(ranked) == 2


def test_ranking_pipeline_prefers_actionable_hybrid_fix_over_vague_warning() -> None:
    ranking = SuggestionRankingPipeline(ranker=NeuralRankerInterface())
    ranked = ranking.rank(
        [
            _suggestion("DET_SPELLING", "detector_spelling", SuggestionSource.MODEL, "কিন্ত", []),
            _suggestion("DET_SPELLING", "detector_spelling", SuggestionSource.HYBRID, "কিন্ত", ["কিন্তু"]),
        ],
        text="আমি কিন্ত স্কুলে যাই।",
    )

    assert ranked[0].source == SuggestionSource.HYBRID
    assert ranked[0].replacement_options == ["কিন্তু"]


def _suggestion(
    rule_id: str,
    subtype: str,
    source: SuggestionSource,
    original_text: str,
    replacements: list[str],
    *,
    category: SuggestionCategory = SuggestionCategory.SPELLING,
    feedback_key: str | None = None,
) -> Suggestion:
    return Suggestion(
        id=rule_id.lower(),
        rule_id=rule_id,
        category=category,
        subtype=subtype,
        span_start=0,
        span_end=len(original_text),
        original_text=original_text,
        replacement_options=replacements,
        confidence=0.88,
        explanation_bn="",
        explanation_en="",
        source=source,
        severity=SuggestionSeverity.MEDIUM,
        feedback_key=feedback_key,
    )
