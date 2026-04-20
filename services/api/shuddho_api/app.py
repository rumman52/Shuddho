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
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline, build_corrected_text
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
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
    Suggestion,
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
    if value is None or not value.strip():
        return list(DEFAULT_ALLOWED_ORIGINS)

    allowed_origins: list[str] = []
    for raw_origin in value.split(","):
        origin = raw_origin.strip()
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)
    return allowed_origins or list(DEFAULT_ALLOWED_ORIGINS)


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
    effective_personal_dictionary = _merge_personal_dictionaries(
        payload.personal_dictionary,
        feedback_store.load_personal_dictionary(user_id=payload.user_id),
    )
    response = analysis_pipeline.analyze(
        payload.text,
        effective_personal_dictionary,
        payload.mode,
    )
    response = response.model_copy(
        update={
            "backend_version": BACKEND_VERSION,
            "lexicon_source": spell_engine.lexicon_source,
            "lexicon_version": spell_engine.lexicon_version,
        }
    )
    suppressed_keys = feedback_store.load_suppressed_keys(user_id=payload.user_id)
    if not suppressed_keys:
        return response

    visible_suggestions = _filter_suppressed_suggestions(response.suggestions, suppressed_keys)
    return response.model_copy(
        update={
            "suggestions": visible_suggestions,
            "corrected_text": build_corrected_text(response.text, visible_suggestions),
        }
    )


@app.post("/feedback", response_model=FeedbackRecord)
def feedback(payload: FeedbackRequest) -> FeedbackRecord:
    return feedback_store.save(payload)


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
        ],
        "strict": [
            "rules",
            "spell",
            "deterministic_candidate_generation",
            "feedback_adaptation",
            "broader_contextual_visibility",
            "orthography_variants",
        ],
        "formal": [
            "rules",
            "spell",
            "deterministic_candidate_generation",
            "feedback_adaptation",
            "broader_contextual_visibility",
            "orthography_variants",
            "formal_style_guidance",
        ],
    }

    if detector_runtime.loaded:
        for capabilities in base_capabilities.values():
            capabilities.append("detector_span_detection")

    if corrector_runtime.loaded:
        for capabilities in base_capabilities.values():
            capabilities.append("sentence_level_local_corrector")
            capabilities.append("inline_corrector_span_projection")

    return base_capabilities


detector_runtime = detector_service.runtime_status()
corrector_runtime = corrector_service.runtime_status()
analysis_profile = _derive_analysis_profile(detector_runtime, corrector_runtime)
degraded_reasons = _derive_degraded_reasons(detector_runtime, corrector_runtime)

logger.info(
    "Shuddho API startup env_file=%s detector_status=%s detector_reason=%s detector_checkpoint=%s detector_checkpoint_exists=%s "
    "corrector_status=%s corrector_reason=%s corrector_checkpoint=%s analysis_profile=%s degraded_reasons=%s backend_version=%s",
    ENV_FILE_PATH,
    detector_runtime.status,
    detector_runtime.reason,
    detector_runtime.checkpoint,
    detector_runtime.checkpoint_exists,
    corrector_runtime.status,
    corrector_runtime.reason,
    corrector_runtime.checkpoint,
    analysis_profile.value,
    degraded_reasons,
    BACKEND_VERSION,
)
if degraded_reasons:
    logger.warning("Shuddho API is running in degraded local analysis mode reasons=%s", degraded_reasons)
