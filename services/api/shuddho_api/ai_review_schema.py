from __future__ import annotations

import json
import re
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

IssueType = Literal[
    "grammar", "spelling", "punctuation", "spacing", "style", "clarity",
    "fluency", "tone", "word_choice", "other",
]
Severity = Literal["low", "medium", "high"]
Language = Literal["bn", "en", "mixed", "unknown"]
Quality = Literal["poor", "fair", "good", "excellent"]

PROMPT_SCHEMA_VERSION = "ai-review-v2"

SYSTEM_PROMPT = (
    "You are Shuddho AI Reviewer, a professional Bangla writing reviewer. "
    "Review Bangla writing with full context from fullText and candidateSentences. "
    "Return only JSON matching the schema. Do not include markdown or commentary. "
    "Do not rewrite the whole document as a suggestion. Only return precise, actionable, minimal suggestions. "
    "Each suggestion.original MUST be an exact substring of fullText, and start/end MUST exactly identify that substring. "
    "Preserve user intent, meaning, tone, names, numbers, IDs, URLs, emails, quoted text, code, and correct punctuation. "
    "Prefer short corrections for spelling, grammar, punctuation, spacing, word choice, clarity, and fluency. "
    "Never invent text or create suggestions for text that does not exist. replacement must differ from original. "
    "If no confident suggestion exists, return suggestions as an empty array and correctedText equal to the original text. "
    "Required top-level output fields: requestId, correctedText, documentAssessment, suggestions. "
    "Each suggestion must include id, sentenceId, original, replacement, issueType, severity, explanation, confidence, start, and end."
)


class DocumentAssessment(BaseModel):
    summary: str = ""
    overallQuality: Quality = "good"
    language: Language = "unknown"


class AIReviewSuggestion(BaseModel):
    id: str
    sentenceId: str
    original: str
    replacement: str
    issueType: IssueType = "grammar"
    severity: Severity = "medium"
    explanation: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["ai"] = "ai"
    start: int | None = None
    end: int | None = None

    @field_validator("original", "replacement")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must not be blank")
        return value


class AIReviewResponse(BaseModel):
    requestId: str
    correctedText: str
    documentAssessment: DocumentAssessment = Field(default_factory=DocumentAssessment)
    suggestions: list[AIReviewSuggestion] = Field(default_factory=list)


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    def visit(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
                props = node.get("properties")
                if isinstance(props, dict):
                    node["required"] = list(props.keys())
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        return node

    return visit(schema)


def required_output_schema() -> dict[str, Any]:
    return _strict_json_schema(AIReviewResponse.model_json_schema())


def strip_json_fences(content: str) -> str:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def extract_json_payload(content: str) -> dict[str, Any]:
    cleaned = strip_json_fences(content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise TypeError("AI response must be a JSON object")
    return parsed


def normalize_review_payload(parsed: dict[str, Any], request_id: str, original_text: str) -> dict[str, Any]:
    payload = dict(parsed)
    payload.setdefault("requestId", request_id)
    payload.setdefault("correctedText", original_text)
    payload.setdefault("documentAssessment", {})
    if not isinstance(payload.get("documentAssessment"), dict):
        payload["documentAssessment"] = {}
    suggestions = payload.get("suggestions")
    if suggestions is None:
        payload["suggestions"] = []
    elif not isinstance(suggestions, list):
        raise ValueError("suggestions must be a list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(payload["suggestions"]):
        if not isinstance(item, dict):
            continue
        copy = dict(item)
        copy.setdefault("id", f"ai_{index}")
        copy.setdefault("sentenceId", copy.get("sentence_id") or "")
        copy.setdefault("issueType", copy.get("type") or copy.get("category") or "grammar")
        copy.setdefault("severity", "medium")
        copy.setdefault("explanation", copy.get("message") or copy.get("explanationBn") or "")
        copy.setdefault("confidence", 0.75)
        copy["source"] = "ai"
        if "start" not in copy and "span_start" in copy:
            copy["start"] = copy.get("span_start")
        if "end" not in copy and "span_end" in copy:
            copy["end"] = copy.get("span_end")
        normalized.append(copy)
    payload["suggestions"] = normalized
    return payload


def build_review_messages(
    *,
    request_id: str,
    full_text: str,
    sentences: list[dict[str, Any]],
    local_suggestions: list[dict[str, Any]],
    candidate_sentences: list[dict[str, Any]],
) -> list[dict[str, str]]:
    user_payload = {
        "requestId": request_id,
        "fullText": full_text,
        "sentences": sentences,
        "localSuggestions": local_suggestions,
        "candidateSentences": candidate_sentences,
        "requestMetadata": {"schemaVersion": PROMPT_SCHEMA_VERSION},
        "requiredOutputSchema": required_output_schema(),
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def validate_ai_review_payload(parsed: dict[str, Any], request_id: str, original_text: str) -> AIReviewResponse:
    payload = normalize_review_payload(parsed, request_id, original_text)
    return AIReviewResponse.model_validate(payload)

# Backward-compatible validator export for callers that expect validation helpers
# near the AI review schema definitions.
def validate_ai_suggestions(text: str, ai_suggestions: list[dict[str, Any]], sentences: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    from services.api.shuddho_api.suggestion_merge import validate_ai_suggestions as _validate_ai_suggestions

    return _validate_ai_suggestions(text, ai_suggestions, sentences)
