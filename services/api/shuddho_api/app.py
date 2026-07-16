from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
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
from services.api.shuddho_api.llm_openai import DEFAULT_OPENAI_MODEL, run_openai_check
from services.api.shuddho_api.llm_gemini import DEFAULT_GEMINI_MODEL, run_gemini_check
from services.api.shuddho_api.llm_candidates import build_llm_candidates, split_bangla_sentences
from services.api.shuddho_api.llm_provider import resolve_llm_config, LlmProviderResult
from services.api.shuddho_api.suggestion_merge import merge_suggestions, validate_ai_suggestions
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


def _load_dotenv_file(path: Path) -> bool:
    if not path.is_file():
        return False
    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
        loaded = True
    return loaded

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = REPO_ROOT / ".env"
ENV_FILE_LOADED = _load_dotenv_file(ENV_FILE_PATH)
ALLOWED_ORIGINS_ENV_VAR = "SHUDDHO_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://shuddho-web-editor.vercel.app",
]
ALLOWED_ORIGIN_REGEX = (
    r"^(chrome-extension://[a-p]{32}|https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app)$"
    if os.environ.get("SHUDDHO_ALLOW_VERCEL_PREVIEWS", "false").strip().lower() in {"1", "true", "yes", "on"}
    else r"^(chrome-extension://[a-p]{32}|https?://(localhost|127\.0\.0\.1)(:\d+)?)$"
)
STARTUP_TIMESTAMP = datetime.now(timezone.utc)
LLM_PROVIDER_ENV_VAR = "SHUDDHO_LLM_PROVIDER"
LLM_ENABLED_ENV_VAR = "SHUDDHO_ENABLE_LLM"
OPENROUTER_API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
OPENAI_MODEL_ENV_VAR = "OPENAI_MODEL"
OPENROUTER_MODEL_ENV_VAR = "OPENROUTER_MODEL"
LOG_RAW_TEXT_ENV_VAR = "SHUDDHO_LOG_RAW_TEXT"
DEFAULT_OPENROUTER_MODEL = ""
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
    correctedText: str | None = None
    documentAssessment: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    provider: str = "gemini"
    model: str = DEFAULT_GEMINI_MODEL
    llm_enabled: bool = False
    configured: bool = False
    called: bool = False
    parsed: bool = False
    status: str = "skipped"
    response_mode: str = "none"
    http_status: int | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    timings: dict[str, float] = Field(default_factory=dict)
    ai_raw_suggestion_count: int = 0


class ApiCheckRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    text: str = Field(..., min_length=1)
    language: str = "bn"
    documentId: str | None = None
    document_id: str | None = None
    revision: int | None = None
    dialect: str | None = None
    userId: str | None = None
    user_id: str | None = None
    client: dict[str, Any] | None = None
    consent: dict[str, Any] | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: Any) -> str:
        if value is None or value == "":
            return "bn"
        normalized = str(value).lower()
        if normalized in {"bangla", "bengali", "bn-bd", "bn_bd", "bn-in", "bn_in"}:
            return "bn"
        return normalized

    @field_validator("options", mode="before")
    @classmethod
    def normalize_options(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return {}


def _parse_allowed_origins(value: str | None) -> list[str]:
    allowed_origins = list(DEFAULT_ALLOWED_ORIGINS)
    if value is None or not value.strip():
        return allowed_origins

    for raw_origin in value.split(","):
        origin = raw_origin.strip().rstrip("/")
        if not origin or origin == "*":
            continue
        if origin not in allowed_origins:
            allowed_origins.append(origin)
    return allowed_origins


def _safe_timings(timings: dict | None) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    if not isinstance(timings, dict):
        return clean

    for key, value in timings.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean[str(key)] = value
            continue
        try:
            clean[str(key)] = float(value)
        except (TypeError, ValueError):
            continue

    return clean


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


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    log_raw_text = os.environ.get("SHUDDHO_LOG_RAW_TEXT", "false").lower() == "true"
    body_info = "<hidden>"
    if log_raw_text:
        try:
            raw_body = await request.body()
            body_info = raw_body.decode("utf-8", errors="replace")[:2000]
        except Exception:
            body_info = "<unavailable>"
    logger.error(
        "REQUEST_VALIDATION_ERROR path=%s method=%s errors=%s body=%s",
        request.url.path,
        request.method,
        exc.errors(),
        body_info,
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "request_validation_error",
            "message": "Request body did not match backend schema.",
            "detail": exc.errors(),
        },
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["content-type", "authorization", "x-request-id", "x-user-id", "x-tenant-id"],
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
llm_jobs: dict[str, dict] = {}
llm_cache: dict[str, dict] = {}
llm_failures: dict[str, list[float]] = {}
llm_circuit_until: dict[str, float] = {}

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


@app.get("/version")
def version() -> dict[str, str]:
    commit = (
        os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("SOURCE_VERSION")
        or _git_short_sha()
        or "unknown"
    )
    build_time = os.environ.get("BUILD_TIME") or STARTUP_TIMESTAMP.isoformat()
    return {
        "commit": commit,
        "build_time": build_time,
        "llm_pipeline_version": "validation-fix-v1",
    }


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
def check_canonical(payload: ApiCheckRequest) -> CanonicalCheckResponse:
    normalized = _normalize_api_check_payload(payload)
    all_options = normalized.get("options") or {}
    include_llm = _should_run_llm(all_options)
    async_llm = _should_run_async_llm(all_options)
    llm_mode = _llm_mode(all_options, include_llm)
    canonical_normalized = {**normalized, "options": _canonical_bool_options(all_options)}
    try:
        canonical_payload = CanonicalCheckRequest(**canonical_normalized)
    except ValidationError as exc:
        logger.error("CANONICAL_PAYLOAD_VALIDATION_ERROR errors=%s", exc.errors())
        return JSONResponse(status_code=422, content={"error": "canonical_payload_validation_error", "message": "Normalized request still failed internal schema validation.", "detail": exc.errors()})

    started_at = time.time()
    request_id = datetime.now(timezone.utc).isoformat()
    logger.info("CHECK_START request_id=%s text_length=%s includeLLM=%s asyncLLM=%s mode=%s", request_id, len(canonical_payload.text), include_llm, async_llm, llm_mode)

    local_started = time.time()
    legacy = analyze(AnalyzeRequest(text=canonical_payload.text, user_id=canonical_payload.userId))
    local_ms = int((time.time() - local_started) * 1000)
    response = analyze_to_check_response(legacy, request_id=request_id, text=canonical_payload.text, document_id=canonical_payload.documentId, revision=canonical_payload.revision)
    response_payload = response.model_dump(mode="json")
    local_suggestions = list(response_payload.get("suggestions") or [])
    local_count = len(local_suggestions)
    detector_runtime = detector_service.runtime_status()
    corrector_runtime = corrector_service.runtime_status()
    local_runtime_warnings = response_payload.get("warnings") or []
    corrector_missing_warning = (
        "sentence_level_corrector_unavailable"
        if (corrector_runtime.status != "ready" or not corrector_runtime.loaded)
        and "corrector_missing_checkpoint" not in local_runtime_warnings
        else None
    )

    config = resolve_llm_config(os.environ)
    llm_env_mode = os.environ.get("SHUDDHO_LLM_ON_CHECK", "manual").strip().lower()
    llm_requested = include_llm or llm_env_mode in {"always", "true"}
    if llm_requested and not include_llm and llm_env_mode in {"always", "true"} and llm_mode in {"none", "fast"}:
        llm_mode = "review_candidates"
    llm_allowed, llm_reason = _llm_allowed_on_check(llm_requested)
    ai = AiCheckResponse(provider=config.provider, model=config.model, llm_enabled=config.enabled, configured=config.configured, warnings=list(config.warnings), status="skipped")
    validated_ai: list[dict[str, Any]] = []
    merge_warnings: list[str] = []
    llm_ms: float | None = None
    job_id: str | None = None
    rejected_count = 0
    raw_ai_count = 0
    ai_empty_reason: str | None = None

    llm_block: dict[str, Any] = {
        "requested": llm_requested,
        "attempted": False,
        "used": False,
        "status": "skipped",
        "provider": config.provider,
        "model": config.model,
        "job_id": None,
        "warnings": list(config.warnings),
        "error": None,
        "cache_hit": False,
        "mode": llm_mode,
        "called": False,
        "configured": config.configured,
        "parsed": False,
        "http_status": None,
        "response_mode": "none",
        "llm_ms": None,
        "skip_reason": None,
    }

    if not llm_requested:
        ai.status = "skipped"
        llm_block["skip_reason"] = "include_llm_false"
        ai.warnings = []
    elif not llm_allowed:
        ai.status = "skipped"
        llm_block["skip_reason"] = llm_reason
    elif not canonical_payload.text.strip():
        ai.status = "skipped"
        ai.warnings.append("llm_empty_text_skipped")
        llm_block["skip_reason"] = "empty_text"
    elif not config.enabled or config.status in {"disabled", "missing_key", "unsupported_provider"} or not config.configured:
        ai.status = config.status
        ai.warnings = _dedupe_strings([*ai.warnings, *(config.warnings or [])])
        llm_block.update({"status": ai.status, "warnings": ai.warnings, "error": ai.warnings[0] if ai.warnings else None})
    elif async_llm:
        job = _create_llm_review_job(canonical_payload.text, canonical_payload.language, local_suggestions, llm_mode, request_id=request_id)
        job_id = job["job_id"]
        ai.status = "attempted"
        llm_block.update({"status": "queued", "job_id": job_id, "used": False, "attempted": True})
    else:
        llm_started = time.time()
        ai = _run_ai_check(canonical_payload.text, request_id, local_suggestions=local_suggestions, timeout_seconds=float(os.environ.get("SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS", os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "45")) or "45"))
        llm_ms = float(int((time.time() - llm_started) * 1000))
        llm_block.update({"status": ai.status, "warnings": list(ai.warnings), "error": ai.warnings[0] if ai.warnings and ai.status not in {"completed", "completed_empty"} else None, "llm_ms": llm_ms, "attempted": bool(ai.called)})
        if ai.status in {"completed", "completed_empty"}:
            sentences = _sentences_for_ai(canonical_payload.text)
            raw_ai_count = int(ai.ai_raw_suggestion_count or len(ai.suggestions or []))
            validated_ai, validation_warnings = validate_ai_suggestions(canonical_payload.text, ai.suggestions, sentences)
            rejected_count = max(0, raw_ai_count - len(validated_ai))
            if raw_ai_count == 0:
                ai_empty_reason = "model_returned_no_suggestions"
            elif not validated_ai:
                ai_empty_reason = "all_ai_suggestions_rejected"
            if ai.suggestions and rejected_count == len(ai.suggestions):
                validation_warnings = _dedupe_strings([*validation_warnings, "ai_suggestions_rejected"])
                ai.status = "completed_rejected"
            elif ai.status == "completed" and not validated_ai:
                ai.status = "completed_empty"
            merged_suggestions, merge_warnings = merge_suggestions(canonical_payload.text, local_suggestions, validated_ai, ai.provider, ai.model)
            response_payload["suggestions"] = merged_suggestions
            llm_block["used"] = ai.called and ai.parsed
            ai.warnings = _dedupe_strings([*ai.warnings, *validation_warnings, *merge_warnings])
        elif ai.status in {"timeout", "invalid_json", "invalid_schema", "provider_error", "auth_or_forbidden", "credits_or_payment_required", "model_not_found", "content_filter", "network_error", "rate_limited", "failed"}:
            ai_empty_reason = ai.status
            _record_llm_failure(ai.provider, ai.model, ai.warnings or [ai.status])

    all_warnings = _dedupe_strings([
        *(response_payload.get("warnings") or []),
        *([corrector_missing_warning] if corrector_missing_warning else []),
        *ai.warnings,
        *merge_warnings,
    ])
    if llm_requested and ai.status not in {"completed", "completed_empty", "completed_rejected", "skipped", "attempted"} and not all_warnings:
        all_warnings.append(f"llm_{ai.status}")
    response_payload["warnings"] = all_warnings
    response_payload["llm_requested"] = llm_requested
    response_payload["llm_attempted"] = bool(ai.called or async_llm and job_id)
    response_payload["llm_used"] = bool(ai.status in {"completed", "completed_empty", "completed_rejected"} and ai.called and ai.parsed)
    response_payload["llm_model"] = ai.model
    response_payload["llm_status"] = ai.status if not (async_llm and job_id) else "queued"
    response_payload["llm_provider"] = ai.provider
    response_payload["llm_response_mode"] = ai.response_mode or llm_mode
    response_payload["rejected_ai_suggestion_count"] = rejected_count
    response_payload["ai_raw_suggestion_count"] = raw_ai_count
    response_payload["ai_valid_suggestion_count"] = len(validated_ai)
    response_payload["ai_rejected_suggestion_count"] = rejected_count
    response_payload["ai_empty_reason"] = ai_empty_reason
    response_payload["correctedText"] = ai.correctedText if ai.status in {"completed", "completed_empty"} and ai.correctedText and "llm_text_truncated" not in ai.warnings else response_payload.get("correctedText") or canonical_payload.text
    response_payload["documentAssessment"] = ai.documentAssessment if ai.status in {"completed", "completed_empty", "completed_rejected"} and ai.documentAssessment else response_payload.get("documentAssessment") or {}
    timings: dict[str, int | float | bool] = {
        "local_ms": local_ms,
        "llm_ms": llm_ms or 0,
        "total_ms": int((time.time() - started_at) * 1000),
        "cache_hit": bool(ai.timings.get("cache_hit")),
    }
    response_payload["timings"] = _safe_timings(timings)
    llm_block.update({
        "status": response_payload["llm_status"],
        "provider": ai.provider,
        "model": ai.model,
        "warnings": all_warnings if ai.status not in {"completed", "completed_empty"} else ai.warnings,
        "rejection_warnings": [warning for warning in all_warnings if warning.startswith("ai_suggestion") or warning == "ai_suggestions_rejected"],
        "called": ai.called,
        "configured": ai.configured,
        "parsed": ai.parsed,
        "http_status": ai.http_status,
        "response_mode": ai.response_mode,
        "llm_ms": llm_ms,
        "timings": ai.timings,
        "cache_hit": bool(ai.timings.get("cache_hit")),
        "attempted": response_payload["llm_attempted"],
        "ai_raw_suggestion_count": raw_ai_count,
        "ai_valid_suggestion_count": len(validated_ai),
        "ai_rejected_suggestion_count": rejected_count,
        "ai_empty_reason": ai_empty_reason,
    })
    response_payload["llm"] = llm_block
    response_payload["local_suggestion_count"] = local_count
    response_payload["ai_suggestion_count"] = len(validated_ai)
    response_payload["diagnostics"] = {
        "backendReachable": True,
        "backendStatus": "ok",
        "detectorLoaded": detector_runtime.loaded,
        "correctorLoaded": corrector_runtime.loaded,
        "correctorReason": corrector_runtime.reason,
        "llmEnabled": config.enabled,
        "llmConfigured": config.configured,
        "llmProvider": config.provider,
        "llmModel": config.model,
        "ai_raw_suggestion_count": raw_ai_count,
        "ai_valid_suggestion_count": len(validated_ai),
        "ai_rejected_suggestion_count": rejected_count,
        "ai_empty_reason": ai_empty_reason,
        "llm": {
            "requested": response_payload["llm_requested"],
            "attempted": response_payload["llm_attempted"],
            "used": response_payload["llm_used"],
            "status": response_payload["llm_status"],
            "provider": ai.provider,
            "model": ai.model,
            "called": ai.called,
            "configured": ai.configured,
            "parsed": ai.parsed,
            "http_status": ai.http_status,
            "rejected_ai_suggestion_count": rejected_count,
            "ai_raw_suggestion_count": raw_ai_count,
            "ai_valid_suggestion_count": len(validated_ai),
            "ai_rejected_suggestion_count": rejected_count,
            "ai_empty_reason": ai_empty_reason,
            "response_mode": ai.response_mode,
            "warnings": all_warnings,
            "rejection_warnings": [warning for warning in all_warnings if warning.startswith("ai_suggestion") or warning == "ai_suggestions_rejected"],
            "error": llm_block.get("error"),
            "skip_reason": llm_block.get("skip_reason"),
            "llm_ms": llm_ms,
            "timings": ai.timings,
            "cache_hit": bool(ai.timings.get("cache_hit")),
            "job_id": job_id,
        },
        "local": {"local_engine_mode": os.environ.get("SHUDDHO_LOCAL_ENGINE_MODE", "fallback"), "suggestion_count": local_count},
    }
    logger.info(
        "CHECK_LLM_STATUS request_id=%s includeLLM=%s llm_requested=%s llm_attempted=%s llm_used=%s llm_status=%s llm_provider=%s llm_model=%s llm_http_status=%s local_suggestion_count=%s ai_suggestion_count=%s rejected_ai_suggestion_count=%s warnings=%s",
        request_id,
        include_llm,
        response_payload["llm_requested"],
        response_payload["llm_attempted"],
        response_payload["llm_used"],
        response_payload["llm_status"],
        ai.provider,
        ai.model,
        ai.http_status,
        local_count,
        len(validated_ai),
        rejected_count,
        all_warnings,
    )
    logger.info("LLM_MERGE_DONE request_id=%s provider=%s model=%s status=%s http_status=%s local_count=%s ai_count=%s rejected_count=%s total_count=%s timings=%s warnings=%s", request_id, ai.provider, ai.model, response_payload["llm_status"], ai.http_status, local_count, len(validated_ai), rejected_count, len(response_payload.get("suggestions") or []), response_payload["timings"], all_warnings)
    try:
        return CanonicalCheckResponse(**response_payload)
    except ValidationError as exc:
        logger.error("CANONICAL_RESPONSE_VALIDATION_ERROR errors=%s response_keys=%s", exc.errors(), list(response_payload.keys()))
        response_payload["warnings"] = _dedupe_strings([*(response_payload.get("warnings") or []), "canonical_response_validation_error"])
        return JSONResponse(status_code=200, content=jsonable_encoder(response_payload))


