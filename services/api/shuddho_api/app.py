from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.candidate_generator import CandidateGenerator
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.feedback.shuddho_feedback.store import FeedbackStore
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeRequest, AnalyzeResponse, FeedbackRecord, FeedbackRequest, HealthResponse

ALLOWED_ORIGINS = [
    "https://shuddho-web-editor.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000"
]

app = FastAPI(title="Shuddho API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)

normalizer = BanglaNormalizer()
spell_engine = SpellEngine(
    runtime_csv_path=Path(__file__).resolve().parents[3] / "data" / "imports" / "lexicon" / "words_clean.csv"
)
rule_engine = RuleEngine()
suggestion_manager = SuggestionManager()
detector_service = DetectorService.from_checkpoint_path(os.environ.get("SHUDDHO_DETECTOR_CHECKPOINT"))
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
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Shuddho API is running"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    return analysis_pipeline.analyze(payload.text, payload.personal_dictionary)


@app.post("/feedback", response_model=FeedbackRecord)
def feedback(payload: FeedbackRequest) -> FeedbackRecord:
    return feedback_store.save(payload)
