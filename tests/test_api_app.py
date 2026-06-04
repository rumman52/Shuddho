import importlib
import re
import json
from fastapi.testclient import TestClient

from services.api.shuddho_api.app import (
    app,
    ALLOWED_ORIGIN_REGEX,
    ALLOWED_ORIGINS,
    _parse_allowed_origins,
    analyze,
    corrector_service,
    detector_service,
    health,
    health_deep,
    get_api_preferences,
    put_api_preferences,
    events_api,
    feedback,
    check_canonical,
    ai_check,
    ApiCheckRequest,
)
from shared.schemas.python_models import (
    AnalyzeMode,
    AnalyzeRequest,
    AnalyzeResponse,
    CanonicalCheckRequest,
    Suggestion,
    SuggestionCategory,
    SuggestionSeverity,
    SuggestionSource,
    FeedbackRequest,
    FeedbackRecord,
)

app_module = importlib.import_module("services.api.shuddho_api.app")
client = TestClient(app)


def test_api_preferences_route_returns_full_shape() -> None:
    response = get_api_preferences("pytest-http-user")
    payload = response.model_dump()

    assert payload["user_id"] == "pytest-http-user"
    assert payload["language"] == "bn"
    assert payload["personal_dictionary"] == []
    assert payload["enabledSuggestionTypes"] == [
        "grammar",
        "spelling",
        "punctuation",
        "spacing",
        "style",
        "tone",
        "rewrite",
    ]


def test_api_check_route_returns_suggestions_and_warnings_arrays() -> None:
    response = check_canonical(
        ApiCheckRequest(text="আমি  আমি ভাত খাই।", language="bn")
    )
    payload = response.model_dump()

    assert payload["language"] == "bn"
    assert isinstance(payload["suggestions"], list)
    assert isinstance(payload["warnings"], list)


def test_health_deep_route_returns_backend_reachable() -> None:
    response = health_deep()

    assert response.backend_reachable is True
    assert response.backend_version
    assert isinstance(response.llm, dict)


def test_ai_check_returns_warning_when_llm_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "false")
    response = ai_check(app_module.AiCheckRequest(text="আমি আজ স্কুলে গেছিলাম।", language="bn"))
    assert response.llm_enabled is False
    assert "llm_disabled" in response.warnings


def test_ai_check_warns_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = ai_check(app_module.AiCheckRequest(text="আমি আজ স্কুলে গেছিলাম।", language="bn"))
    assert "openrouter_api_key_missing" in response.warnings



def test_routes_survive_missing_corrector_checkpoint() -> None:
    health_response = health()
    assert health_response.status == "ok"

    deep_response = health_deep()
    assert deep_response.backend_reachable is True
    assert deep_response.corrector.status in {
        "missing_checkpoint",
        "disabled",
        "load_failed",
    }

    check_response = check_canonical(
        ApiCheckRequest(text="আমি  আমি ভাত খাই।", language="bn")
    )
    assert isinstance(check_response.suggestions, list)
    assert isinstance(check_response.warnings, list)
    if deep_response.corrector.status != "ready":
        assert (
            "Sentence-level corrector is not loaded. Shuddho is running rules + spelling only."
            in check_response.warnings
        )


def test_api_events_route_returns_ok() -> None:
    assert events_api({"type": "editor_loaded", "language": "bn"}) == {"ok": True}


def test_cors_configuration_includes_vercel_origin() -> None:
    assert "https://shuddho-web-editor.vercel.app" in ALLOWED_ORIGINS


def test_api_preferences_get_returns_defaults() -> None:
    response = get_api_preferences("pytest-user")

    assert response.language == "bn"
    assert response.dialect == "standard"
    assert "grammar" in response.enabledSuggestionTypes
    assert response.disabledSuggestionTypes == []


def test_api_preferences_put_stores_values() -> None:
    payload = app_module.ApiPreferences(
        user_id="pytest-user", disabledSuggestionTypes=["tone"]
    )

    saved = put_api_preferences(payload, user_id="pytest-user")
    loaded = get_api_preferences("pytest-user")

    assert saved.disabledSuggestionTypes == ["tone"]
    assert loaded.disabledSuggestionTypes == ["tone"]


def test_api_events_returns_ok() -> None:
    assert events_api({"type": "frontend_loaded"}) == {"ok": True}


