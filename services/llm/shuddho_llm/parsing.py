from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, Field, ValidationError, field_validator


class GeminiIssueCategory(str, Enum):
    GRAMMAR_ERROR = "grammar_error"
    SPELLING_ERROR = "spelling_error"
    PUNCTUATION_ERROR = "punctuation_error"
    SPACING_ERROR = "spacing_error"
    ORTHOGRAPHY_VARIANT = "orthography_variant"
    STYLE_SUGGESTION = "style_suggestion"


class GeminiIssue(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    original: str
    replacement: str
    category: GeminiIssueCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reason_bn: str

    @field_validator("original", "replacement", "reason_bn")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return value.strip()


class GeminiIssueEnvelope(BaseModel):
    issues: list[GeminiIssue] = Field(default_factory=list)


def parse_gemini_response(raw_text: str, *, sentence: str | None = None) -> list[GeminiIssue]:
    if not raw_text or not raw_text.strip():
        return []

    stripped_text = _strip_json_fences(raw_text)
    try:
        payload = json.loads(stripped_text)
    except json.JSONDecodeError:
        return []

    try:
        envelope = GeminiIssueEnvelope.model_validate(payload)
    except ValidationError:
        return []

    valid_issues: list[GeminiIssue] = []
    for issue in envelope.issues:
        if not _is_structurally_safe(issue):
            continue
        if sentence is not None and not _matches_sentence(issue, sentence):
            continue
        valid_issues.append(issue)
    return valid_issues


def _strip_json_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _is_structurally_safe(issue: GeminiIssue) -> bool:
    if issue.end <= issue.start:
        return False
    if not issue.original or not issue.replacement or not issue.reason_bn:
        return False
    if issue.original == issue.replacement:
        return False
    return True


def _matches_sentence(issue: GeminiIssue, sentence: str) -> bool:
    if issue.end > len(sentence):
        return False
    return sentence[issue.start : issue.end] == issue.original
