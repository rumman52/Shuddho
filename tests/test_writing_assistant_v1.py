from pathlib import Path

import importlib

from services.feedback.shuddho_feedback.store import FeedbackStore
from shared.schemas.python_models import (
    AnalyzeMode,
    AnalyzeResponse,
    FeedbackAction,
    FeedbackRequest,
    RewriteRequest,
    Suggestion,
    SuggestionCategory,
    SuggestionSeverity,
    SuggestionSource,
    ToneAnalysisRequest,
    UserPreferences,
)

app_module = importlib.import_module("services.api.shuddho_api.app")


def test_preferences_round_trip_and_feedback_merge(tmp_path: Path, monkeypatch) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    monkeypatch.setattr(app_module, "feedback_store", store)

    saved = app_module.save_preferences(
        "writer-1",
        UserPreferences(
            user_id="writer-1",
            writing_goal="business",
            tone_goal="professional",
            suggestion_density="low",
            personal_dictionary=["শুদ্ধ"],
            suppressed_rule_keys=["STYLE:001"],
            disabled_sites=["mail.example.com"],
        ),
    )

    store.save(
        FeedbackRequest(
            suggestion_id="s-1",
            action=FeedbackAction.ADD_TO_PERSONAL_DICTIONARY,
            text="রাহুলল",
            original_text="রাহুলল",
            user_dictionary_entry="রাহুল",
            user_id="writer-1",
        )
    )
    store.save(
        FeedbackRequest(
            suggestion_id="s-2",
            action=FeedbackAction.IGNORE_FOREVER,
            text="কিন্ত",
            rule_id="SPELL_001",
            subtype="spelling_error",
            original_text="কিন্ত",
            user_id="writer-1",
        )
    )

    loaded = app_module.get_preferences("writer-1")

    assert saved.writing_goal == "business"
    assert loaded.personal_dictionary == ["শুদ্ধ", "রাহুল"]
    assert "SPELL_001:spelling_error" in loaded.suppressed_rule_keys
    assert loaded.disabled_sites == ["mail.example.com"]


def test_rewrite_endpoint_returns_valid_response(monkeypatch) -> None:
    class StubPipeline:
        def analyze(self, text: str, personal_dictionary: list[str] | None = None, mode: AnalyzeMode = AnalyzeMode.STANDARD) -> AnalyzeResponse:
            del personal_dictionary, mode
            return AnalyzeResponse(
                text=text,
                normalized_text=text,
                corrected_text=text.replace("প্লিজ", "অনুগ্রহ করে"),
                suggestions=[],
            )

    monkeypatch.setattr(app_module, "analysis_pipeline", StubPipeline())

    response = app_module.rewrite(
        RewriteRequest(
            text="প্লিজ রিপোর্ট পাঠান!!",
            intent="professional",
        )
    )

    assert response.intent == "professional"
    assert response.options
    assert response.options[0].rewritten_text
    assert response.target_text == response.options[0].rewritten_text


def test_tone_analyze_endpoint_returns_valid_response() -> None:
    response = app_module.analyze_tone(ToneAnalysisRequest(text="অনুগ্রহ করে দ্রুত উত্তর দিন!!", user_id="writer-1"))

    assert response.primary_tone in {"professional", "respectful", "urgent"}
    assert response.detected_tones
    assert response.confidence >= 0.0
    assert isinstance(response.suggestions, list)


def test_analyze_route_filters_saved_rule_suppression(tmp_path: Path, monkeypatch) -> None:
    store = FeedbackStore(database_path=tmp_path / "feedback.db")
    monkeypatch.setattr(app_module, "feedback_store", store)

    store.save(
        FeedbackRequest(
            suggestion_id="s-1",
            action=FeedbackAction.IGNORE_FOREVER,
            text="কিন্ত",
            rule_id="SPELL_001",
            subtype="spelling_error",
            original_text="কিন্ত",
            user_id="writer-2",
        )
    )

    class StubPipeline:
        def analyze(self, text: str, personal_dictionary: list[str] | None = None, mode: AnalyzeMode = AnalyzeMode.STANDARD) -> AnalyzeResponse:
            del personal_dictionary, mode
            return AnalyzeResponse(
                text=text,
                normalized_text=text,
                corrected_text=text,
                suggestions=[
                    _suggestion("SPELL_001", "spelling_error", "কিন্ত", ["কিন্তু"]),
                    _suggestion("REP_001", "repeated_word", "আমি আমি", ["আমি"], span_start=6),
                ],
            )

    monkeypatch.setattr(app_module, "analysis_pipeline", StubPipeline())

    response = app_module.analyze(
        app_module.AnalyzeRequest(
            text="কিন্ত আমি আমি",
            user_id="writer-2",
        )
    )

    assert [suggestion.rule_id for suggestion in response.suggestions] == ["REP_001"]


def _suggestion(
    rule_id: str,
    subtype: str,
    original_text: str,
    replacements: list[str],
    *,
    span_start: int = 0,
) -> Suggestion:
    return Suggestion(
        id=rule_id.lower(),
        rule_id=rule_id,
        category=SuggestionCategory.SPELLING if rule_id.startswith("SPELL") else SuggestionCategory.GRAMMAR,
        subtype=subtype,
        span_start=span_start,
        span_end=span_start + len(original_text),
        original_text=original_text,
        replacement_options=replacements,
        confidence=0.96,
        explanation_bn="",
        explanation_en="",
        source=SuggestionSource.RULE,
        severity=SuggestionSeverity.MEDIUM,
    )
