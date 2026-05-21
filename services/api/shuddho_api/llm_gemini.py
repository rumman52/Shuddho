from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

_ALLOWED_TYPES = {"grammar", "spelling", "style", "tone", "rewrite", "punctuation", "spacing"}

PROMPT_TEMPLATE = """You are Shuddho, a Bangla writing assistant.

Your job is to find Bangla writing issues and suggest improvements.

Rules:
- Do not translate Bangla into English.
- Do not change the meaning.
- Prefer natural standard written Bangla.
- Keep suggestions short and precise.
- Return only valid JSON.
- Do not include markdown.
- Do not include extra explanation outside JSON.
- If no correction is needed, return {\"suggestions\":[]}.
- Do not invent facts.
- Do not rewrite the whole text unless necessary.

Return JSON exactly in this shape:

{
  \"suggestions\": [
    {
      \"type\": \"grammar\",
      \"originalText\": \"গেছিলাম\",
      \"suggestedText\": \"গিয়েছিলাম\",
      \"explanationBn\": \"লিখিত বাংলায় ‘গিয়েছিলাম’ বেশি প্রমিত।\",
      \"confidence\": 0.85
    }
  ]
}

Allowed type values:
- grammar
- spelling
- style
- tone
- rewrite
- punctuation
- spacing

User text:
{{TEXT}}"""


@dataclass
class GeminiResult:
    suggestions: list[dict[str, Any]]
    warnings: list[str]


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    for c in candidates:
        for part in (c.get("content") or {}).get("parts") or []:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text
    return ""


def _parse_json_object(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    candidates = [raw.strip()]
    fenced = re.sub(r"^```json\s*|```$", "", raw.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    if fenced and fenced not in candidates:
        candidates.append(fenced)
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.append(match.group(0))
    for item in candidates:
        try:
            parsed = json.loads(item)
            if isinstance(parsed, dict):
                return parsed, None
        except json.JSONDecodeError:
            continue
    return None, "gemini_invalid_json"


def call_gemini(*, text: str, api_key: str, model: str, timeout_seconds: float = 20.0) -> tuple[str, str | None]:
    prompt = PROMPT_TEMPLATE.replace("{{TEXT}}", text)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "topP": 0.8, "maxOutputTokens": 2048},
            },
        )
        if response.status_code >= 400:
            return "", f"gemini_http_{response.status_code}"
        return _extract_text(response.json()), None


def parse_and_normalize(*, user_text: str, raw_text: str) -> GeminiResult:
    parsed, parse_warning = _parse_json_object(raw_text)
    if not parsed:
        return GeminiResult(suggestions=[], warnings=[parse_warning or "gemini_invalid_response"])
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, item in enumerate(parsed.get("suggestions") or []):
        if not isinstance(item, dict):
            continue
        suggestion_type = str(item.get("type") or "style").strip().lower()
        if suggestion_type not in _ALLOWED_TYPES:
            suggestion_type = "style"
        original = str(item.get("originalText") or "").strip()
        suggested = str(item.get("suggestedText") or "").strip()
        if not original or not suggested:
            continue
        confidence = item.get("confidence", 0.7)
        try:
            confidence_num = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_num = 0.7
        start = user_text.find(original)
        end = start + len(original) if start >= 0 else 0
        if start < 0:
            start = 0
            warnings.append("gemini_span_not_found")
        stable_id = hashlib.sha1(f"gemini|{original}|{suggested}|{index}".encode("utf-8")).hexdigest()[:16]
        explanation = str(item.get("explanationBn") or "জেমিনি প্রস্তাবিত সংশোধন।").strip()
        out.append({
            "id": stable_id,
            "rule_id": "gemini_smart_correction",
            "category": suggestion_type,
            "type": suggestion_type,
            "originalText": original,
            "suggestedText": suggested,
            "explanationBn": explanation,
            "confidence": confidence_num,
            "source": "gemini",
            "span_start": start,
            "span_end": end,
            "original_text": original,
            "replacement_options": [suggested],
            "explanation_bn": explanation,
        })
    if parse_warning:
        warnings.append(parse_warning)
    return GeminiResult(suggestions=out, warnings=list(dict.fromkeys(warnings)))
