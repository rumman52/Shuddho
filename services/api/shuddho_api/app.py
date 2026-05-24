from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator
from fastapi.middleware.cors import CORSMiddleware

from services.analysis.shuddho_analysis.candidate_generator import CandidateGenerator
from services.analysis.shuddho_analysis.corrector_service import CorrectorRuntimeStatus, CorrectorService
from services.analysis.shuddho_analysis.detector import DetectorRuntimeStatus, DetectorService
from services.analysis.shuddho_analysis.incremental_cache import ContentHashCache
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline, build_corrected_text
from services.analysis.shuddho_analysis.preferences import UserPreferencesService
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.analysis.shuddho_analysis.rewrite_service import RewriteService
from services.analysis.shuddho_analysis.tone import ToneAnalyzer
from services.feedback.shuddho_feedback.store import FeedbackStore
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from services.api.shuddho_api.adapters import analyze_to_check_response
from services.api.shuddho_api.llm_openrouter import DEFAULT_OPENROUTER_MODEL, run_openrouter_check
from shared.schemas.python_models import (
    AnalysisProfile,
    AnalyzeRequest,
    AnalyzeResponse,
    CorrectorHealth,
    DetectorHealth,
    FeedbackRecord,
    FeedbackRequest,
    HealthDeepResponse,
    HealthResponse,
    LexiconHealth,
    RewriteRequest,
    RewriteResponse,
    Suggestion,
    ToneAnalysisRequest,
    ToneAnalysisResponse,
    UserPreferences,
    CanonicalCheckRequest,
    CanonicalCheckResponse,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = REPO_ROOT / ".env"
ENV_FILE_LOADED = load_dotenv(dotenv_path=ENV_FILE_PATH, override=True)
ALLOWED_ORIGINS_ENV_VAR = "SHUDDHO_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://shuddho-web-editor.vercel.app",
]
ALLOWED_ORIGIN_REGEX = r"^(chrome-extension://[a-p]{32}|https?://(localhost|127\.0\.0\.1)(:\d+)?)$"
STARTUP_TIMESTAMP = datetime.now(timezone.utc)
LLM_PROVIDER_ENV_VAR = "SHUDDHO_LLM_PROVIDER"
LLM_ENABLED_ENV_VAR = "SHUDDHO_ENABLE_LLM"
OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_ENV_VAR = "OPENROUTER_MODEL"
LOG_RAW_TEXT_ENV_VAR = "SHUDDHO_LOG_RAW_TEXT"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
MAX_AI_CHECK_CHARS = int(os.environ.get("SHUDDHO_MAX_AI_TEXT_CHARS", "5000"))


class AiCheckRequest(BaseModel):
    text: str
    language: Literal["bn"] = "bn"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("text must not be empty")
        if len(value) > MAX_AI_CHECK_CHARS:
            raise ValueError(f"text too large; max {MAX_AI_CHECK_CHARS} chars")
        return value


class AiCheckResponse(BaseModel):
    suggestions: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str = "openrouter"
    model: str = DEFAULT_OPENROUTER_MODEL
    llm_enabled: bool = False


def _parse_allowed_origins(value: str | None) -> list[str]:
    allowed_origins = list(DEFAULT_ALLOWED_ORIGINS)
    if value is None or not value.strip():
        return allowed_origins

    for raw_origin in value.split(","):
        origin = raw_origin.strip()
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)
    return allowed_origins


def _resolve_backend_version(base_version: str) -> str:
    git_sha = _git_short_sha()
    if not git_sha:
        return base_version
    return f"{base_version}+git.{git_sha}"


def _git_short_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


logger.info(
    "Shuddho API environment env_file=%s exists=%s loaded=%s",
    ENV_FILE_PATH,
    ENV_FILE_PATH.is_file(),
    ENV_FILE_LOADED,
)
ALLOWED_ORIGINS = _parse_allowed_origins(os.environ.get(ALLOWED_ORIGINS_ENV_VAR))

