from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


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


class AnalyzeMode(str, Enum):
    STANDARD = "standard"
    STRICT = "strict"
    FORMAL = "formal"


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
    mode: AnalyzeMode = AnalyzeMode.STANDARD

    @field_validator("personal_dictionary")
    @classmethod
    def normalize_personal_dictionary(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for entry in value:
            compact = " ".join(entry.split())
            if not compact or compact in seen:
                continue
            seen.add(compact)
            normalized.append(compact)
        return normalized


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
    detector_loaded: bool
    detector_checkpoint: str | None = None
    allowed_origins: list[str]
