from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SuggestionCategory(str, Enum):
    SPELLING = "spelling"
    GRAMMAR = "grammar"
    PUNCTUATION = "punctuation"
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


class Suggestion(BaseModel):
    id: str
    rule_id: str
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
    feedback_key: str | None = None


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
    feedback_key: str | None = None
    rule_id: str | None = None
    subtype: str | None = None
    source: SuggestionSource | None = None
    original_text: str | None = None


class FeedbackRecord(BaseModel):
    id: int | None = None
    suggestion_id: str
    action: FeedbackAction
    text: str
    replacement: str | None = None
    feedback_key: str | None = None
    rule_id: str | None = None
    subtype: str | None = None
    source: SuggestionSource | None = None
    original_text: str | None = None
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