@app.post("/api/ai/check", response_model=AiCheckResponse)
def ai_check(payload: AiCheckRequest) -> AiCheckResponse:
    request_id = datetime.now(timezone.utc).isoformat()
    logger.info("CHECK_START request_id=%s text_length=%s includeLLM=%s asyncLLM=%s mode=%s", request_id, len(payload.text), True, False, "review_candidates")
    return _run_ai_check(payload.text, request_id)


class LlmReviewRequest(BaseModel):
    text: str
    language: Literal["bn"] = "bn"
    local_suggestions: list[dict] = Field(default_factory=list)
    mode: str = "review_candidates"
    request_id: str | None = None


@app.post("/api/llm/review")
def create_llm_review(payload: LlmReviewRequest) -> dict:
    return _create_llm_review_job(payload.text, payload.language, payload.local_suggestions, payload.mode, payload.request_id)


@app.get("/api/llm/review/{job_id}")
def get_llm_review(job_id: str) -> dict:
    _cleanup_llm_jobs()
    return llm_jobs.get(job_id, {"job_id": job_id, "status": "failed", "suggestions": [], "warnings": ["llm_job_not_found"]})


@app.get("/api/llm/debug")
def llm_debug() -> dict:
    config = resolve_llm_config(os.environ)
    primary = _provider_safe_state(config.provider, config.model, config.configured, config.api_key, config.status, config.warnings)
    fallback = _provider_safe_state(config.fallback_provider, config.fallback_model, config.fallback_configured, config.fallback_api_key, config.fallback_status, config.fallback_warnings)
    debug_status = "ready" if config.enabled and config.configured and not _is_circuit_open(config.provider, config.model) else config.status
    return {
        "enabled": config.enabled,
        "configured": config.configured,
        "provider": config.provider,
        "model": config.model,
        "status": debug_status,
        "warnings": list(config.warnings),
        "api_key_present": bool(config.api_key),
        "has_api_key": bool(config.api_key),
        "primary": primary,
        "fallback": fallback,
        "fallback_provider": config.fallback_provider,
        "fallback_model": config.fallback_model,
        "fallback_configured": config.fallback_configured,
        "on_check": os.environ.get("SHUDDHO_LLM_ON_CHECK", "manual").strip().lower(),
        "endpoint": "https://generativelanguage.googleapis.com" if config.provider == "gemini" else ("https://openrouter.ai/api/v1/chat/completions" if config.provider == "openrouter" else "https://api.openai.com/v1/responses"),
        "interactive_timeout_seconds": float(os.environ.get("SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS", os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "45"))),
        "background_timeout_seconds": float(os.environ.get("SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS", "60")),
        "timeout_seconds": float(os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "35")),
        "cache_ttl_seconds": int(os.environ.get("SHUDDHO_LLM_CACHE_TTL_SECONDS", "86400")),
        "timeout_settings": {
            "interactive_seconds": float(os.environ.get("SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS", os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "45"))),
            "background_seconds": float(os.environ.get("SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS", "60")),
            "default_seconds": float(os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "35")),
        },
        "circuit_open": _is_circuit_open(config.provider, config.model),
        "circuit_state": "open" if _is_circuit_open(config.provider, config.model) else "closed",
        "max_candidates": int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATES", "8")),
        "max_candidate_chars": int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATE_CHARS", "2200")),
        "max_ai_text_chars": int(os.environ.get("SHUDDHO_MAX_AI_TEXT_CHARS", "5000")),
    }


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
    config = resolve_llm_config(os.environ)
    return config.enabled, config.provider, config.model, config.api_key


