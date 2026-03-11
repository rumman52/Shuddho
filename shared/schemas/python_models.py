from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SuggestionCategory(str, Enum):
    CORRECTNESS = "correctness"
    SPELLING = "spelling"
    GRAMMAR = "grammar"
    PUNCTUATION = "punctuation"
    CLARITY = "clarity"
    STYLE = "style"


class SuggestionSource(str, Enum):
    RULE = "rule"
    SPELL = "spell"
    MODEL = "model"
    HYBRID = "hybrid"


class SuggestionSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SuggestionStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class Suggestion(BaseModel):
    id: str
    category: SuggestionCategory
    subtype: str
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=0)
    original_text: str
    replacement_options: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    explanation_bn: str
    explanation_en: str
    source: SuggestionSource
    severity: SuggestionSeverity
    status: SuggestionStatus = SuggestionStatus.OPEN


class AnalyzeRequest(BaseModel):
    text: str
    personal_dictionary: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    text: str
    normalized_text: str
    suggestions: list[Suggestion]


class FeedbackAction(str, Enum):
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class FeedbackRequest(BaseModel):
    suggestion_id: str
    action: FeedbackAction
    text: str
    replacement: str | None = None


class FeedbackRecord(BaseModel):
    id: int | None = None
    suggestion_id: str
    action: FeedbackAction
    text: str
    replacement: str | None = None
    created_at: datetime


class HealthResponse(BaseModel):
    status: str

