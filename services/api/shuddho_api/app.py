from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.candidate_generator import CandidateGenerator
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.feedback.shuddho_feedback.store import FeedbackStore
from services.llm.shuddho_llm.openrouter_client import OpenRouterClient
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeRequest, AnalyzeResponse, FeedbackRecord, FeedbackRequest, HealthResponse, Suggestion

logger = logging.getLogger(__name__)
ALLOWED_ORIGINS_ENV_VAR = "SHUDDHO_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://shuddho-web-editor.vercel.app",
]
# Chrome extension origins and arbitrary localhost ports stay on the regex path.
ALLOWED_ORIGIN_REGEX = r"^(chrome-extension://[a-p]{32}|https?://(localhost|127\.0\.0\.1)(:\d+)?)$"


def _parse_allowed_origins(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return list(DEFAULT_ALLOWED_ORIGINS)

    allowed_origins: list[str] = []
    for raw_origin in value.split(","):
        origin = raw_origin.strip()
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)

    return allowed_origins or list(DEFAULT_ALLOWED_ORIGINS)

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE_PATH = REPO_ROOT / ".env"
ENV_FILE_LOADED = load_dotenv(ENV_FILE_PATH, override=False)
logger.info(
    "Shuddho API environment env_file=%s exists=%s loaded=%s",
    ENV_FILE_PATH,
    ENV_FILE_PATH.is_file(),
    ENV_FILE_LOADED,
)
ALLOWED_ORIGINS = _parse_allowed_origins(os.environ.get(ALLOWED_ORIGINS_ENV_VAR))

app = FastAPI(title="Shuddho API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)

normalizer = BanglaNormalizer()
spell_engine = SpellEngine(
    runtime_csv_path=REPO_ROOT / "data" / "imports" / "lexicon" / "words_clean.csv"
)
rule_engine = RuleEngine()
suggestion_manager = SuggestionManager()
detector_service = DetectorService.from_environment(os.environ)
openrouter_client = OpenRouterClient.from_environment(os.environ)
candidate_generator = CandidateGenerator()
feedback_store = FeedbackStore()
ranking_pipeline = SuggestionRankingPipeline(feedback_store=feedback_store)
analysis_pipeline = AnalysisPipeline(
    normalizer=normalizer,
    spell_engine=spell_engine,
    rule_engine=rule_engine,
    suggestion_manager=suggestion_manager,
    detector_service=detector_service,
    candidate_generator=candidate_generator,
    ranking_pipeline=ranking_pipeline,
    openrouter_client=openrouter_client,
)

logger.info(
    "Shuddho API startup openrouter_api_key_found=%s openrouter_configured=%s openrouter_available=%s openrouter_model=%s",
    openrouter_client.has_api_key(),
    openrouter_client.is_configured(),
    openrouter_client.is_available(),
    openrouter_client.model_name,
)
if not openrouter_client.is_configured():
    if openrouter_client.has_api_key():
        logger.warning(
            "OpenRouter is disabled because OPENROUTER_API_KEY in %s is still a placeholder or invalid. "
            "Replace it with OPENROUTER_API_KEY=your_real_openrouter_key_here and restart the backend.",
            ENV_FILE_PATH,
        )
    else:
        logger.warning(
            "OpenRouter is disabled because OPENROUTER_API_KEY is missing from %s. "
            "Add OPENROUTER_API_KEY=your_real_openrouter_key_here and restart the backend.",
            ENV_FILE_PATH,
        )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    openrouter_configured = openrouter_client.is_configured()
    openrouter_available = openrouter_client.is_available()
    return HealthResponse(
        status="ok",
        detector_loaded=detector_service.is_loaded(),
        detector_checkpoint=detector_service.checkpoint_path,
        allowed_origins=ALLOWED_ORIGINS,
        openrouter_configured=openrouter_configured,
        openrouter_available=openrouter_available,
        openrouter_model=openrouter_client.model_name,
    )


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
    suppressed_keys = feedback_store.load_suppressed_keys(user_id=payload.user_id)
    if not suppressed_keys:
        return response
    return response.model_copy(
        update={
            "suggestions": _filter_suppressed_suggestions(response.suggestions, suppressed_keys),
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