def _provider_safe_state(provider: str | None, model: str, configured: bool, api_key: str | None, status: str, warnings: list[str]) -> dict[str, Any] | None:
    if not provider:
        return None
    return {
        "provider": provider,
        "model": model,
        "configured": configured,
        "api_key_present": bool(api_key),
        "circuit_open": _is_circuit_open(provider, model),
        "status": "ready" if configured and not _is_circuit_open(provider, model) else status,
        "warnings": list(warnings),
        "last_failure_count": len(llm_failures.get(f"{provider}:{model}", [])),
    }


def _llm_safe_status() -> dict[str, Any]:
    config = resolve_llm_config(os.environ)
    primary = _provider_safe_state(config.provider, config.model, config.configured, config.api_key, config.status, config.warnings)
    fallback = _provider_safe_state(config.fallback_provider, config.fallback_model, config.fallback_configured, config.fallback_api_key, config.fallback_status, config.fallback_warnings)
    return {
        "enabled": config.enabled,
        "provider": config.provider,
        "model": config.model,
        "configured": config.configured,
        "api_key_present": bool(config.api_key),
        "primary": primary,
        "fallback": fallback,
        "circuit_open": _is_circuit_open(config.provider, config.model),
        "warnings": list(config.warnings),
        "status": config.status,
        "cache_enabled": True,
        "on_check": os.environ.get("SHUDDHO_LLM_ON_CHECK", "manual").strip().lower(),
        "interactive_timeout_seconds": float(os.environ.get("SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS", os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "45"))),
        "background_timeout_seconds": float(os.environ.get("SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS", "60")),
        "timeout_seconds": float(os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "35")),
        "cache_ttl_seconds": int(os.environ.get("SHUDDHO_LLM_CACHE_TTL_SECONDS", "86400")),
        "max_candidates": int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATES", "8")),
        "max_candidate_chars": int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATE_CHARS", "2200")),
        "max_ai_text_chars": int(os.environ.get("SHUDDHO_MAX_AI_TEXT_CHARS", "5000")),
    }


