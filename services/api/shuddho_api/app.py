from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
spell_engine = SpellEngine()
rule_engine = RuleEngine()
suggestion_manager = SuggestionManager()
feedback_store = FeedbackStore()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Shuddho API is running"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    normalized = normalizer.normalize(payload.text)
    spell_suggestions = spell_engine.analyze(normalized.text, payload.personal_dictionary)
    rule_suggestions = rule_engine.analyze(payload.text)
    merged = suggestion_manager.merge(payload.text, normalized, spell_suggestions, rule_suggestions)
    return AnalyzeResponse(text=payload.text, normalized_text=normalized.text, suggestions=merged)


@app.post("/feedback", response_model=FeedbackRecord)
def feedback(payload: FeedbackRequest) -> FeedbackRecord:
    return feedback_store.save(payload)
