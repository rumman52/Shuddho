from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, Field, ValidationError, field_validator


class OpenRouterIssueCategory(str, Enum):
    GRAMMAR_ERROR = "grammar_error"
    SPELLING_ERROR = "spelling_error"
    PUNCTUATION_ERROR = "punctuation_error"
    SPACING_ERROR = "spacing_error"
    ORTHOGRAPHY_VARIANT = "orthography_variant"
    STYLE_SUGGESTION = "style_suggestion"


class OpenRouterIssue(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    original: str
    replacement: str
    category: OpenRouterIssueCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reason_bn: str
    subtype: str = "localized_issue"

    @field_validator("original", "replacement", "reason_bn", "subtype")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return value.strip()


class StructuredOpenRouterIssueCategory(str, Enum):
    GRAMMAR = "grammar"
    SPELLING = "spelling"
    ORTHOGRAPHY = "orthography"
    PUNCTUATION = "punctuation"
    STYLE = "style"


class StructuredOpenRouterIssue(BaseModel):
    category: StructuredOpenRouterIssueCategory
    subtype: str
    span_text: str
    replacement: str
    explanation_bn: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("subtype", "span_text", "replacement", "explanation_bn")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return value.strip()


class StructuredOpenRouterIssueEnvelope(BaseModel):
    issues: list[StructuredOpenRouterIssue] = Field(default_factory=list)


def parse_openrouter_response(raw_text: str, *, sentence: str | None = None) -> list[OpenRouterIssue]:
    if not raw_text or not raw_text.strip():
        return []

    stripped_text = _strip_json_fences(raw_text)
    try:
        payload = json.loads(stripped_text)
    except json.JSONDecodeError:
        return []

    try:
        envelope = StructuredOpenRouterIssueEnvelope.model_validate(payload)
    except ValidationError:
        return []

    valid_issues: list[OpenRouterIssue] = []
    for issue in envelope.issues:
        parsed_issue = _to_internal_issue(issue, sentence=sentence)
        if parsed_issue is None:
            continue
        valid_issues.append(parsed_issue)
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


def _is_structurally_safe(issue: OpenRouterIssue) -> bool:
    if issue.end <= issue.start:
        return False
    if not issue.original or not issue.replacement or not issue.reason_bn:
        return False
    if issue.original == issue.replacement:
        return False
    if not issue.subtype:
        return False
    return True


def _matches_sentence(issue: OpenRouterIssue, sentence: str) -> bool:
    if issue.end > len(sentence):
        return False
    return sentence[issue.start : issue.end] == issue.original


def _to_internal_issue(
    issue: StructuredOpenRouterIssue,
    *,
    sentence: str | None,
) -> OpenRouterIssue | None:
    category = _map_category(issue.category, issue.subtype)
    if category is None:
        return None

    if sentence is None:
        return None

    span_offsets = _resolve_span_offsets(issue.span_text, sentence)
    if span_offsets is None:
        return None

    start, end = span_offsets
    parsed_issue = OpenRouterIssue(
        start=start,
        end=end,
        original=issue.span_text,
        replacement=issue.replacement,
        category=category,
        confidence=issue.confidence,
        reason_bn=issue.explanation_bn,
        subtype=issue.subtype,
    )
    if not _is_structurally_safe(parsed_issue):
        return None
    if not _matches_sentence(parsed_issue, sentence):
        return None
    return parsed_issue


def _map_category(
    category: StructuredOpenRouterIssueCategory,
    subtype: str,
) -> OpenRouterIssueCategory | None:
    normalized_subtype = subtype.strip().casefold()
    if category == StructuredOpenRouterIssueCategory.GRAMMAR:
        if normalized_subtype in {
            "spacing_error",
            "extra_whitespace",
            "space_before_punctuation",
            "space_after_punctuation",
            "fused_postposition",
            "genitive_spacing",
        }:
            return OpenRouterIssueCategory.SPACING_ERROR
        return OpenRouterIssueCategory.GRAMMAR_ERROR
    if category == StructuredOpenRouterIssueCategory.SPELLING:
        return OpenRouterIssueCategory.SPELLING_ERROR
    if category == StructuredOpenRouterIssueCategory.ORTHOGRAPHY:
        return OpenRouterIssueCategory.ORTHOGRAPHY_VARIANT
    if category == StructuredOpenRouterIssueCategory.PUNCTUATION:
        if normalized_subtype in {
            "spacing_error",
            "extra_whitespace",
            "space_before_punctuation",
            "space_after_punctuation",
            "fused_postposition",
            "genitive_spacing",
        }:
            return OpenRouterIssueCategory.SPACING_ERROR
        return OpenRouterIssueCategory.PUNCTUATION_ERROR
    if category == StructuredOpenRouterIssueCategory.STYLE:
        return OpenRouterIssueCategory.STYLE_SUGGESTION
    return None


def _resolve_span_offsets(span_text: str, sentence: str) -> tuple[int, int] | None:
    normalized_span = span_text.strip()
    if not normalized_span:
        return None

    matches: list[tuple[int, int]] = []
    cursor = 0
    while True:
        index = sentence.find(normalized_span, cursor)
        if index < 0:
            break
        matches.append((index, index + len(normalized_span)))
        cursor = index + 1

    if len(matches) != 1:
        return None

    return matches[0]