def _sentences_for_ai(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "text": sentence.text, "start": sentence.start, "end": sentence.end}
        for idx, sentence in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "text": text, "start": 0, "end": len(text)}]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _should_run_llm(options: dict[str, Any]) -> bool:
    if not isinstance(options, dict):
        return os.environ.get("SHUDDHO_CHECK_STRATEGY", "").strip().lower() == "ai_first"
    explicit_keys = ["includeLLM", "includeAi", "includeAI", "ai", "llm"]
    for key in explicit_keys:
        if key in options:
            return _as_bool(options.get(key))
    return os.environ.get("SHUDDHO_CHECK_STRATEGY", "").strip().lower() == "ai_first"


def _should_run_async_llm(options: dict[str, Any]) -> bool:
    if not isinstance(options, dict):
        return False
    return bool(
        _as_bool(options.get("asyncLLM"))
        or _as_bool(options.get("asyncAi"))
        or _as_bool(options.get("asyncAI"))
    )


def _llm_mode(options: dict[str, Any], include_llm: bool) -> str:
    if not isinstance(options, dict):
        return "smart" if include_llm else "fast"
    value = options.get("llmMode") or options.get("mode")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "smart" if include_llm else "fast"


def _llm_allowed_on_check(include_llm: bool) -> tuple[bool, str]:
    mode = os.environ.get("SHUDDHO_LLM_ON_CHECK", "manual").strip().lower()
    if mode in {"never", "off", "false"}:
        return False, "env_never"
    if mode in {"always", "true"}:
        return True, "env_always"
    if mode == "manual":
        return bool(include_llm), "manual_requested" if include_llm else "manual_not_requested"
    return bool(include_llm), "default_manual"


def _normalize_api_check_payload(payload: ApiCheckRequest) -> dict[str, Any]:
    options = dict(payload.options or {})
    extra = getattr(payload, "__pydantic_extra__", None) or {}
    for key in ["includeLLM", "includeAi", "includeAI", "asyncLLM", "asyncAi", "asyncAI", "llmMode", "mode", "ai", "llm"]:
        if key in extra and key not in options:
            options[key] = extra[key]
    return {
        "text": payload.text,
        "language": payload.language or "bn",
        "document_id": getattr(payload, "document_id", None) or getattr(payload, "documentId", None),
        "revision": getattr(payload, "revision", None),
        "dialect": getattr(payload, "dialect", None),
        "user_id": getattr(payload, "user_id", None) or getattr(payload, "userId", None),
        "client": getattr(payload, "client", None),
        "consent": getattr(payload, "consent", None),
        "options": options,
    }


