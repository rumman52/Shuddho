import importlib
import re

from services.api.shuddho_api.app import (
    ALLOWED_ORIGIN_REGEX,
    ALLOWED_ORIGINS,
    _parse_allowed_origins,
    analyze,
    corrector_service,
    detector_service,
    health,
    health_deep,
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


def test_health_reports_detector_and_corrector_status() -> None:
    response = health()
    payload = response.model_dump()
    detector_runtime = detector_service.runtime_status()
    corrector_runtime = corrector_service.runtime_status()

    assert response.status == "ok"
    assert response.backend_reachable is True
    assert response.detector_loaded is detector_service.is_loaded()
    assert response.detector_checkpoint == detector_service.checkpoint_path
    assert response.corrector_loaded is corrector_service.is_loaded()
    assert response.corrector_checkpoint == corrector_service.checkpoint_path
    assert response.allowed_origins == ALLOWED_ORIGINS
    assert set(payload) == {
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
    assert all(reason.startswith(("detector_", "corrector_")) for reason in response.degraded_reasons)
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
    assert response.degraded_reasons == ["detector_disabled", "corrector_missing_checkpoint"]
    assert response.detector.reason == "SHUDDHO_DETECTOR_ENABLED=false disabled detector startup."
    assert response.corrector.reason.startswith("Corrector checkpoint could not be loaded")
    assert "sentence_level_local_corrector" not in response.mode_capabilities["standard"]


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
                corrected_text="আমি।",
                suggestions=[
                    _suggestion("REP_001", "আমি আমি", ["আমি"], suppression_key="sup_hidden"),
                    _suggestion("PUNC_001", "।।", ["।"], category=SuggestionCategory.PUNCTUATION, suppression_key="sup_visible", span_start=7),
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
    assert response.lexicon.runtime_source_of_truth in {"csv_runtime", "built_runtime_csv", "seed_fallback"}
    assert response.lexicon.accepted_word_count >= 0
    assert response.lexicon.candidate_word_count >= 0
    assert response.lexicon.correction_map_count >= 0
    assert response.lexicon.restart_required is True


def test_analyze_route_preserves_runtime_metadata_from_pipeline(monkeypatch) -> None:
    class StubPipeline:
        def analyze(self, text: str, personal_dictionary: list[str] | None, mode: AnalyzeMode) -> AnalyzeResponse:
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
