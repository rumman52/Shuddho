from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
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
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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


def _rewrite_service() -> RewriteService:
    return RewriteService(analysis_pipeline)


def _build_health_response() -> HealthResponse:
    detector_runtime = detector_service.runtime_status()
    corrector_runtime = corrector_service.runtime_status()
    analysis_profile = _derive_analysis_profile(detector_runtime, corrector_runtime)
    degraded_reasons = _derive_degraded_reasons(detector_runtime, corrector_runtime)
    backend_warning = _derive_backend_warning(detector_runtime, corrector_runtime)
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
        backend_warning=backend_warning,
        mode_capabilities=_build_mode_capabilities(detector_runtime, corrector_runtime),
    )


def _build_health_deep_response() -> HealthDeepResponse:
    shallow = _build_health_response()
    snapshot = spell_engine.repository.snapshot
    return HealthDeepResponse(
        **shallow.model_dump(),
        backend_version=BACKEND_VERSION,
        env_file_path=str(ENV_FILE_PATH),
        env_file_loaded=ENV_FILE_LOADED,
        last_startup_timestamp=STARTUP_TIMESTAMP,
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
