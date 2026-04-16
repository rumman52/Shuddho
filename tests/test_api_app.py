import importlib
import re

from services.api.shuddho_api.app import (
    ALLOWED_ORIGIN_REGEX,
    ALLOWED_ORIGINS,
    _parse_allowed_origins,
    analyze,
    detector_service,
    health,
    openrouter_client,
)
from shared.schemas.python_models import (
    AnalyzeMode,
    AnalyzeRequest,
    AnalyzeResponse,
    Suggestion,
    SuggestionCategory,
    SuggestionSeverity,
    SuggestionSource,
)

app_module = importlib.import_module("services.api.shuddho_api.app")


def test_health_reports_detector_status() -> None:
    response = health()
    payload = response.model_dump()
    detector_runtime = detector_service.runtime_status()
    openrouter_runtime = openrouter_client.runtime_status()

    assert response.status == "ok"
    assert response.detector_loaded is detector_service.is_loaded()
    assert response.detector_checkpoint == detector_service.checkpoint_path
    assert response.allowed_origins == ALLOWED_ORIGINS
    assert set(payload) == {
        "status",
        "detector_loaded",
        "detector_checkpoint",
        "allowed_origins",
        "openrouter_configured",
        "openrouter_available",
        "openrouter_model",
        "detector",
        "openrouter",
        "analysis_profile",
        "degraded_reasons",
    }
    assert response.openrouter_configured is openrouter_client.is_configured()
    assert response.openrouter_available is openrouter_client.is_available()
    assert response.openrouter_model == openrouter_client.model_name
    assert response.detector.loaded is detector_runtime.loaded
    assert response.detector.enabled is detector_runtime.enabled
    assert response.detector.status == detector_runtime.status
    assert response.detector.reason == detector_runtime.reason
    assert response.detector.checkpoint == detector_runtime.checkpoint
    assert response.detector.backend_name == detector_runtime.backend_name
    assert response.detector.threshold == detector_runtime.threshold
    assert response.openrouter.status == openrouter_runtime.status
    assert response.openrouter.reason == openrouter_runtime.reason
    assert response.openrouter.model == openrouter_runtime.model
    assert response.openrouter.api_key_present is openrouter_runtime.api_key_present
    assert response.openrouter.timeout_seconds == openrouter_runtime.timeout_seconds
    assert response.analysis_profile in {
        "full_backend",
        "backend_without_detector",
        "backend_without_openrouter",
        "backend_rules_and_spell_only",
    }
    assert all(reason.startswith(("detector_", "openrouter_")) for reason in response.degraded_reasons)


def test_health_exposes_degraded_runtime_reasons(monkeypatch) -> None:
    class StubDetectorService:
        checkpoint_path = "artifacts/detector/detector-base"

        def is_loaded(self) -> bool:
            return False

        def runtime_status(self):
            return type(
                "DetectorStatus",
                (),
                {
                    "enabled": False,
                    "loaded": False,
                    "status": "disabled",
                    "reason": "SHUDDHO_DETECTOR_ENABLED=false disabled detector startup.",
                    "checkpoint": self.checkpoint_path,
                    "checkpoint_exists": True,
                    "backend_name": "disabled",
                    "threshold": 0.92,
                },
            )()

    class StubOpenRouterClient:
        model_name = "openrouter-test"

        def is_configured(self) -> bool:
            return False

        def is_available(self) -> bool:
            return False

        def runtime_status(self):
            return type(
                "OpenRouterStatus",
                (),
                {
                    "configured": False,
                    "available": False,
                    "status": "missing_api_key",
                    "reason": "OPENROUTER_API_KEY is missing from the repo-root environment.",
                    "model": self.model_name,
                    "api_key_present": False,
                    "timeout_seconds": 20,
                },
            )()

    monkeypatch.setattr(app_module, "detector_service", StubDetectorService())
    monkeypatch.setattr(app_module, "openrouter_client", StubOpenRouterClient())

    response = app_module.health()

    assert response.analysis_profile == "backend_rules_and_spell_only"
    assert response.degraded_reasons == ["detector_disabled", "openrouter_missing_api_key"]
    assert response.detector.reason == "SHUDDHO_DETECTOR_ENABLED=false disabled detector startup."
    assert response.openrouter.reason == "OPENROUTER_API_KEY is missing from the repo-root environment."


def test_cors_allows_extension_origin() -> None:
    origin = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    assert re.fullmatch(ALLOWED_ORIGIN_REGEX, origin)


def test_cors_allows_localhost_dev_origin() -> None:
    origin = "http://localhost:5173"

    assert re.fullmatch(ALLOWED_ORIGIN_REGEX, origin)


def test_default_allowed_origins_include_local_dev_hosts() -> None:
    assert "http://127.0.0.1:5173" in ALLOWED_ORIGINS
    assert "http://localhost:5173" in ALLOWED_ORIGINS


def test_parse_allowed_origins_can_include_production_frontend_origin() -> None:
    allowed_origins = _parse_allowed_origins(
        "http://127.0.0.1:5173, https://shuddho-web-editor.vercel.app"
    )

    assert allowed_origins == [
        "http://127.0.0.1:5173",
        "https://shuddho-web-editor.vercel.app",
    ]


