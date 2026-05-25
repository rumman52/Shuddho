from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
ALLOWED_TYPES = {"spelling", "grammar", "punctuation", "style", "fluency"}
SYSTEM_PROMPT = (
    "You are Shuddho AI Reviewer. Return strict JSON only. Do not use markdown. "
    "Do not explain outside JSON. Only suggest corrections for exact substrings from the input."
)


def _build_prompt(text: str) -> str:
    return f"""You are correcting Bangla writing for Shuddho.

Input text:
<<<TEXT
{text}
TEXT

Return strict JSON only in this exact shape:

{{
  "suggestions": [
    {{
      "type": "grammar",
      "message": "short Bangla or English explanation",
      "original": "exact substring from the input",
      "replacement": "corrected text",
      "start": null,
      "end": null,
      "confidence": 0.85,
      "source": "openrouter"
    }}
  ]
}}

Rules:
- Return only JSON.
- No markdown.
- No explanation outside JSON.
- If there are no problems, return {{"suggestions":[]}}.
- "original" must be an exact substring from the input text.
- Do not invent text that is not present.
- Do not rewrite the whole paragraph.
- Prefer short precise corrections.
- Find grammar, spelling, punctuation, style, and fluency problems.
- If offsets are uncertain, use null for start and end.
- source must be "openrouter"."""


def _strip_fences(content: str) -> str:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\\s*```$", "", cleaned)
    return cleaned.strip()


def _map_http(status: int) -> str:
    return {
        400: "openrouter_http_error",
        401: "openrouter_http_401_invalid_key",
        402: "openrouter_http_402_payment_required",
        403: "openrouter_http_403_forbidden",
        404: "openrouter_http_404_model_not_found",
        408: "openrouter_timeout",
        413: "openrouter_http_413_content_too_large",
        429: "openrouter_http_429_quota_or_rate_limit",
        500: "openrouter_provider_or_server_error",
        502: "openrouter_provider_or_server_error",
        503: "openrouter_provider_or_server_error",
        504: "openrouter_provider_or_server_error",
    }.get(status, "openrouter_http_error")


def _structured_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "shuddho_corrections",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "type": {"type": "string", "enum": sorted(ALLOWED_TYPES)},
                                "message": {"type": "string"},
                                "original": {"type": "string"},
                                "replacement": {"type": "string"},
                                "start": {"type": ["integer", "null"]},
                                "end": {"type": ["integer", "null"]},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "source": {"type": "string", "enum": ["openrouter"]},
                            },
                            "required": [
                                "type",
                                "message",
                                "original",
                                "replacement",
                                "start",
                                "end",
                                "confidence",
                                "source",
                            ],
                        },
                    }
                },
                "required": ["suggestions"],
            },
        },
    }


def _normalize_suggestions(input_text: str, items: Any, model: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    seen: set[tuple[str, str, int, int]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        original = item.get("original")
        replacement = item.get("replacement")
        if not isinstance(original, str) or not isinstance(replacement, str):
            continue
        if not original.strip() or not replacement.strip():
            continue

        start = item.get("start")
        end = item.get("end")
        if isinstance(start, int) and isinstance(end, int) and end > start and input_text[start:end] == original:
            span_start, span_end = start, end
        else:
            found = input_text.find(original)
            if found < 0:
                out.append({"_warning": "openrouter_original_not_found"})
                continue
            span_start, span_end = found, found + len(original)

        kind = item.get("type") if isinstance(item.get("type"), str) else "grammar"
        kind = kind if kind in ALLOWED_TYPES else "grammar"

        try:
            confidence = float(item.get("confidence", 0.75))
        except (TypeError, ValueError):
            confidence = 0.75
        if confidence < 0.75 or confidence > 1:
            confidence = 0.75
        if original.strip() == input_text.strip():
            continue

        key = (original, replacement, span_start, span_end)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": f"openrouter-{span_start}-{span_end}-{len(out)}",
                "rule_id": f"openrouter.{kind}",
                "category": kind,
                "type": kind,
                "severity": "medium",
                "originalText": original,
                "suggestedText": replacement,
                "replacement_options": [replacement],
                "replacementOptions": [replacement],
                "span_start": span_start,
                "span_end": span_end,
                "spanStart": span_start,
                "spanEnd": span_end,
                "explanationBn": str(item.get("message") or "প্রস্তাবিত সংশোধন"),
                "confidence": confidence,
                "source": "model",
                "provider": "openrouter",
                "model": model,
                "metadata": {"llm": True},
            }
        )
    return out


def _extract_content(response_json: dict[str, Any]) -> str | None:
    content = ((((response_json.get("choices") or [{}])[0]).get("message") or {}).get("content"))
    return content if isinstance(content, str) and content.strip() else None


def run_openrouter_check(
    text: str,
    model: str,
    api_key: str,
    language: str = "bn",
    timeout_seconds: float = 35.0,
) -> dict[str, Any]:
    del language
    model = (model or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
    warnings: list[str] = []

    if not api_key or not api_key.strip():
        return {
            "suggestions": [],
            "warnings": ["openrouter_api_key_missing"],
            "provider": "openrouter",
            "model": model,
            "llm_enabled": True,
        }

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    http_referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
    app_title = os.environ.get("OPENROUTER_APP_TITLE", "").strip()
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    if app_title:
        headers["X-OpenRouter-Title"] = app_title

    base_payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(text)},
        ],
        "temperature": 0.1,
        "max_completion_tokens": 900,
        "stream": False,
    }

    payload = {**base_payload, "response_format": _structured_response_format()}

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(OPENROUTER_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
            if response.status_code == 400:
                warnings.append("openrouter_structured_output_fallback_used")
                response = client.post(OPENROUTER_CHAT_COMPLETIONS_URL, headers=headers, json=base_payload)
    except httpx.TimeoutException:
        return {"suggestions": [], "warnings": ["openrouter_http_408_timeout"], "provider": "openrouter", "model": model, "llm_enabled": True}
    except httpx.RequestError:
        return {"suggestions": [], "warnings": ["openrouter_request_failed"], "provider": "openrouter", "model": model, "llm_enabled": True}

    if response.status_code >= 400:
        warnings.append(_map_http(response.status_code))
        return {"suggestions": [], "warnings": warnings, "provider": "openrouter", "model": model, "llm_enabled": True}

    try:
        response_json = response.json()
    except json.JSONDecodeError:
        warnings.append("openrouter_invalid_json")
        return {"suggestions": [], "warnings": warnings, "provider": "openrouter", "model": model, "llm_enabled": True}

    content = _extract_content(response_json)
    if content is None:
        warnings.append("openrouter_empty_response")
        return {"suggestions": [], "warnings": warnings, "provider": "openrouter", "model": model, "llm_enabled": True}

    try:
        parsed = json.loads(_strip_fences(content))
    except json.JSONDecodeError:
        warnings.append("openrouter_invalid_json")
        return {"suggestions": [], "warnings": warnings, "provider": "openrouter", "model": model, "llm_enabled": True}

    raw = _normalize_suggestions(text, parsed.get("suggestions") if isinstance(parsed, dict) else None, model)
    warnings.extend([item["_warning"] for item in raw if isinstance(item, dict) and "_warning" in item])
    suggestions = [item for item in raw if isinstance(item, dict) and "_warning" not in item]
    return {
        "suggestions": suggestions,
        "warnings": warnings,
        "provider": "openrouter",
        "model": model,
        "llm_enabled": True,
    }