app = FastAPI(title="Shuddho API", version="0.1.0")
BACKEND_VERSION = _resolve_backend_version(app.version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

normalizer = BanglaNormalizer()
spell_engine = SpellEngine(
    runtime_csv_path=REPO_ROOT / "data" / "runtime" / "lexicon" / "runtime_words.csv"
)
rule_engine = RuleEngine()
suggestion_manager = SuggestionManager()
detector_service = DetectorService.from_environment(os.environ)
corrector_service = CorrectorService.from_environment(os.environ)
candidate_generator = CandidateGenerator()
feedback_store = FeedbackStore()
ranking_pipeline = SuggestionRankingPipeline(feedback_store=feedback_store)
analysis_pipeline = AnalysisPipeline(
    normalizer=normalizer,
    spell_engine=spell_engine,
    rule_engine=rule_engine,
    suggestion_manager=suggestion_manager,
    detector_service=detector_service,
    corrector_service=corrector_service,
    candidate_generator=candidate_generator,
    ranking_pipeline=ranking_pipeline,
)
tone_analyzer = ToneAnalyzer()
analyze_cache: ContentHashCache[AnalyzeResponse] = ContentHashCache(ttl_seconds=8.0, max_entries=128)
rewrite_cache: ContentHashCache[RewriteResponse] = ContentHashCache(ttl_seconds=20.0, max_entries=64)
tone_cache: ContentHashCache[ToneAnalysisResponse] = ContentHashCache(ttl_seconds=20.0, max_entries=64)

class ApiPreferences(BaseModel):
    user_id: str = "demo-user"
    preferred_language_variant: str = "bangla"
    writing_goal: str = "general"
    tone_goal: str = "neutral"
    suggestion_density: str = "balanced"
    auto_show_tone: bool = True
    enable_rewrites: bool = True
    personal_dictionary: list[str] = Field(default_factory=list)
    suppressed_rule_keys: list[str] = Field(default_factory=list)
    disabled_sites: list[str] = Field(default_factory=list)
    language: Literal["bn"] = "bn"
    dialect: str = "standard"
    enabledSuggestionTypes: list[str] = Field(
        default_factory=lambda: [
            "grammar",
            "spelling",
            "punctuation",
            "spacing",
            "style",
            "tone",
            "rewrite",
        ]
    )
    disabledSuggestionTypes: list[str] = Field(default_factory=list)
    ignoredRuleIds: list[str] = Field(default_factory=list)
    ignoredSuggestionIds: list[str] = Field(default_factory=list)
    ignoredSuppressionKeys: list[str] = Field(default_factory=list)
    productImprovementConsent: bool = False


_preferences_store: dict[str, ApiPreferences] = {}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return _build_health_response()


@app.get("/health/deep", response_model=HealthDeepResponse)
def health_deep() -> HealthDeepResponse:
    return _build_health_deep_response()


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Shuddho API is running"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    preferences_service = _preferences_service()
    preferences = preferences_service.load(payload.user_id)
    stored_personal_dictionary = (
        feedback_store.load_personal_dictionary(user_id=payload.user_id)
        if hasattr(feedback_store, "load_personal_dictionary")
        else []
    )
    effective_personal_dictionary = _merge_personal_dictionaries(
        payload.personal_dictionary,
        stored_personal_dictionary,
        preferences.personal_dictionary if preferences is not None else [],
    )
    cache_key = analyze_cache.build_key(
        namespace="analyze",
        payload={
            "text": payload.text,
            "personal_dictionary": effective_personal_dictionary,
            "mode": payload.mode.value,
        },
    )
    response = analyze_cache.get_or_create(
        cache_key,
        lambda: analysis_pipeline.analyze(
            payload.text,
            effective_personal_dictionary,
            payload.mode,
        ),
    )
    response = response.model_copy(
        update={
            "backend_version": BACKEND_VERSION,
            "lexicon_source": spell_engine.lexicon_source,
            "lexicon_version": spell_engine.lexicon_version,
        }
    )
    suppressed_keys = feedback_store.load_suppressed_keys(user_id=payload.user_id)
    visible_suggestions = _filter_suppressed_suggestions(response.suggestions, suppressed_keys)
    visible_suggestions = preferences_service.filter_suggestions(visible_suggestions, preferences)
    return response.model_copy(
        update={
            "suggestions": visible_suggestions,
            "corrected_text": build_corrected_text(response.text, visible_suggestions),
        }
    )


@app.post("/feedback", response_model=FeedbackRecord)
def feedback(payload: FeedbackRequest) -> FeedbackRecord:
    return feedback_store.save(payload)




@app.get("/api/preferences", response_model=ApiPreferences)
def get_api_preferences(user_id: str = "demo-user") -> ApiPreferences:
    return _preferences_store.get(user_id, ApiPreferences(user_id=user_id))


@app.put("/api/preferences", response_model=ApiPreferences)
def put_api_preferences(payload: ApiPreferences, user_id: str = "demo-user") -> ApiPreferences:
    stored = payload.model_copy(update={"user_id": payload.user_id or user_id})
    _preferences_store[user_id] = stored
    return stored

@app.post("/api/check", response_model=CanonicalCheckResponse)
def check_canonical(payload: CanonicalCheckRequest) -> CanonicalCheckResponse:
    request_id = datetime.now(timezone.utc).isoformat()
    legacy = analyze(AnalyzeRequest(text=payload.text, user_id=payload.userId))
    response = analyze_to_check_response(
        legacy,
        request_id=request_id,
        text=payload.text,
        document_id=payload.documentId,
        revision=payload.revision,
    )
    llm_requested = _should_run_llm(payload)
    ai = _run_ai_check(payload.text, request_id) if llm_requested else AiCheckResponse(
        suggestions=[],
        warnings=[],
        provider="openrouter",
        model=_llm_config()[2],
        llm_enabled=_llm_config()[0],
    )
    response_payload = response.model_dump(mode="json")
    seen = {
        (
            item.get("originalText"),
            item.get("suggestedText"),
            (item.get("span") or {}).get("startIndex"),
        )
        for item in response_payload["suggestions"]
    }
    for item in ai.suggestions:
        if not isinstance(item, dict):
            response_payload["warnings"].append("openrouter_invalid_suggestion_shape")
            continue
        span_start = item.get("span_start")
        span_end = item.get("span_end")
        if not isinstance(span_start, int) or not isinstance(span_end, int):
            response_payload["warnings"].append("openrouter_suggestion_missing_span")
            continue
        if span_start < 0 or span_end <= span_start or span_end > len(payload.text):
            response_payload["warnings"].append("openrouter_suggestion_invalid_span")
            continue
        key = (item["originalText"], item["suggestedText"], span_start)
        if key in seen:
            continue
        seen.add(key)
        response_payload["suggestions"].append(
            {
                "id": item["id"],
                "suppressionKey": f"openrouter:{item['id']}",
                "ruleId": item["rule_id"],
                "type": item["type"],
                "severity": "medium",
                "originalText": item["originalText"],
                "suggestedText": item["suggestedText"],
                "replacementOptions": item["replacement_options"],
                "explanationBn": item["explanationBn"],
                "explanationEn": None,
                "span": {"startIndex": span_start, "endIndex": span_end},
                "confidence": item["confidence"],
                "source": "model",
                "provider": "openrouter",
                "metadata": {"source": "openrouter"},
            }
        )
    ai_warnings = list(ai.warnings)
    if "llm_disabled" in ai_warnings and not llm_requested:
        ai_warnings = [warning for warning in ai_warnings if warning != "llm_disabled"]
    response_payload["warnings"] = _dedupe_strings([*response_payload["warnings"], *ai_warnings])
    response_payload["llm_requested"] = llm_requested
    response_payload["llm_attempted"] = bool(llm_requested)
    response_payload["llm_used"] = bool(
        llm_requested
        and ai.llm_enabled
        and ai.provider == "openrouter"
        and "llm_requested_but_not_successful" not in response_payload["warnings"]
    )
    response_payload["llm_model"] = ai.model
    response_payload["local_suggestion_count"] = len(response.suggestions)
    response_payload["ai_suggestion_count"] = len(ai.suggestions)
    return CanonicalCheckResponse(**response_payload)


@app.post("/api/ai/check", response_model=AiCheckResponse)
def ai_check(payload: AiCheckRequest) -> AiCheckResponse:
    request_id = datetime.now(timezone.utc).isoformat()
    return _run_ai_check(payload.text, request_id)


@app.post("/rewrite", response_model=RewriteResponse)
def rewrite(payload: RewriteRequest) -> RewriteResponse:
    preferences = _preferences_service().load(payload.user_id)
    cache_key = rewrite_cache.build_key(
        namespace="rewrite",
        payload={
            "request": payload.model_dump(mode="json"),
            "preferences": preferences.model_dump(mode="json") if preferences is not None else None,
        },
    )
    response = rewrite_cache.get_or_create(
        cache_key,
        lambda: _rewrite_service().rewrite(payload, preferences),
    )
    degraded_reasons = _derive_degraded_reasons(
        detector_service.runtime_status(),
        corrector_service.runtime_status(),
    )
    if not degraded_reasons:
        return response
    return response.model_copy(
        update={
            "warnings": _dedupe_strings([*response.warnings, *degraded_reasons]),
        }
    )


@app.post("/tone/analyze", response_model=ToneAnalysisResponse)
def analyze_tone(payload: ToneAnalysisRequest) -> ToneAnalysisResponse:
    cache_key = tone_cache.build_key(
        namespace="tone",
        payload=payload.model_dump(mode="json"),
    )
    return tone_cache.get_or_create(
        cache_key,
        lambda: tone_analyzer.analyze(payload.text),
    )


@app.post("/api/rewrite", response_model=RewriteResponse)
def rewrite_api(payload: RewriteRequest) -> RewriteResponse:
    return rewrite(payload)


@app.post("/api/tone", response_model=ToneAnalysisResponse)
def tone_api(payload: ToneAnalysisRequest) -> ToneAnalysisResponse:
    return analyze_tone(payload)


@app.post("/api/events")
def events_api(payload: dict) -> dict[str, bool]:
    return {"ok": True}


@app.get("/preferences/{user_id}", response_model=UserPreferences)
def get_preferences(user_id: str) -> UserPreferences:
    return _preferences_service().load(user_id) or UserPreferences(user_id=user_id)


@app.post("/preferences/{user_id}", response_model=UserPreferences)
def save_preferences(user_id: str, payload: UserPreferences) -> UserPreferences:
    return _preferences_service().save(user_id, payload)


def _merge_personal_dictionaries(*sources: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for entry in source:
            normalized = " ".join(entry.split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _filter_suppressed_suggestions(suggestions: list[Suggestion], suppressed_keys: set[str]) -> list[Suggestion]:
    return [
        suggestion
        for suggestion in suggestions
        if suggestion.suppression_key not in suppressed_keys
    ]


def _preferences_service() -> UserPreferencesService:
    return UserPreferencesService(feedback_store)


def _llm_config() -> tuple[bool, str, str, str | None]:
    provider = os.environ.get(LLM_PROVIDER_ENV_VAR, "openrouter").strip().lower() or "openrouter"
    model = os.environ.get(OPENROUTER_MODEL_ENV_VAR, DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
    raw_api_key = os.environ.get(OPENROUTER_API_KEY_ENV_VAR)
    api_key = raw_api_key.strip() if raw_api_key else None
    raw_enabled = os.environ.get(LLM_ENABLED_ENV_VAR)
    if raw_enabled is None or raw_enabled.strip().lower() in {"", "auto"}:
        enabled = bool(api_key)
    else:
        enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
    return enabled, provider, model, api_key


def _should_run_llm(payload: object) -> bool:
    options = getattr(payload, "options", None) or {}
    if not isinstance(options, dict):
        return False

    return bool(
        options.get("includeLLM")
        or options.get("includeAi")
        or options.get("includeAI")
        or options.get("ai")
        or options.get("llm")
    )


def _log_raw_text_enabled() -> bool:
    return os.environ.get(LOG_RAW_TEXT_ENV_VAR, "false").strip().lower() == "true"


def _run_ai_check(text: str, request_id: str) -> AiCheckResponse:
    enabled, provider, model, api_key = _llm_config()
    if not enabled:
        return AiCheckResponse(warnings=["llm_disabled"], provider="openrouter", model=model, llm_enabled=False)
    if provider != "openrouter":
        return AiCheckResponse(warnings=["unsupported_llm_provider"], provider="openrouter", model=model, llm_enabled=True)
    if not api_key:
        return AiCheckResponse(warnings=["openrouter_api_key_missing"], provider="openrouter", model=model, llm_enabled=True)
    timeout_seconds = float(os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "35") or "35")
    result = run_openrouter_check(text=text, model=model, api_key=api_key, timeout_seconds=timeout_seconds)
    logger.info("ai_check_complete request_id=%s text_length=%s warnings=%s suggestion_count=%s", request_id, len(text), len(result.get("warnings", [])), len(result.get("suggestions", [])))
    return AiCheckResponse(
        suggestions=result.get("suggestions", []),
        warnings=_dedupe_strings(result.get("warnings", [])),
        provider="openrouter",
        model=model,
        llm_enabled=True,
    )


def _rewrite_service() -> RewriteService:
    return RewriteService(analysis_pipeline)


def _build_health_response() -> HealthResponse:
    detector_runtime = detector_service.runtime_status()
    corrector_runtime = corrector_service.runtime_status()
    analysis_profile = _derive_analysis_profile(detector_runtime, corrector_runtime)
    degraded_reasons = _derive_degraded_reasons(detector_runtime, corrector_runtime)
    return HealthResponse(
        status="ok",
        backend_reachable=True,
        detector_loaded=detector_runtime.loaded,
        detector_checkpoint=detector_runtime.checkpoint,
        corrector_loaded=corrector_runtime.loaded,
        corrector_checkpoint=corrector_runtime.checkpoint,
        allowed_origins=ALLOWED_ORIGINS,
        detector=DetectorHealth(
            enabled=detector_runtime.enabled,
            loaded=detector_runtime.loaded,
            status=detector_runtime.status,
            reason=detector_runtime.reason,
            checkpoint=detector_runtime.checkpoint,
            checkpoint_exists=detector_runtime.checkpoint_exists,
            backend_name=detector_runtime.backend_name,
            threshold=detector_runtime.threshold,
        ),
        corrector=_build_corrector_health(corrector_runtime),
        analysis_profile=analysis_profile,
        degraded_reasons=degraded_reasons,
        mode_capabilities=_build_mode_capabilities(detector_runtime, corrector_runtime),
    )


def _build_health_deep_response() -> HealthDeepResponse:
    shallow = _build_health_response()
    snapshot = spell_engine.repository.snapshot
    return HealthDeepResponse(
        **shallow.model_dump(),
        backend_warning=_derive_backend_warning(detector_service.runtime_status(), corrector_service.runtime_status()),
        backend_version=BACKEND_VERSION,
        env_file_path=str(ENV_FILE_PATH),
        env_file_loaded=ENV_FILE_LOADED,
        last_startup_timestamp=STARTUP_TIMESTAMP,
        llm={
            "enabled": _llm_config()[0],
            "provider": _llm_config()[1],
            "model": _llm_config()[2],
            "configured": bool(_llm_config()[3]),
        },
        lexicon=LexiconHealth(
            runtime_source_of_truth=snapshot.runtime_source_of_truth,
            runtime_source=spell_engine.lexicon_source,
            runtime_path=str(spell_engine.lexicon_runtime_path) if spell_engine.lexicon_runtime_path is not None else None,
            runtime_exists=spell_engine.lexicon_runtime_exists,
            version=spell_engine.lexicon_version,
            checksum=spell_engine.lexicon_checksum,
            accepted_word_count=spell_engine.lexicon_row_counts["accepted_words"],
            candidate_word_count=spell_engine.lexicon_row_counts["candidate_words"],
            correction_map_count=spell_engine.lexicon_row_counts["correction_map"],
            import_database_path=(
                str(spell_engine.lexicon_import_database_path)
                if spell_engine.lexicon_import_database_path is not None
                else None
            ),
            import_database_exists=spell_engine.lexicon_import_database_exists,
            loaded_at=spell_engine.lexicon_loaded_at,
            reload_supported=True,
            restart_required=True,
        ),
    )


def _build_corrector_health(corrector_runtime: CorrectorRuntimeStatus) -> CorrectorHealth:
    return CorrectorHealth(
        enabled=corrector_runtime.enabled,
        loaded=corrector_runtime.loaded,
        status=corrector_runtime.status,
        reason=corrector_runtime.reason,
        checkpoint=corrector_runtime.checkpoint,
        checkpoint_exists=corrector_runtime.checkpoint_exists,
        backend_name=corrector_runtime.backend_name,
        threshold=corrector_runtime.threshold,
    )


def _derive_analysis_profile(
    detector_runtime: DetectorRuntimeStatus,
    corrector_runtime: CorrectorRuntimeStatus,
) -> AnalysisProfile:
    if detector_runtime.loaded and corrector_runtime.loaded:
        return AnalysisProfile.FULL_LOCAL
    if detector_runtime.loaded:
        return AnalysisProfile.BACKEND_WITHOUT_CORRECTOR
    if corrector_runtime.loaded:
        return AnalysisProfile.BACKEND_WITHOUT_DETECTOR
    return AnalysisProfile.BACKEND_RULES_AND_SPELL_ONLY


def _derive_degraded_reasons(
    detector_runtime: DetectorRuntimeStatus,
    corrector_runtime: CorrectorRuntimeStatus,
) -> list[str]:
    degraded_reasons: list[str] = []
    if detector_runtime.status != "ready":
        degraded_reasons.append(f"detector_{detector_runtime.status}")
    if corrector_runtime.status != "ready":
        degraded_reasons.append(f"corrector_{corrector_runtime.status}")
    return degraded_reasons


def _build_mode_capabilities(
    detector_runtime: DetectorRuntimeStatus,
    corrector_runtime: CorrectorRuntimeStatus,
) -> dict[str, list[str]]:
    base_capabilities = {
        "standard": [
            "rules",
            "spell",
            "deterministic_candidate_generation",
            "feedback_adaptation",
            "low_noise_visibility",
            "tone_analysis",
            "rewrite_service",
        ],
        "strict": [
            "rules",
            "spell",
            "deterministic_candidate_generation",
            "feedback_adaptation",
            "broader_contextual_visibility",
            "orthography_variants",
            "tone_analysis",
            "rewrite_service",
        ],
        "formal": [
            "rules",
            "spell",
            "deterministic_candidate_generation",
            "feedback_adaptation",
            "broader_contextual_visibility",
            "orthography_variants",
            "formal_style_guidance",
            "tone_analysis",
            "rewrite_service",
        ],
    }

    if detector_runtime.loaded:
        for capabilities in base_capabilities.values():
            capabilities.append("detector_span_corroboration")
    else:
        for capabilities in base_capabilities.values():
            capabilities.append("detector_not_loaded")

    if corrector_runtime.loaded:
        for capabilities in base_capabilities.values():
            capabilities.append("sentence_level_local_corrector")
            capabilities.append("inline_corrector_span_projection")
    else:
        for capabilities in base_capabilities.values():
            capabilities.append("sentence_level_corrector_unavailable")

    return base_capabilities


def _derive_backend_warning(
    detector_runtime: DetectorRuntimeStatus,
    corrector_runtime: CorrectorRuntimeStatus,
) -> str | None:
    if corrector_runtime.status != "ready":
        return "Sentence-level corrector is not loaded. Shuddho is running rules + spelling only."
    if detector_runtime.status != "ready":
        return "Detector is not loaded. Shuddho is using rules, spelling, and exact span anchors only."
    return None


def _dedupe_strings(values: list[str]) -> list[str]:
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        compact.append(normalized)
    return compact


detector_runtime = detector_service.runtime_status()
corrector_runtime = corrector_service.runtime_status()
analysis_profile = _derive_analysis_profile(detector_runtime, corrector_runtime)
degraded_reasons = _derive_degraded_reasons(detector_runtime, corrector_runtime)

logger.info(
    "Shuddho API startup env_file=%s detector_status=%s detector_reason=%s detector_checkpoint=%s detector_checkpoint_exists=%s "
    "corrector_status=%s corrector_reason=%s corrector_checkpoint=%s corrector_checkpoint_exists=%s analysis_profile=%s degraded_reasons=%s allowed_origins=%s backend_version=%s",
    ENV_FILE_PATH,
    detector_runtime.status,
    detector_runtime.reason,
    detector_runtime.checkpoint,
    detector_runtime.checkpoint_exists,
    corrector_runtime.status,
    corrector_runtime.reason,
    corrector_runtime.checkpoint,
    corrector_runtime.checkpoint_exists,
    analysis_profile.value,
    degraded_reasons,
    ALLOWED_ORIGINS,
    BACKEND_VERSION,
)
if degraded_reasons:
    logger.warning(
        "Shuddho API is running in degraded local analysis mode reasons=%s detector_fix=%s corrector_fix=%s",
        degraded_reasons,
        f"Set {DetectorService.__name__} checkpoint via SHUDDHO_DETECTOR_CHECKPOINT or create {DetectorService._configured_checkpoint_path(None)}",
        "Set SHUDDHO_CORRECTOR_CHECKPOINT or train with 'python -m ml.corrector.train --config ml/training/configs/corrector.base.json'",
    )