def test_feedback_route_persists_record_via_store(monkeypatch) -> None:
    captured: list[FeedbackRequest] = []

    class StubFeedbackStore:
        def save(self, payload: FeedbackRequest) -> FeedbackRecord:
            captured.append(payload)
            return FeedbackRecord(
                id=1,
                suggestion_id=payload.suggestion_id,
                action=payload.action,
                text=payload.text,
                replacement=payload.replacement,
                feedback_key=payload.feedback_key,
                rule_id=payload.rule_id,
                subtype=payload.subtype,
                source=payload.source,
                original_text=payload.original_text,
                suppression_key=payload.suppression_key,
                user_dictionary_entry=payload.user_dictionary_entry,
                user_id=payload.user_id,
                created_at=app_module.STARTUP_TIMESTAMP,
            )

    monkeypatch.setattr(app_module, "feedback_store", StubFeedbackStore())
    payload = FeedbackRequest(
        suggestion_id="SUGG_1",
        action="accepted",
        text="আমি ভাত খাই",
        replacement="খাই।",
        feedback_key="fbk-1",
        rule_id="bn.rule",
        subtype="grammar",
        source="rule",
        original_text="খাই",
        user_id="u-1",
    )
    result = feedback(payload)

    assert len(captured) == 1
    assert captured[0].model_dump() == payload.model_dump()
    assert result.id == 1


def test_api_check_compatibility_route_accepts_bangla_text(monkeypatch) -> None:
    def stub_analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
        assert payload.text == "আমি  আমি ভাত খাই।"
        return AnalyzeResponse(
            text=payload.text,
            normalized_text=payload.text,
            corrected_text=payload.text,
            suggestions=[],
            runtime_warnings=["corrector_missing_checkpoint"],
            backend_warning="Sentence-level corrector is not loaded. Shuddho is running rules + spelling only.",
        )

    monkeypatch.setattr(app_module, "analyze", stub_analyze)

    response = check_canonical(
        ApiCheckRequest(text="আমি  আমি ভাত খাই।", language="bn")
    )

    assert response.language == "bn"
    assert response.normalizedText == "আমি  আমি ভাত খাই।"
    assert response.suggestions == []
    assert response.warnings == [
        "corrector_missing_checkpoint",
        "Sentence-level corrector is not loaded. Shuddho is running rules + spelling only.",
    ]


