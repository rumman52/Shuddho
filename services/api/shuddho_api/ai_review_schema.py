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

PROMPT_SCHEMA_VERSION = "ai-review-v2"

SYSTEM_PROMPT = """You are Shuddho AI Reviewer, a professional Bangla writing reviewer.

Task:
Review the entire Bangla fullText with document context. Inspect every sentence in the supplied sentences list and every localSuggestions/candidateSentences item. Return every valid correction you can justify, not only the single best or highest-confidence correction.
Return ONLY valid JSON that matches the supplied schema exactly.

Coverage requirements:
- Review all sentences from start to end, including sentences without local candidates.
- Review every local suggestion/candidate and either include a better correction when valid or leave it out when it is not actually needed.
- Return all independent valid corrections. Multiple suggestions may target the same sentence when that sentence has multiple issues.
- Include spelling, grammar, punctuation, spacing, repeated_word, fluency, and sentence_rewrite corrections when appropriate.
- Use sentence_rewrite only for a single sentence-level rewrite; never use it to rewrite the whole document as one suggestion.
- correctedText should be the full text with all accepted corrections applied coherently.

Hard rules:
- Never return markdown.
- Never return commentary outside JSON.
- Never rewrite the full document as one suggestion.
- Return precise, minimal, actionable edits; use sentence_rewrite only when smaller edits cannot preserve fluency.
- Each suggestion.original MUST be an exact substring of fullText whenever possible.
- start and end should identify the exact original substring in fullText. If unsure about indexes, still provide the exact original substring and sentenceId so the backend can resolve the span.
- Preserve meaning, names, numbers, IDs, URLs, emails, quoted text, code, and user intent.
- Prefer small spelling, grammar, punctuation, spacing, repeated_word, clarity, fluency, or word-choice edits.
- If uncertain, do not guess.
- If there is no confident edit anywhere in the full text, return suggestions: [] and correctedText equal to the input fullText.
- replacement must differ from original.
- Do not invent spans, sentence IDs, or fields.

Required top-level fields:
requestId, correctedText, documentAssessment, suggestions

Required JSON:
{
  "requestId": "string",
  "correctedText": "string",
  "documentAssessment": {
    "summary": "string",
    "overallQuality": "poor|fair|good|excellent",
    "language": "bn|en|mixed|unknown"
  },
  "suggestions": [
    {
      "id": "string",
      "sentenceId": "string",
      "original": "string",
      "replacement": "string",
      "issueType": "spelling|grammar|punctuation|spacing|repeated_word|fluency|sentence_rewrite|style|clarity|tone|word_choice|other",
      "severity": "low|medium|high",
      "explanation": "string",
      "confidence": 0.0,
      "start": 0,
      "end": 1
    }
  ]
}"""


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
