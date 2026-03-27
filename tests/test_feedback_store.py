from pathlib import Path

from services.feedback.shuddho_feedback.store import FeedbackStats, FeedbackStore
from shared.schemas.python_models import (
    FeedbackAction,
    FeedbackRequest,
    Suggestion,
    SuggestionCategory,
    SuggestionSeverity,
    SuggestionSource,
)


def test_feedback_store_loads_signal_index_from_saved_history(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    store.save(
        FeedbackRequest(
            suggestion_id="s_1",
            action=FeedbackAction.ACCEPTED,
            text="আমি কিন্ত স্কুলে যাই।",
            replacement="কিন্তু",
            feedback_key="fbk_spell",
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
            feedback_key="fbk_spell",
            rule_id="SPELL_002",
            subtype="orthography_variant",
            source=SuggestionSource.SPELL,
            original_text="কিন্ত",
        )
    )
    store.save(
        FeedbackRequest(
            suggestion_id="s_3",
            action=FeedbackAction.ACCEPTED,
            text="আমি আমি স্কুলে যাই।।",
            replacement="আমি",
            feedback_key="fbk_grammar",
            rule_id="REP_001",
            subtype="repeated_word",
            source=SuggestionSource.RULE,
            original_text="আমি আমি",
        )
    )

    signal_index = store.load_signal_index(
        [
            _suggestion("SPELL_002", "orthography_variant", "কিন্ত", ["কিন্তু"], feedback_key="fbk_spell"),
            _suggestion("REP_001", "repeated_word", "আমি আমি", ["আমি"], source=SuggestionSource.RULE, feedback_key="fbk_grammar"),
        ]
    )

    assert signal_index.by_feedback_key["fbk_spell"] == FeedbackStats(accepted=1, dismissed=1)
    assert signal_index.by_rule_id["REP_001"] == FeedbackStats(accepted=1, dismissed=0)
    assert signal_index.by_subtype["orthography_variant"] == FeedbackStats(accepted=1, dismissed=1)


def test_feedback_store_handles_empty_history_without_crashing(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    signal_index = store.load_signal_index([_suggestion("SPELL_002", "orthography_variant", "কিন্ত", ["কিন্তু"])])

    assert signal_index.by_feedback_key == {}
    assert signal_index.by_rule_id == {}
    assert signal_index.by_subtype == {}


def _suggestion(
    rule_id: str,
    subtype: str,
    original_text: str,
    replacements: list[str],
    *,
    source: SuggestionSource = SuggestionSource.SPELL,
    feedback_key: str | None = None,
) -> Suggestion:
    return Suggestion(
        id=rule_id.lower(),
        rule_id=rule_id,
        category=SuggestionCategory.SPELLING if source == SuggestionSource.SPELL else SuggestionCategory.GRAMMAR,
        subtype=subtype,
        span_start=0,
        span_end=len(original_text),
        original_text=original_text,
        replacement_options=replacements,
        confidence=0.9,
        explanation_bn="",
        explanation_en="",
        source=source,
        severity=SuggestionSeverity.MEDIUM,
        feedback_key=feedback_key,
    )
