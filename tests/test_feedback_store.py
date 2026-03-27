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
            text="\u0986\u09ae\u09bf \u0995\u09bf\u09a8\u09cd\u09a4 \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964",
            replacement="\u0995\u09bf\u09a8\u09cd\u09a4\u09c1",
            feedback_key="fbk_spell",
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
            feedback_key="fbk_spell",
            rule_id="SPELL_002",
            subtype="orthography_variant",
            source=SuggestionSource.SPELL,
            original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
        )
    )
    store.save(
        FeedbackRequest(
            suggestion_id="s_3",
            action=FeedbackAction.ACCEPTED,
            text="\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964\u0964",
            replacement="\u0986\u09ae\u09bf",
            feedback_key="fbk_grammar",
            rule_id="REP_001",
            subtype="repeated_word",
            source=SuggestionSource.RULE,
            original_text="\u0986\u09ae\u09bf \u0986\u09ae\u09bf",
        )
    )

    signal_index = store.load_signal_index(
        [
            _suggestion("SPELL_002", "orthography_variant", "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"], feedback_key="fbk_spell"),
            _suggestion("REP_001", "repeated_word", "\u0986\u09ae\u09bf \u0986\u09ae\u09bf", ["\u0986\u09ae\u09bf"], source=SuggestionSource.RULE, feedback_key="fbk_grammar"),
        ]
    )

    assert signal_index.by_feedback_key["fbk_spell"] == FeedbackStats(accepted=1, dismissed=1)
    assert signal_index.by_rule_id["REP_001"] == FeedbackStats(accepted=1, dismissed=0)
    assert signal_index.by_subtype["orthography_variant"] == FeedbackStats(accepted=1, dismissed=1)


def test_feedback_store_handles_empty_history_without_crashing(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    signal_index = store.load_signal_index([_suggestion("SPELL_002", "orthography_variant", "\u0995\u09bf\u09a8\u09cd\u09a4", ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"])])

    assert signal_index.by_feedback_key == {}
    assert signal_index.by_rule_id == {}
    assert signal_index.by_subtype == {}


def test_feedback_store_persists_suppression_and_personal_dictionary_preferences_per_user(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    store.save(
        FeedbackRequest(
            suggestion_id="s_1",
            action=FeedbackAction.IGNORE_FOREVER,
            text="\u0995\u09bf\u09a8\u09cd\u09a4 \u0986\u09ae\u09bf \u0986\u09b8\u09ac",
            feedback_key="fbk_variant",
            rule_id="SPELL_002",
            subtype="orthography_variant",
            source=SuggestionSource.SPELL,
            original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
            suppression_key="sup_variant",
            user_id="web-user",
        )
    )
    store.save(
        FeedbackRequest(
            suggestion_id="s_2",
            action=FeedbackAction.ADD_TO_PERSONAL_DICTIONARY,
            text="\u09b0\u09be\u09b9\u09c1\u09b2\u09b2",
            feedback_key="fbk_user_word",
            rule_id="SPELL_003",
            subtype="spelling_error",
            source=SuggestionSource.SPELL,
            original_text="\u09b0\u09be\u09b9\u09c1\u09b2\u09b2",
            user_dictionary_entry="\u09b0\u09be\u09b9\u09c1\u09b2",
            user_id="web-user",
        )
    )

    preference_index = store.load_preference_index(user_id="web-user")

    assert preference_index.suppressed_keys == {"sup_variant"}
    assert preference_index.personal_dictionary == {"\u09b0\u09be\u09b9\u09c1\u09b2"}
    assert store.load_suppressed_keys(user_id="web-user") == {"sup_variant"}
    assert store.load_personal_dictionary(user_id="web-user") == ["\u09b0\u09be\u09b9\u09c1\u09b2"]


def test_feedback_store_keeps_user_preferences_scoped(tmp_path: Path) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    store.save(
        FeedbackRequest(
            suggestion_id="s_1",
            action=FeedbackAction.NOT_WRONG,
            text="\u0995\u09bf\u09a8\u09cd\u09a4 \u0986\u09ae\u09bf \u0986\u09b8\u09ac",
            feedback_key="fbk_variant",
            rule_id="SPELL_002",
            subtype="orthography_variant",
            source=SuggestionSource.SPELL,
            original_text="\u0995\u09bf\u09a8\u09cd\u09a4",
            suppression_key="sup_variant",
            user_id="user-a",
        )
    )

    assert store.load_suppressed_keys(user_id="user-a") == {"sup_variant"}
    assert store.load_suppressed_keys(user_id="user-b") == set()


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