def test_parse_allowed_origins_supports_trycloudflare_origin() -> None:
    allowed_origins = _parse_allowed_origins(
        "https://random-name.trycloudflare.com, https://shuddho-web-editor.vercel.app"
    )

    assert allowed_origins == [
        "https://random-name.trycloudflare.com",
        "https://shuddho-web-editor.vercel.app",
    ]


def test_analyze_route_forwards_mode_to_analysis_pipeline(monkeypatch) -> None:
    recorded_call: dict[str, object] = {}

    class StubPipeline:
        def analyze(self, text: str, personal_dictionary: list[str] | None, mode: AnalyzeMode) -> AnalyzeResponse:
            recorded_call["text"] = text
            recorded_call["personal_dictionary"] = personal_dictionary
            recorded_call["mode"] = mode
            return AnalyzeResponse(text=text, normalized_text=text, corrected_text=text, suggestions=[])

    class StubFeedbackStore:
        def load_personal_dictionary(self, user_id: str | None = None) -> list[str]:
            assert user_id is None
            return []

        def load_suppressed_keys(self, user_id: str | None = None) -> set[str]:
            assert user_id is None
            return set()

    monkeypatch.setattr(app_module, "analysis_pipeline", StubPipeline())
    monkeypatch.setattr(app_module, "feedback_store", StubFeedbackStore())

    response = analyze(
        AnalyzeRequest(
            text="\u09ac\u09be\u0982\u09b2\u09be",
            personal_dictionary=["\u09a8\u09bf\u099c\u09b8\u09cd\u09ac \u09b6\u09ac\u09cd\u09a6"],
            mode=AnalyzeMode.FORMAL,
        )
    )

    assert response.suggestions == []
    assert recorded_call == {
        "text": "\u09ac\u09be\u0982\u09b2\u09be",
        "personal_dictionary": ["\u09a8\u09bf\u099c\u09b8\u09cd\u09ac \u09b6\u09ac\u09cd\u09a6"],
        "mode": AnalyzeMode.FORMAL,
    }
    assert response.corrected_text == "\u09ac\u09be\u0982\u09b2\u09be"


def test_analyze_route_merges_user_dictionary_and_filters_suppressed_suggestions(monkeypatch) -> None:
    recorded_call: dict[str, object] = {}

    class StubPipeline:
        def analyze(self, text: str, personal_dictionary: list[str] | None, mode: AnalyzeMode) -> AnalyzeResponse:
            recorded_call["text"] = text
            recorded_call["personal_dictionary"] = personal_dictionary
            recorded_call["mode"] = mode
            return AnalyzeResponse(
                text=text,
                normalized_text=text,
                corrected_text="\u0986\u09ae\u09bf\u0964",
                suggestions=[
                    _suggestion("REP_001", "\u0986\u09ae\u09bf \u0986\u09ae\u09bf", ["\u0986\u09ae\u09bf"], suppression_key="sup_hidden"),
                    _suggestion("PUNC_001", "\u0964\u0964", ["\u0964"], category=SuggestionCategory.PUNCTUATION, suppression_key="sup_visible", span_start=7),
                ],
            )

    class StubFeedbackStore:
        def load_personal_dictionary(self, user_id: str | None = None) -> list[str]:
            assert user_id == "web-user"
            return ["\u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4 \u09b6\u09ac\u09cd\u09a6"]

        def load_suppressed_keys(self, user_id: str | None = None) -> set[str]:
            assert user_id == "web-user"
            return {"sup_hidden"}

    monkeypatch.setattr(app_module, "analysis_pipeline", StubPipeline())
    monkeypatch.setattr(app_module, "feedback_store", StubFeedbackStore())

    response = analyze(
        AnalyzeRequest(
            text="\u0986\u09ae\u09bf \u0986\u09ae\u09bf\u0964\u0964",
            personal_dictionary=["\u09a8\u09bf\u099c\u09b8\u09cd\u09ac \u09b6\u09ac\u09cd\u09a6", "\u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4 \u09b6\u09ac\u09cd\u09a6"],
            mode=AnalyzeMode.STRICT,
            user_id="web-user",
        )
    )

    assert recorded_call == {
        "text": "\u0986\u09ae\u09bf \u0986\u09ae\u09bf\u0964\u0964",
        "personal_dictionary": ["\u09a8\u09bf\u099c\u09b8\u09cd\u09ac \u09b6\u09ac\u09cd\u09a6", "\u09b8\u0982\u09b0\u0995\u09cd\u09b7\u09bf\u09a4 \u09b6\u09ac\u09cd\u09a6"],
        "mode": AnalyzeMode.STRICT,
    }
    assert [suggestion.rule_id for suggestion in response.suggestions] == ["PUNC_001"]
    assert response.corrected_text == "\u0986\u09ae\u09bf \u0986\u09ae\u09bf\u0964"


def _suggestion(
    rule_id: str,
    original_text: str,
    replacements: list[str],
    *,
    category: SuggestionCategory = SuggestionCategory.GRAMMAR,
    suppression_key: str | None = None,
    span_start: int = 0,
) -> Suggestion:
    return Suggestion(
        id=rule_id.lower(),
        rule_id=rule_id,
        category=category,
        subtype=rule_id.lower(),
        span_start=span_start,
        span_end=span_start + len(original_text),
        original_text=original_text,
        replacement_options=replacements,
        confidence=0.95,
        explanation_bn="",
        explanation_en="",
        source=SuggestionSource.RULE,
        severity=SuggestionSeverity.MEDIUM,
        suppression_key=suppression_key,
    )
