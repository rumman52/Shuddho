from pathlib import Path

from ml.ranking.pipeline import NeuralRankerInterface
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.feedback.shuddho_feedback.store import FeedbackStore
from shared.schemas.python_models import (
    AnalyzeMode,
    FeedbackAction,
    FeedbackRequest,
    Suggestion,
    SuggestionCategory,
    SuggestionSeverity,
    SuggestionSource,
)


def test_ranking_pipeline_uses_feedback_history_when_available_for_optional_variants_in_formal_mode(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    store.save(
        FeedbackRequest(
            suggestion_id="s_1",
            action=FeedbackAction.ACCEPTED,
            text="\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964",
            replacement="\u0995\u09bf\u09a8\u09cd\u09a4\u09c1",
            feedback_key="fbk_accept",
            rule_id="SPELL_002",
            subtype="orthography_variant",
            source=SuggestionSource.SPELL,
            original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
        )
    )
    store.save(
        FeedbackRequest(
            suggestion_id="s_2",
            action=FeedbackAction.DISMISSED,
            text="\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964",
            replacement="\u0995\u09bf\u09a8\u09cd\u09a4\u09c1",
            feedback_key="fbk_dismiss",
            rule_id="SPELL_003",
            subtype="spelling_error",
            source=SuggestionSource.MODEL,
            original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
        )
    )

    ranking = SuggestionRankingPipeline(ranker=NeuralRankerInterface(), feedback_store=store)
    ranked = ranking.rank(
        [
            _suggestion("SPELL_003", "spelling_error", SuggestionSource.MODEL, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"], feedback_key="fbk_dismiss"),
            _suggestion("SPELL_002", "orthography_variant", SuggestionSource.SPELL, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"], feedback_key="fbk_accept"),
        ],
        text="\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964",
        mode=AnalyzeMode.FORMAL,
    )

    assert ranked[0].rule_id == "SPELL_002"


def test_ranker_prefers_direct_spell_fix_over_model_guess_for_same_span() -> None:
    ranker = NeuralRankerInterface()
    ranked = ranker.rank(
        [
            _suggestion("ML_001", "model_guess", SuggestionSource.MODEL, "\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df", ["\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc"]),
            _suggestion("SPELL_003", "spelling_error", SuggestionSource.SPELL, "\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df", ["\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc"]),
            _suggestion("SPELL_004", "spelling_error", SuggestionSource.MODEL, "\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df", ["\u0985\u0987\u0989\u09b0\u09aa\u09c0\u09af\u09bc\u0987"]),
        ],
        text="\u0986\u09ae\u09bf \u0985\u0987\u0989\u09b0\u09aa\u09c0\u09df \u09b2\u09bf\u0996\u09bf\u0964",
    )

    scores = {item.suggestion.rule_id: item.score for item in ranked}
    assert scores["SPELL_003"] > scores["ML_001"]
    assert scores["SPELL_003"] > scores["SPELL_004"]


def test_ranking_pipeline_with_empty_feedback_store_keeps_analyze_safe(tmp_path: Path) -> None:
    ranking = SuggestionRankingPipeline(
        ranker=NeuralRankerInterface(),
        feedback_store=FeedbackStore(database_path=tmp_path / "feedback.db"),
    )
    ranked = ranking.rank(
        [
            _suggestion("PUNC_002", "space_before_punctuation", SuggestionSource.RULE, " \u0964", ["\u0964"], category=SuggestionCategory.PUNCTUATION),
            _suggestion("DET_PUNCT", "detector_punctuation", SuggestionSource.MODEL, " \u0964", [], category=SuggestionCategory.PUNCTUATION),
        ],
        text="\u09b8\u09c7 \u09af\u09be\u09df \u0964",
    )

    assert ranked[0].rule_id == "PUNC_002"
    assert len(ranked) == 2


def test_ranking_pipeline_prefers_actionable_hybrid_fix_over_vague_warning() -> None:
    ranking = SuggestionRankingPipeline(ranker=NeuralRankerInterface())
    ranked = ranking.rank(
        [
            _suggestion("DET_SPELLING", "detector_spelling", SuggestionSource.MODEL, "\u0995\u09bf\u09a8\u09cd\u09a4", []),
            _suggestion("DET_SPELLING", "detector_spelling", SuggestionSource.HYBRID, "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]),
        ],
        text="\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964",
    )

    assert ranked[0].source == SuggestionSource.HYBRID
    assert ranked[0].replacement_options == ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]


def test_ranker_demotes_same_span_spelling_when_contextual_grammar_exists() -> None:
    ranker = NeuralRankerInterface()
    ranked = ranker.rank(
        [
            _suggestion(
                "GRAM_005",
                "first_person_verb_mismatch",
                SuggestionSource.RULE,
                "\u0996\u09be\u09df",
                ["\u0996\u09be\u0987"],
                category=SuggestionCategory.GRAMMAR,
            ),
            _suggestion(
                "SPELL_002",
                "spelling_error",
                SuggestionSource.SPELL,
                "\u0996\u09be\u09df",
                ["\u0996\u09be\u09df\u09bc"],
                category=SuggestionCategory.SPELLING,
            ),
        ],
        text="\u0986\u09ae\u09bf \u09ad\u09be\u09a4 \u0996\u09be\u09df\u0964",
    )

    assert ranked[0].suggestion.rule_id == "GRAM_005"


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
    confidence = 0.99 if source == SuggestionSource.SPELL and subtype == "spelling_error" else 0.88
    return Suggestion(
        id=rule_id.lower(),
        rule_id=rule_id,
        category=category,
        subtype=subtype,
        span_start=0,
        span_end=len(original_text),
        original_text=original_text,
        replacement_options=replacements,
        confidence=confidence,
        explanation_bn="",
        explanation_en="",
        source=source,
        severity=SuggestionSeverity.MEDIUM,
        feedback_key=feedback_key,
    )