def _canonical_bool_options(options: dict[str, Any]) -> dict[str, bool]:
    if not isinstance(options, dict):
        return {}
    cleaned: dict[str, bool] = {}
    for key, value in options.items():
        if key in {"mode", "llmMode"}:
            continue
        if isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, str) and value.strip().lower() in {
            "true",
            "false",
            "1",
            "0",
            "yes",
            "no",
            "on",
            "off",
        }:
            cleaned[key] = _as_bool(value)
    return cleaned


def _log_raw_text_enabled() -> bool:
    return os.environ.get(LOG_RAW_TEXT_ENV_VAR, "false").strip().lower() == "true"



def _provider_configured(config: Any, fallback: bool = False) -> dict[str, Any]:
    return {
        "provider": config.fallback_provider if fallback else config.provider,
        "model": config.fallback_model if fallback else config.model,
        "api_key": config.fallback_api_key if fallback else config.api_key,
        "configured": config.fallback_configured if fallback else config.configured,
        "status": config.fallback_status if fallback else config.status,
        "warnings": list(config.fallback_warnings if fallback else config.warnings),
    }


FALLBACK_ELIGIBLE_STATUSES = {"missing_key", "auth_or_forbidden", "credits_or_payment_required", "model_not_found", "timeout", "rate_limited", "network_error", "provider_error", "invalid_json", "invalid_schema", "failed"}


def run_configured_provider(
    provider_config: dict[str, Any],
    text: str,
    request_id: str,
    sentences: list[dict[str, Any]],
    local_suggestions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    timeout_seconds: float,
) -> dict[str, Any]:
    provider = provider_config.get("provider")
    model = provider_config.get("model") or ""
    if not provider_config.get("configured") or not provider_config.get("api_key"):
        warning = {"gemini": "gemini_api_key_missing", "openrouter": "openrouter_api_key_missing", "openai": "openai_api_key_missing"}.get(str(provider), "unsupported_llm_provider")
        status = provider_config.get("status") or "missing_key"
        return LlmProviderResult(provider=str(provider or "disabled"), model=model, configured=False, status=status, warnings=[*(provider_config.get("warnings") or []), warning], response_mode="none").model_dump()
    if _is_circuit_open(str(provider), model):
        return LlmProviderResult(provider=str(provider), model=model, configured=True, status="failed", warnings=["llm_circuit_open"], response_mode="none").model_dump()
    if provider == "gemini":
        return run_gemini_check(text=text, model=model, api_key=provider_config.get("api_key") or "", timeout_seconds=timeout_seconds, request_id=request_id, sentences=sentences, local_suggestions=local_suggestions, candidates=candidates)
    if provider == "openrouter":
        return run_openrouter_check(text=text, model=model, api_key=provider_config.get("api_key") or "", timeout_seconds=timeout_seconds, request_id=request_id, sentences=sentences, local_suggestions=local_suggestions, candidates=candidates)
    if provider == "openai":
        return run_openai_check(text=text, model=model, api_key=provider_config.get("api_key") or "", timeout_seconds=timeout_seconds, request_id=request_id, sentences=sentences, local_suggestions=local_suggestions, candidates=candidates)
    return LlmProviderResult(provider=str(provider or "disabled"), model=model, status="unsupported_provider", warnings=["unsupported_llm_provider"]).model_dump()


