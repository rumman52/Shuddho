from __future__ import annotations

import json
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

IssueType = Literal[
    "spelling", "grammar", "punctuation", "spacing", "repeated_word",
    "fluency", "sentence_rewrite", "style", "clarity", "tone",
    "word_choice", "other",
]
Severity = Literal["low", "medium", "high"]
Language = Literal["bn", "en", "mixed", "unknown"]
Quality = Literal["poor", "fair", "good", "excellent"]

PROMPT_SCHEMA_VERSION = "ai-review-v4-function-call"

SYSTEM_PROMPT = """You are Shuddho, a professional Bangla editor. Review fullText in context for spelling, grammar, punctuation, spacing, word choice, clarity, fluency, and meaning. Return only JSON (no markdown) with keys requestId, correctedText, documentAssessment, suggestions. documentAssessment has summary, overallQuality (poor|fair|good|excellent), language (bn|en|mixed|unknown). Each suggestion has id, sentenceId, original, replacement, issueType, severity, explanation, confidence, start, end.
original must be an exact fullText substring and [start,end) its exact indexes. Prefer minimal edits, preserve meaning/names/numbers/quotes, never rewrite the whole document as one suggestion, and omit uncertain edits. correctedText must be the complete corrected document. If no edits, use suggestions=[] and correctedText=fullText."""


class DocumentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    overallQuality: Quality = "good"
    language: Language = "unknown"


class AIReviewSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sentenceId: str
    original: str
    replacement: str
    issueType: IssueType = "grammar"
    severity: Severity = "medium"
    explanation: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)

    @field_validator("original", "replacement")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must not be blank")
        return value


class AIReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    # Providers occasionally encode the whole object as a JSON string. Decode
    # at most once more; never apply lossy text substitutions.
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
    except json.JSONDecodeError as direct_error:
        start = cleaned.find("{")
        if start < 0:
            raise direct_error
        depth = 0
        in_string = False
        escaped = False
        end = None
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise direct_error
        parsed = json.loads(cleaned[start:end])
    if not isinstance(parsed, dict):
        raise TypeError("AI response must be a JSON object")
    return parsed


def raw_suggestion_count(parsed: dict[str, Any]) -> int:
    suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else None
    return len(suggestions) if isinstance(suggestions, list) else 0


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
        original = copy.get("original") or copy.get("originalText") or copy.get("original_text")
        replacement = (
            copy.get("replacement")
            or copy.get("suggestedText")
            or copy.get("suggested_text")
            or copy.get("replacementText")
            or copy.get("replacement_text")
        )
        copy["original"] = original
        copy["replacement"] = replacement
        copy["id"] = copy.get("id") or f"ai_{index}"
        copy["sentenceId"] = copy.get("sentenceId") or copy.get("sentence_id") or ""
        copy["issueType"] = copy.get("issueType") or copy.get("type") or copy.get("category") or "grammar"
        copy["severity"] = copy.get("severity") or "medium"
        copy["explanation"] = copy.get("explanation") or copy.get("message") or copy.get("explanationBn") or copy.get("explanation_en") or ""
        copy["confidence"] = copy.get("confidence", 0.75)
        copy.pop("source", None)
        if "start" not in copy and "span_start" in copy:
            copy["start"] = copy.get("span_start")
        if "end" not in copy and "span_end" in copy:
            copy["end"] = copy.get("span_end")
        allowed = {"id", "sentenceId", "original", "replacement", "issueType", "severity", "explanation", "confidence", "start", "end"}
        candidate = {key: copy.get(key) for key in allowed if key in copy}
        try:
            normalized.append(AIReviewSuggestion.model_validate(candidate).model_dump())
        except Exception:
            continue
    payload["suggestions"] = normalized
    return payload


def build_review_messages(
    *, request_id: str, full_text: str, sentences: list[dict[str, Any]],
    local_suggestions: list[dict[str, Any]], candidate_sentences: list[dict[str, Any]],
) -> list[dict[str, str]]:
    # Text exists exactly once. Sentence/candidate text is represented by offsets only.
    sentence_spans = [
        {"id": item.get("sentenceId") or item.get("id") or f"s{idx}",
         "start": item.get("start", 0), "end": item.get("end", 0)}
        for idx, item in enumerate(sentences)
    ]
    local_hints = []
    for idx, item in enumerate(local_suggestions):
        compact = {
            "id": item.get("id") or f"l{idx}",
            "type": item.get("type") or item.get("issueType"),
            "start": item.get("start"), "end": item.get("end"),
            "original": item.get("original") or item.get("originalText"),
            "replacement": item.get("replacement") or item.get("suggestedText"),
        }
        local_hints.append({key: value for key, value in compact.items() if value is not None})
    user_payload = {
        "requestId": request_id, "fullText": full_text,
        "sentenceSpans": sentence_spans, "localHints": local_hints,
        "schemaVersion": PROMPT_SCHEMA_VERSION,
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