def test_api_check_accepts_minimal_payload() -> None:
    response = client.post("/api/check", json={"text": "আমি ভাত খাই।"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["status"] == "skipped"


def test_api_check_accepts_fast_mode_without_bool_parsing_errors() -> None:
    response = client.post(
        "/api/check",
        json={
            "text": "গত মাসে আমি চিড়িয়াখানায় যাবে।",
            "language": "bn",
            "options": {
                "includeLLM": False,
                "asyncLLM": False,
                "llmMode": "none",
                "mode": "fast",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["status"] == "skipped"


def test_api_check_accepts_smart_review_candidates_payload() -> None:
    response = client.post(
        "/api/check",
        json={
            "text": "গত মাসে আমি চিড়িয়াখানায় যাবে।",
            "language": "bn",
            "options": {
                "includeLLM": True,
                "asyncLLM": True,
                "llmMode": "review_candidates",
                "mode": "smart",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["requested"] is True


def test_api_check_fast_timings_has_no_none() -> None:
    response = client.post(
        "/api/check",
        json={
            "text": "আমি ভাত খাই।",
            "language": "bn",
            "options": {"includeLLM": False, "asyncLLM": False, "mode": "fast", "llmMode": "none"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "timings" in data
    assert all(value is not None for value in data["timings"].values())
    assert all(isinstance(value, (int, float)) for value in data["timings"].values())
    assert data["llm"]["status"] == "skipped"


def test_api_check_async_llm_timings_has_no_none() -> None:
    response = client.post(
        "/api/check",
        json={
            "text": "গত মাসে আমি চিড়িয়াখানায় যাবে।",
            "language": "bn",
            "options": {"includeLLM": True, "asyncLLM": True, "mode": "smart", "llmMode": "review_candidates"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert all(value is not None for value in data["timings"].values())
    assert all(isinstance(value, (int, float)) for value in data["timings"].values())
    if "llm_ms" in data["timings"]:
        assert isinstance(data["timings"]["llm_ms"], (int, float))
    assert isinstance(data.get("llm"), dict)


def test_api_check_response_validation_fallback_when_payload_invalid(monkeypatch) -> None:
    original_model = app_module.CanonicalCheckResponse

    class _BoomModel:
        def __init__(self, **_: object) -> None:
            raise ValidationError.from_exception_data("CanonicalCheckResponse", [])

    monkeypatch.setattr(app_module, "CanonicalCheckResponse", _BoomModel)
    response = client.post("/api/check", json={"text": "আমি ভাত খাই।", "language": "bn"})
    monkeypatch.setattr(app_module, "CanonicalCheckResponse", original_model)

    assert response.status_code == 200
    payload = response.json()
    assert "canonical_response_validation_error" in (payload.get("warnings") or [])
    assert all(value is not None for value in payload.get("timings", {}).values())


def test_api_check_mode_and_llmmode_strings_do_not_crash() -> None:
    response = client.post(
        "/api/check",
        json={
            "text": "আমি ভাত খাই।",
            "language": "bn",
            "options": {"includeLLM": True, "asyncLLM": True, "mode": "smart", "llmMode": "review_candidates"},
        },
    )
    assert response.status_code == 200
    assert isinstance(response.json().get("llm"), dict)



def test_health_route_returns_fast_ok_without_llm_keys(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "shuddho-api"
    assert "llm" not in payload


def test_health_deep_does_not_call_llm_provider(monkeypatch) -> None:
    def fail_llm_config() -> tuple[bool, str, str, str | None]:
        raise AssertionError("health/deep must not initialize or call an LLM provider")

    monkeypatch.setattr(app_module, "_llm_config", fail_llm_config)

    response = client.get("/health")

    assert response.status_code == 200


def test_cors_preflight_allows_vercel_frontend_origin() -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "https://shuddho-web-editor.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://shuddho-web-editor.vercel.app"

def test_api_check_validation_returns_json_422_not_asgi_500() -> None:
    response = client.post("/api/check", json={"text": ""})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "request_validation_error"


def test_cors_config_includes_vercel_frontend_origin() -> None:
    assert "https://shuddho-web-editor.vercel.app" in ALLOWED_ORIGINS


def test_health_reports_detector_and_corrector_status() -> None:
    response = health()
    payload = response.model_dump()
    detector_runtime = detector_service.runtime_status()
    corrector_runtime = corrector_service.runtime_status()

    assert response.ok is True
    assert response.service == "shuddho-api"
    assert response.status == "ok"
    assert response.backend_reachable is True
    assert response.detector_loaded is detector_service.is_loaded()
    assert response.detector_checkpoint == detector_service.checkpoint_path
    assert response.corrector_loaded is corrector_service.is_loaded()
    assert response.corrector_checkpoint == corrector_service.checkpoint_path
    assert response.allowed_origins == ALLOWED_ORIGINS
    assert set(payload) == {
        "ok",
        "service",
        "status",
        "backend_reachable",
        "detector_loaded",
        "detector_checkpoint",
        "corrector_loaded",
        "corrector_checkpoint",
        "allowed_origins",
        "detector",
        "corrector",
        "analysis_profile",
        "degraded_reasons",
        "mode_capabilities",
    }
    assert response.detector.loaded is detector_runtime.loaded
    assert response.detector.enabled is detector_runtime.enabled
    assert response.detector.status == detector_runtime.status
    assert response.detector.reason == detector_runtime.reason
    assert response.detector.checkpoint == detector_runtime.checkpoint
    assert response.detector.backend_name == detector_runtime.backend_name
    assert response.detector.threshold == detector_runtime.threshold
    assert response.corrector.loaded is corrector_runtime.loaded
    assert response.corrector.enabled is corrector_runtime.enabled
    assert response.corrector.status == corrector_runtime.status
    assert response.corrector.reason == corrector_runtime.reason
    assert response.corrector.checkpoint == corrector_runtime.checkpoint
    assert response.corrector.backend_name == corrector_runtime.backend_name
    assert response.corrector.threshold == corrector_runtime.threshold
    assert response.analysis_profile in {
        "full_local",
        "backend_without_detector",
        "backend_without_corrector",
        "backend_rules_and_spell_only",
    }
    assert all(
        reason.startswith(("detector_", "corrector_"))
        for reason in response.degraded_reasons
    )
    assert set(response.mode_capabilities) == {"standard", "strict", "formal"}
    assert "rules" in response.mode_capabilities["standard"]
    assert "spell" in response.mode_capabilities["strict"]


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

    class StubCorrectorService:
        checkpoint_path = "artifacts/corrector/corrector-base"

        def is_loaded(self) -> bool:
            return False

        def runtime_status(self):
            return type(
                "CorrectorStatus",
                (),
                {
                    "enabled": True,
                    "loaded": False,
                    "status": "missing_checkpoint",
                    "reason": "Corrector checkpoint could not be loaded from 'artifacts/corrector/corrector-base': missing required corrector checkpoint files: metadata.json",
                    "checkpoint": self.checkpoint_path,
                    "checkpoint_exists": False,
                    "backend_name": "disabled",
                    "threshold": 0.86,
                },
            )()

    monkeypatch.setattr(app_module, "detector_service", StubDetectorService())
    monkeypatch.setattr(app_module, "corrector_service", StubCorrectorService())

    response = app_module.health()

    assert response.analysis_profile == "backend_rules_and_spell_only"
    assert response.backend_reachable is True
    assert response.degraded_reasons == [
        "detector_disabled",
        "corrector_missing_checkpoint",
    ]
    assert (
        response.detector.reason
        == "SHUDDHO_DETECTOR_ENABLED=false disabled detector startup."
    )
    assert response.corrector.reason.startswith(
        "Corrector checkpoint could not be loaded"
    )
    assert (
        "sentence_level_local_corrector" not in response.mode_capabilities["standard"]
    )


def test_health_deep_reports_full_profile_when_mock_corrector_loaded(
    monkeypatch,
) -> None:
    class StubDetectorService:
        checkpoint_path = "artifacts/detector/detector-base"

        def is_loaded(self) -> bool:
            return True

        def runtime_status(self):
            return type(
                "DetectorStatus",
                (),
                {
                    "enabled": True,
                    "loaded": True,
                    "status": "ready",
                    "reason": None,
                    "checkpoint": self.checkpoint_path,
                    "checkpoint_exists": True,
                    "backend_name": "stub_detector",
                    "threshold": 0.92,
                },
            )()

    class StubCorrectorService:
        checkpoint_path = "artifacts/corrector/corrector-base"

        def is_loaded(self) -> bool:
            return True

        def runtime_status(self):
            return type(
                "CorrectorStatus",
                (),
                {
                    "enabled": True,
                    "loaded": True,
                    "status": "ready",
                    "reason": None,
                    "checkpoint": self.checkpoint_path,
                    "checkpoint_exists": True,
                    "backend_name": "stub_corrector",
                    "threshold": 0.86,
                },
            )()

    monkeypatch.setattr(app_module, "detector_service", StubDetectorService())
    monkeypatch.setattr(app_module, "corrector_service", StubCorrectorService())

    response = app_module.health_deep()

    assert response.corrector.status == "ready"
    assert response.corrector.loaded is True
    assert response.analysis_profile == "full_local"
    assert response.degraded_reasons == []
    assert "sentence_level_local_corrector" in response.mode_capabilities["standard"]


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
        "http://localhost:5173",
        "https://shuddho-web-editor.vercel.app",
    ]


def test_parse_allowed_origins_supports_trycloudflare_origin() -> None:
    allowed_origins = _parse_allowed_origins(
        "https://random-name.trycloudflare.com, https://shuddho-web-editor.vercel.app"
    )

    assert allowed_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "https://shuddho-web-editor.vercel.app",
        "https://random-name.trycloudflare.com",
    ]


def test_parse_allowed_origins_keeps_default_frontend_origin_when_env_lists_only_local_hosts() -> (
    None
):
    allowed_origins = _parse_allowed_origins(
        "http://127.0.0.1:5173, http://localhost:5173"
    )

    assert allowed_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "https://shuddho-web-editor.vercel.app",
    ]


def test_analyze_route_forwards_mode_to_analysis_pipeline(monkeypatch) -> None:
    recorded_call: dict[str, object] = {}

    class StubPipeline:
        def analyze(
            self, text: str, personal_dictionary: list[str] | None, mode: AnalyzeMode
        ) -> AnalyzeResponse:
            recorded_call["text"] = text
            recorded_call["personal_dictionary"] = personal_dictionary
            recorded_call["mode"] = mode
            return AnalyzeResponse(
                text=text, normalized_text=text, corrected_text=text, suggestions=[]
            )

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
            text="বাংলা",
            personal_dictionary=["নিজস্ব শব্দ"],
            mode=AnalyzeMode.FORMAL,
        )
    )

    assert response.suggestions == []
    assert recorded_call == {
        "text": "বাংলা",
        "personal_dictionary": ["নিজস্ব শব্দ"],
        "mode": AnalyzeMode.FORMAL,
    }
    assert response.corrected_text == "বাংলা"


def test_analyze_route_merges_user_dictionary_and_filters_suppressed_suggestions(
    monkeypatch,
) -> None:
    recorded_call: dict[str, object] = {}

    class StubPipeline:
        def analyze(
            self, text: str, personal_dictionary: list[str] | None, mode: AnalyzeMode
        ) -> AnalyzeResponse:
            recorded_call["text"] = text
            recorded_call["personal_dictionary"] = personal_dictionary
            recorded_call["mode"] = mode
            return AnalyzeResponse(
                text=text,
                normalized_text=text,
                corrected_text="আমি।",
                suggestions=[
                    _suggestion(
                        "REP_001", "আমি আমি", ["আমি"], suppression_key="sup_hidden"
                    ),
                    _suggestion(
                        "PUNC_001",
                        "।।",
                        ["।"],
                        category=SuggestionCategory.PUNCTUATION,
                        suppression_key="sup_visible",
                        span_start=7,
                    ),
                ],
            )

    class StubFeedbackStore:
        def load_personal_dictionary(self, user_id: str | None = None) -> list[str]:
            assert user_id == "web-user"
            return ["সংরক্ষিত শব্দ"]

        def load_suppressed_keys(self, user_id: str | None = None) -> set[str]:
            assert user_id == "web-user"
            return {"sup_hidden"}

    monkeypatch.setattr(app_module, "analysis_pipeline", StubPipeline())
    monkeypatch.setattr(app_module, "feedback_store", StubFeedbackStore())

    response = analyze(
        AnalyzeRequest(
            text="আমি আমি।।",
            personal_dictionary=["নিজস্ব শব্দ", "সংরক্ষিত শব্দ"],
            mode=AnalyzeMode.STRICT,
            user_id="web-user",
        )
    )

    assert recorded_call == {
        "text": "আমি আমি।।",
        "personal_dictionary": ["নিজস্ব শব্দ", "সংরক্ষিত শব্দ"],
        "mode": AnalyzeMode.STRICT,
    }
    assert [suggestion.rule_id for suggestion in response.suggestions] == ["PUNC_001"]
    assert response.corrected_text == "আমি আমি।"


def test_health_deep_reports_runtime_lexicon_metadata() -> None:
    response = health_deep()

    assert response.backend_reachable is True
    assert response.last_startup_timestamp is not None
    assert response.backend_version
    assert response.env_file_path
    assert response.lexicon.runtime_source
    assert response.lexicon.runtime_source_of_truth in {
        "csv_runtime",
        "built_runtime_csv",
        "seed_fallback",
    }
    assert response.lexicon.accepted_word_count >= 0
    assert response.lexicon.candidate_word_count >= 0
    assert response.lexicon.correction_map_count >= 0
    assert response.lexicon.restart_required is True


def test_analyze_route_preserves_runtime_metadata_from_pipeline(monkeypatch) -> None:
    class StubPipeline:
        def analyze(
            self, text: str, personal_dictionary: list[str] | None, mode: AnalyzeMode
        ) -> AnalyzeResponse:
            assert personal_dictionary == ["নিজস্ব"]
            assert mode == AnalyzeMode.STANDARD
            return AnalyzeResponse(
                text=text,
                normalized_text=text,
                corrected_text=text,
                suggestions=[],
                analysis_profile="backend_without_corrector",
                runtime_source="backend_without_corrector",
                runtime_warnings=["corrector_missing_checkpoint"],
                used_detector=True,
                used_corrector=False,
                lexicon_source="words_clean.csv",
                lexicon_version="abc123",
                backend_version="from-pipeline",
                sentence_count=2,
                request_mode_applied=AnalyzeMode.STANDARD,
            )

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
            text="আমি বাংলা। আমি আসি।",
            personal_dictionary=["নিজস্ব"],
            mode=AnalyzeMode.STANDARD,
        )
    )

    assert response.analysis_profile == "backend_without_corrector"
    assert response.runtime_source == "backend_without_corrector"
    assert response.runtime_warnings == ["corrector_missing_checkpoint"]
    assert response.used_detector is True
    assert response.used_corrector is False
    assert response.lexicon_source == app_module.spell_engine.lexicon_source
    assert response.lexicon_version == app_module.spell_engine.lexicon_version
    assert response.backend_version == app_module.BACKEND_VERSION
    assert response.sentence_count == 2


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


def test_llm_auto_enabled_when_key_set_and_unset_enable(monkeypatch) -> None:
    monkeypatch.delenv("SHUDDHO_ENABLE_LLM", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    enabled, _, _, _ = app_module._llm_config()
    assert enabled is True


def test_llm_auto_disabled_without_key(monkeypatch) -> None:
    monkeypatch.delenv("SHUDDHO_ENABLE_LLM", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    enabled, _, _, _ = app_module._llm_config()
    assert enabled is False


def test_llm_false_overrides_key(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    enabled, _, _, _ = app_module._llm_config()
    assert enabled is False


def test_health_deep_openrouter_details(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    resp = health_deep().model_dump()
    assert resp["llm"]["provider"] == "openrouter"
    assert resp["llm"]["model"] == "openai/gpt-oss-120b:free"
    assert resp["llm"]["configured"] is True


def test_ai_check_invalid_json_warning(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    def stub(**kwargs):
        return {"suggestions": [], "warnings": ["openrouter_invalid_json"], "provider": "openrouter", "model": "openai/gpt-oss-120b:free", "raw_used": False}
    monkeypatch.setattr(app_module, "run_openrouter_check", stub)
    response = ai_check(app_module.AiCheckRequest(text="আমি আজ স্কুলে গেছিলাম।", language="bn"))
    assert "openrouter_invalid_json" in response.warnings


def test_api_check_returns_local_when_openrouter_fails(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setattr(app_module, "run_openrouter_check", lambda **kwargs: {"suggestions": [], "warnings": ["openrouter_request_failed"], "provider": "openrouter", "model": "openai/gpt-oss-120b:free", "raw_used": False})
    response = check_canonical(CanonicalCheckRequest(text="আমি  আমি ভাত খাই।", language="bn"))
    assert isinstance(response.suggestions, list)
    assert "openrouter_request_failed" in response.warnings

def test_api_check_accepts_minimal_payload() -> None:
    response = client.post("/api/check", json={"text": "আমি ভাত খাই।"})
    assert response.status_code == 200
    assert response.json()["llm"]["status"] == "skipped"


def test_api_check_accepts_fast_local_payload() -> None:
    response = client.post("/api/check", json={"text": "গত মাসে আমি চিড়িয়াখানায় যাবে।", "language": "bn", "options": {"includeLLM": False, "mode": "fast"}})
    assert response.status_code == 200
    assert response.json()["llm"]["requested"] is False


def test_api_check_accepts_deep_ai_review_payload() -> None:
    response = client.post("/api/check", json={"text": "গত মাসে আমি চিড়িয়াখানায় যাবে।", "language": "bn", "options": {"includeLLM": True, "asyncLLM": True, "llmMode": "review_candidates", "mode": "smart"}})
    assert response.status_code == 200
    assert response.json()["llm"]["requested"] is True


def test_api_check_accepts_camel_case() -> None:
    response = client.post("/api/check", json={"text": "আমি ভাত খাই।", "documentId": "doc1", "userId": "user1", "language": "bn-BD"})
    assert response.status_code == 200


def test_invalid_request_returns_request_validation_error() -> None:
    response = client.post("/api/check", json={})
    assert response.status_code == 422
    assert response.json()["error"] == "request_validation_error"


def test_api_llm_debug_never_returns_api_key(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-token")
    payload = client.get("/api/llm/debug").json()
    assert "secret-token" not in str(payload)


def test_version_returns_validation_fix_version() -> None:
    payload = client.get("/version").json()
    assert payload["llm_pipeline_version"] == "validation-fix-v1"


def test_api_check_include_llm_false_has_explicit_skip_reason(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    response = client.post("/api/check", json={"text": "আমি  আমি ভাত খাই।", "language": "bn", "options": {"includeLLM": False, "mode": "fast", "llmMode": "none"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_requested"] is False
    assert payload["llm_status"] == "skipped"
    assert payload["llm"]["skip_reason"] == "include_llm_false"
    assert isinstance(payload["suggestions"], list)


def test_api_check_openai_missing_key_preserves_local(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/api/check", json={"text": "আমি  আমি ভাত খাই।", "language": "bn", "options": {"includeLLM": True, "asyncLLM": False, "mode": "smart", "llmMode": "review_candidates"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_status"] == "missing_key"
    assert "openai_api_key_missing" in payload["warnings"]
    assert isinstance(payload["suggestions"], list)


def test_api_check_openai_rejects_openrouter_model_id(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "openai/gpt-oss-120b:free")
    response = client.post("/api/check", json={"text": "আমি ভাত খাই।", "language": "bn", "options": {"includeLLM": True, "asyncLLM": False}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_status"] == "unsupported_provider"
    assert "openai_model_id_suspicious_use_openrouter_provider" in payload["warnings"]


def test_api_check_successful_mocked_openai_merges_model_suggestion(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    def fake_run(text, request_id, local_suggestions=None, timeout_seconds=None):
        return app_module.AiCheckResponse(
            suggestions=[{"id":"ai1","sentenceId":"s_0","original":"ভাত","replacement":"ভাতই","issueType":"clarity","severity":"low","explanation":"আরও পরিষ্কার","confidence":0.9}],
            correctedText=text.replace("ভাত", "ভাতই"),
            provider="openai",
            model="gpt-4o-mini",
            llm_enabled=True,
            configured=True,
            called=True,
            parsed=True,
            status="completed",
            response_mode="json_schema",
        )

    monkeypatch.setattr(app_module, "_run_ai_check", fake_run)
    response = client.post("/api/check", json={"text": "আমি ভাত খাই।", "language": "bn", "options": {"includeLLM": True, "asyncLLM": False, "mode": "smart", "llmMode": "review_candidates"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_attempted"] is True
    assert payload["llm_used"] is True
    assert payload["llm_status"] == "completed"
    assert payload["ai_suggestion_count"] > 0
    assert any(s["source"] in {"model", "hybrid"} for s in payload["suggestions"])


def test_api_check_timeout_invalid_json_invalid_schema_and_empty(monkeypatch) -> None:
    statuses = [
        ("timeout", "openai_timeout"),
        ("invalid_json", "openai_invalid_json"),
        ("invalid_schema", "openai_invalid_schema"),
        ("completed_empty", None),
    ]
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    for status, warning in statuses:
        def fake_run(text, request_id, local_suggestions=None, timeout_seconds=None, status=status, warning=warning):
            return app_module.AiCheckResponse(provider="openai", model="gpt-4o-mini", llm_enabled=True, configured=True, called=True, parsed=status=="completed_empty", status=status, warnings=[warning] if warning else [], response_mode="json_schema")
        monkeypatch.setattr(app_module, "_run_ai_check", fake_run)
        response = client.post("/api/check", json={"text": "আমি  আমি ভাত খাই।", "language": "bn", "options": {"includeLLM": True, "asyncLLM": False}})
        assert response.status_code == 200
        payload = response.json()
        assert payload["llm_status"] == status
        if warning:
            assert warning in payload["warnings"]
        assert isinstance(payload["suggestions"], list)


def test_llm_debug_exposes_safe_config(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    response = client.get("/api/llm/debug")
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key_present"] is True
    assert "api_key" not in payload
    assert payload["status"] == "ready"
    assert payload["interactive_timeout_seconds"] == 45

def test_api_check_include_llm_false_skips_llm(monkeypatch) -> None:
    called = False

    def fail_run_ai_check(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM should not run when includeLLM=false")

    monkeypatch.setattr(app_module, "_run_ai_check", fail_run_ai_check)
    response = check_canonical(
        ApiCheckRequest(
            text="আমি ভাত খাই।",
            language="bn",
            options={"includeLLM": False, "asyncLLM": False, "mode": "fast", "llmMode": "none"},
        )
    )
    assert called is False
    assert response.llm_requested is False
    assert response.llm_attempted is False
    assert response.llm_status == "skipped"


def test_api_check_include_llm_true_merges_valid_ai(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

    def fake_run_ai_check(text, request_id, local_suggestions=None, timeout_seconds=None):
        return app_module.AiCheckResponse(
            suggestions=[
                {
                    "id": "ai-1",
                    "sentenceId": "s_0",
                    "original": "ভাত",
                    "replacement": "ভাতটা",
                    "issueType": "clarity",
                    "severity": "low",
                    "explanation": "আরও নির্দিষ্ট করুন",
                    "confidence": 0.9,
                    "start": 4,
                    "end": 7,
                }
            ],
            correctedText="আমি ভাতটা খাই।",
            documentAssessment={"summary": "ok"},
            provider="openrouter",
            model="openai/gpt-oss-120b:free",
            llm_enabled=True,
            configured=True,
            called=True,
            parsed=True,
            status="completed",
            response_mode="json_schema",
        )

    monkeypatch.setattr(app_module, "_run_ai_check", fake_run_ai_check)
    response = check_canonical(
        ApiCheckRequest(
            text="আমি ভাত খাই।",
            language="bn",
            options={"includeLLM": True, "asyncLLM": False, "mode": "smart", "llmMode": "review_candidates"},
        )
    )
    assert response.llm_requested is True
    assert response.llm_attempted is True
    assert response.llm_used is True
    assert response.llm_provider == "openrouter"
    assert response.llm_model == "openai/gpt-oss-120b:free"
    assert response.ai_suggestion_count == 1
    assert any(s.originalText == "ভাত" and s.provider == "openrouter" for s in response.suggestions)


def test_health_deep_reports_safe_llm_configuration(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "openai/gpt-oss-120b:free")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    response = health_deep()
    assert response.llm["enabled"] is True
    assert response.llm["provider"] == "openai"
    assert response.llm["configured"] is False
    assert response.llm["status"] == "unsupported_provider"
    assert "openai_model_id_suspicious_use_openrouter_provider" in response.llm["warnings"]
    assert "api_key" not in response.llm


def test_api_check_local_suggestions_continue_when_corrector_missing(monkeypatch) -> None:
    class StubCorrectorService:
        checkpoint_path = "artifacts/corrector/corrector-base"

        def is_loaded(self) -> bool:
            return False

        def runtime_status(self):
            return type(
                "CorrectorStatus",
                (),
                {
                    "enabled": True,
                    "loaded": False,
                    "status": "missing_checkpoint",
                    "reason": "missing required corrector checkpoint files: best_model.pt",
                    "checkpoint": self.checkpoint_path,
                    "checkpoint_exists": False,
                    "backend_name": "disabled",
                    "threshold": 0.86,
                },
            )()

    monkeypatch.setattr(app_module, "corrector_service", StubCorrectorService())
    response = check_canonical(
        ApiCheckRequest(
            text="আমি  আমি ভাত খাই।",
            language="bn",
            options={"includeLLM": False, "asyncLLM": False, "mode": "fast", "llmMode": "none"},
        )
    )

    assert response.local_suggestion_count == len(response.suggestions)
    assert response.local_suggestion_count > 0
    assert "sentence_level_corrector_unavailable" in response.warnings
    assert response.diagnostics["backendReachable"] is True
    assert response.diagnostics["backendStatus"] == "ok"
    assert response.diagnostics["correctorLoaded"] is False
    assert response.diagnostics["correctorReason"] == "missing required corrector checkpoint files: best_model.pt"


def test_api_check_calls_openrouter_when_llm_configured_and_corrector_missing(monkeypatch) -> None:
    class StubCorrectorService:
        checkpoint_path = "artifacts/corrector/corrector-base"

        def is_loaded(self) -> bool:
            return False

        def runtime_status(self):
            return type(
                "CorrectorStatus",
                (),
                {
                    "enabled": True,
                    "loaded": False,
                    "status": "missing_checkpoint",
                    "reason": "missing required corrector checkpoint files: best_model.pt",
                    "checkpoint": self.checkpoint_path,
                    "checkpoint_exists": False,
                    "backend_name": "disabled",
                    "threshold": 0.86,
                },
            )()

    calls = []

    def fake_run_ai_check(text, request_id, local_suggestions=None, timeout_seconds=None):
        calls.append({"text": text, "local_suggestions": list(local_suggestions or [])})
        return app_module.AiCheckResponse(
            suggestions=[],
            provider="openrouter",
            model="openai/gpt-oss-120b:free",
            llm_enabled=True,
            configured=True,
            called=True,
            parsed=True,
            status="completed_empty",
            response_mode="json_schema",
        )

    monkeypatch.setattr(app_module, "corrector_service", StubCorrectorService())
    monkeypatch.setattr(app_module, "_run_ai_check", fake_run_ai_check)
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

    response = check_canonical(
        ApiCheckRequest(
            text="আমি  আমি ভাত খাই।",
            language="bn",
            options={"includeLLM": True, "asyncLLM": False, "mode": "smart", "llmMode": "review_candidates"},
        )
    )

    assert calls
    assert response.llm_requested is True
    assert response.llm_attempted is True
    assert response.llm_provider == "openrouter"
    assert response.llm_model == "openai/gpt-oss-120b:free"
    assert "sentence_level_corrector_unavailable" in response.warnings
    assert response.diagnostics["llmEnabled"] is True
    assert response.diagnostics["llmConfigured"] is True
    assert response.diagnostics["llmProvider"] == "openrouter"
    assert response.diagnostics["llmModel"] == "openai/gpt-oss-120b:free"


def test_llm_debug_does_not_expose_api_key(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-value")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
    response = app_module.llm_debug()
    rendered = json.dumps(response)
    assert response["api_key_present"] is True
    assert "sk-secret-value" not in rendered
    assert response["provider"] == "openrouter"
    assert response["model"] == "openai/gpt-oss-120b:free"
    assert "timeout_settings" in response
    assert response["circuit_state"] in {"open", "closed"}


def test_health_shapes_include_lightweight_process_fields() -> None:
    response = app_module.health()
    assert response.ok is True
    assert response.version
    assert response.uptime_seconds >= 0
    assert response.allowed_origins_count == len(response.allowed_origins)
    assert "llm_provider" in response.config


def test_health_deep_shape_includes_llm_without_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-value")
    response = app_module.health_deep()
    rendered = response.model_dump_json()
    assert response.ok is True
    assert isinstance(response.llm, dict)
    assert "sk-secret-value" not in rendered