def _run_provider_chain(config: Any, text: str, request_id: str, sentences: list[dict[str, Any]], local_suggestions: list[dict[str, Any]], candidates: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    primary_cfg = _provider_configured(config)
    result = run_configured_provider(primary_cfg, text, request_id, sentences, local_suggestions, candidates, timeout)
    primary_status = str(result.get("status") or "failed")
    fallback_provider = config.fallback_provider
    if fallback_provider and primary_status in FALLBACK_ELIGIBLE_STATUSES:
        fallback_cfg = _provider_configured(config, fallback=True)
        fallback_result = run_configured_provider(fallback_cfg, text, request_id, sentences, local_suggestions, candidates, timeout)
        fallback_result["warnings"] = _dedupe_strings([
            *(result.get("warnings") or []),
            f"primary_provider_failed:{config.provider}",
            f"primary_provider_status:{primary_status}",
            f"fallback_provider_used:{fallback_provider}",
            *(fallback_result.get("warnings") or []),
        ])
        if fallback_result.get("status") in {"completed", "completed_empty"}:
            fallback_result.setdefault("timings", {})
            fallback_result["timings"] = {**(fallback_result.get("timings") or {}), "fallback_used": True}
            return fallback_result
        return fallback_result
    return result


def _run_ai_check(
    text: str,
    request_id: str,
    local_suggestions: list[dict[str, Any]] | None = None,
    timeout_seconds: float | None = None,
) -> AiCheckResponse:
    config = resolve_llm_config(os.environ)
    base = {"provider": config.provider, "model": config.model, "llm_enabled": config.enabled, "configured": config.configured, "warnings": list(config.warnings), "status": config.status if config.status != "completed" else "attempted"}
    if not config.enabled:
        return AiCheckResponse(**{**base, "status": "disabled", "warnings": _dedupe_strings([*config.warnings, "llm_disabled"] if not config.warnings else config.warnings)})
    if not text.strip():
        return AiCheckResponse(**{**base, "status": "skipped", "warnings": _dedupe_strings([*config.warnings, "llm_empty_text_skipped"])})

    os.environ["SHUDDHO_REQUEST_ID"] = request_id
    timeout = timeout_seconds if timeout_seconds is not None else float(os.environ.get("SHUDDHO_LLM_TIMEOUT_SECONDS", "35") or "35")
    max_ai_chars = int(os.environ.get("SHUDDHO_MAX_AI_TEXT_CHARS", "5000") or "5000")
    ai_text = text[:max_ai_chars]
    truncation_warnings = ["llm_text_truncated"] if len(text) > max_ai_chars else []
    locals_for_prompt = local_suggestions or []
    candidates = build_llm_candidates(ai_text, locals_for_prompt, max_sentences=int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATES", "8")), max_chars=int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATE_CHARS", "2200")), max_text_chars=int(os.environ.get("SHUDDHO_MAX_AI_TEXT_CHARS", "5000")))
    sentences = _sentences_for_ai(ai_text)
    cache_key = _cache_key(ai_text, locals_for_prompt, candidates, config.provider, config.model, config.fallback_provider, config.fallback_model)
    cache_ttl = int(os.environ.get("SHUDDHO_LLM_CACHE_TTL_SECONDS", "86400") or "86400")
    cached = llm_cache.get(cache_key)
    if cached and time.time() - cached.get("created_at", 0) < cache_ttl:
        result = dict(cached.get("result") or cached)
        result.setdefault("called", True)
        result.setdefault("configured", True)
        result["timings"] = {**(result.get("timings") or {}), "cache_hit": True}
    else:
        result = _run_provider_chain(config, ai_text, request_id, sentences, locals_for_prompt, candidates, timeout)
        if result.get("status") in {"completed", "completed_empty"}:
            llm_cache[cache_key] = {"created_at": time.time(), "result": result, "provider": result.get("provider"), "model": result.get("model")}
    warnings = _dedupe_strings([*config.warnings, *truncation_warnings, *(result.get("warnings") or [])])
    logger.info("ai_check_complete request_id=%s provider=%s model=%s status=%s http_status=%s text_length=%s sent_length=%s llm_ms=%s warnings=%s", request_id, result.get("provider") or config.provider, result.get("model") or config.model, result.get("status"), result.get("http_status"), len(text), len(ai_text), (result.get("timings") or {}).get("llm_ms"), len(warnings))
    return AiCheckResponse(suggestions=result.get("suggestions", []) or [], correctedText=result.get("correctedText"), documentAssessment=result.get("documentAssessment") or {}, warnings=warnings, provider=result.get("provider") or config.provider, model=result.get("model") or config.model, llm_enabled=config.enabled, configured=bool(result.get("configured", config.configured)), called=bool(result.get("called")), parsed=bool(result.get("parsed")), status=str(result.get("status") or "failed"), response_mode=str(result.get("response_mode") or "none"), http_status=result.get("http_status"), usage=result.get("usage") or {}, timings=_safe_timings(result.get("timings")), ai_raw_suggestion_count=int(result.get("ai_raw_suggestion_count") or 0))


def _create_llm_review_job(text: str, language: str, local_suggestions: list[dict], mode: str, request_id: str | None = None) -> dict:
    request_id = request_id or datetime.now(timezone.utc).isoformat()
    job_id = f"llm_{uuid.uuid4().hex[:12]}"
    candidates = build_llm_candidates(
        text,
        local_suggestions,
        max_sentences=int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATES", "8")),
        max_chars=min(
            int(os.environ.get("SHUDDHO_LLM_MAX_CANDIDATE_CHARS", "2200")),
            int(os.environ.get("SHUDDHO_MAX_AI_TEXT_CHARS", "5000")),
        ),
    )
    llm_jobs[job_id] = {"job_id": job_id, "status": "queued", "suggestions": [], "verified_local_suggestion_ids": [], "rejected_local_suggestion_ids": [], "warnings": [], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}, "timings": {"queue_ms": 0, "llm_ms": 0, "total_ms": 0}, "created_at": time.time()}
    threading.Thread(target=_run_llm_job, args=(job_id, text, candidates, local_suggestions, request_id), daemon=True).start()
    return {"job_id": job_id, "status": "queued", "estimated_seconds": 3, "candidate_count": len(candidates)}


def _run_llm_job(job_id: str, text: str, candidates: list[dict], local_suggestions: list[dict], request_id: str) -> None:
    started = time.time()
    job = llm_jobs[job_id]
    job["status"] = "running"
    enabled, provider, model, _ = _llm_config()
    if not enabled or _is_circuit_open(provider, model):
        job.update({"status": "failed", "warnings": ["llm_circuit_open" if _is_circuit_open(provider, model) else "llm_disabled"]})
        return
    key = _cache_key(text, local_suggestions, candidates, provider, model, resolve_llm_config(os.environ).fallback_provider, resolve_llm_config(os.environ).fallback_model)
    cached = llm_cache.get(key)
    ttl = int(os.environ.get("SHUDDHO_LLM_CACHE_TTL_SECONDS", "86400"))
    if cached and time.time() - cached.get("created_at", 0) < ttl:
        job.update(cached | {"job_id": job_id, "status": "succeeded"})
        return
    ai = _run_ai_check(text, request_id, local_suggestions=local_suggestions, timeout_seconds=float(os.environ.get("SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS", "60") or "60"))
    if ai.status not in {"completed", "completed_empty"}:
        _record_llm_failure(ai.provider, ai.model, ai.warnings or [ai.status])
        job.update({"status": ai.status if ai.status in {"timeout", "rate_limited"} else "failed", "llm_status": ai.status, "warnings": ai.warnings, "provider": ai.provider, "model": ai.model, "timings": {"queue_ms": 0, "llm_ms": int((time.time()-started)*1000), "total_ms": int((time.time()-started)*1000)}})
        return
    valid_ai, validation_warnings = validate_ai_suggestions(text, ai.suggestions, _sentences_for_ai(text))
    merged, merge_warnings = merge_suggestions(text, local_suggestions, valid_ai, ai.provider, ai.model)
    warnings = _dedupe_strings([*ai.warnings, *validation_warnings, *merge_warnings])
    raw_ai_count = int(ai.ai_raw_suggestion_count or len(ai.suggestions or []))
    payload = {"suggestions": merged, "ai_suggestion_count": len(valid_ai), "ai_raw_suggestion_count": raw_ai_count, "ai_valid_suggestion_count": len(valid_ai), "ai_rejected_suggestion_count": max(0, raw_ai_count - len(valid_ai)), "ai_empty_reason": "model_returned_no_suggestions" if raw_ai_count == 0 else ("all_ai_suggestions_rejected" if raw_ai_count and not valid_ai else None), "correctedText": ai.correctedText, "documentAssessment": ai.documentAssessment, "llm_status": ai.status, "provider": ai.provider, "model": ai.model, "verified_local_suggestion_ids": [], "rejected_local_suggestion_ids": [], "warnings": warnings, "usage": ai.usage, "timings": {"queue_ms": 0, "llm_ms": int((time.time()-started)*1000), "total_ms": int((time.time()-started)*1000)}, "created_at": time.time()}
    llm_cache[key] = payload
    job.update(payload | {"status": "completed" if ai.status in {"completed", "completed_empty"} else ai.status})


def _cache_key(text: str, local_suggestions: list[dict], candidates: list[dict], provider: str, model: str, fallback_provider: str | None = None, fallback_model: str = "") -> str:
    from services.api.shuddho_api.ai_review_schema import PROMPT_SCHEMA_VERSION
    normalized = " ".join(text.split())
    blob = normalized + json.dumps(local_suggestions, sort_keys=True, ensure_ascii=False) + json.dumps(candidates, sort_keys=True, ensure_ascii=False) + provider + model + str(fallback_provider or "") + fallback_model + PROMPT_SCHEMA_VERSION + "v2"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _record_llm_failure(provider: str, model: str, warnings: list[str]) -> None:
    failure_markers = ("timeout", "rate", "server", "invalid_json", "failed", "network")
    if not any(any(marker in warning for marker in failure_markers) for warning in warnings):
        return
    key = f"{provider}:{model}"
    now = time.time()
    window = int(os.environ.get("SHUDDHO_LLM_CIRCUIT_WINDOW_SECONDS", "300"))
    llm_failures[key] = [t for t in llm_failures.get(key, []) if now - t <= window] + [now]
    if len(llm_failures[key]) >= int(os.environ.get("SHUDDHO_LLM_CIRCUIT_FAILURE_LIMIT", "5")):
        llm_circuit_until[key] = now + int(os.environ.get("SHUDDHO_LLM_CIRCUIT_COOLDOWN_SECONDS", "180"))


def _is_circuit_open(provider: str, model: str) -> bool:
    return time.time() < llm_circuit_until.get(f"{provider}:{model}", 0)


def _cleanup_llm_jobs() -> None:
    ttl = 1800
    now = time.time()
    for key in list(llm_jobs.keys()):
        if now - llm_jobs[key].get("created_at", now) > ttl:
            llm_jobs.pop(key, None)


def _rewrite_service() -> RewriteService:
    return RewriteService(analysis_pipeline)


def _build_health_response() -> HealthResponse:
    detector_runtime = detector_service.runtime_status()
    corrector_runtime = corrector_service.runtime_status()
    llm_config = resolve_llm_config(os.environ)
    analysis_profile = _derive_analysis_profile(detector_runtime, corrector_runtime)
    degraded_reasons = _derive_degraded_reasons(detector_runtime, corrector_runtime)
    return HealthResponse(
        status="ok",
        version=BACKEND_VERSION,
        uptime_seconds=max(0.0, (datetime.now(timezone.utc) - STARTUP_TIMESTAMP).total_seconds()),
        allowed_origins_count=len(ALLOWED_ORIGINS),
        config={
            "llm_provider": llm_config.provider,
            "llm_enabled": llm_config.enabled,
            "check_strategy": os.environ.get("SHUDDHO_CHECK_STRATEGY", "manual"),
            "max_ai_text_chars": MAX_AI_CHECK_CHARS,
        },
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
        llm=_llm_safe_status(),
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
