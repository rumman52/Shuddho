from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

_ALLOWED_TYPES = {"spelling", "grammar", "punctuation", "spacing", "style", "tone"}

PROMPT_TEMPLATE = """Analyze this Bangla text and return correction suggestions as strict JSON only.
Return exactly this shape:
{"suggestions":[{"type":"grammar","message":"কথ্য রূপের পরিবর্তে মানক রূপ ব্যবহার করুন।","original":"গেছিলাম","replacement":"গিয়েছিলাম","start":null,"end":null,"confidence":0.85,"source":"openrouter"}]}
Rules:
- Return JSON only.
- No markdown.
- No explanation outside JSON.
- original must be an exact substring from the input text.
- Do not invent or paraphrase original text.
- suggestions must be an array.
- type must be one of: spelling, grammar, punctuation, spacing, style, tone.
- source must be openrouter.
- If no issues found, return {"suggestions":[]}.
- If no exact substring exists for a candidate, return {"suggestions":[]}.
- If exact character offsets are uncertain, use null for start/end.
Text:
{{TEXT}}"""


@dataclass
class OpenRouterResult:
    suggestions: list[dict[str, Any]]
    warnings: list[str]


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
    return None, "openrouter_invalid_json"


OPENROUTER_HTTP_REFERER_ENV_VAR = "OPENROUTER_HTTP_REFERER"
OPENROUTER_APP_TITLE_ENV_VAR = "OPENROUTER_APP_TITLE"
DEFAULT_OPENROUTER_HTTP_REFERER = "https://shuddho-web-editor.vercel.app"
DEFAULT_OPENROUTER_APP_TITLE = "Shuddho"


def _openrouter_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    http_referer = os.environ.get(
        OPENROUTER_HTTP_REFERER_ENV_VAR,
        DEFAULT_OPENROUTER_HTTP_REFERER,
    ).strip()

    app_title = os.environ.get(
        OPENROUTER_APP_TITLE_ENV_VAR,
        DEFAULT_OPENROUTER_APP_TITLE,
    ).strip()

    if http_referer:
        headers["HTTP-Referer"] = http_referer

    if app_title:
        headers["X-OpenRouter-Title"] = app_title

    return headers


def call_openrouter(*, text: str, api_key: str, model: str, timeout_seconds: float = 20.0) -> tuple[str, str | None]:
    prompt = PROMPT_TEMPLATE.replace("{{TEXT}}", text)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=_openrouter_headers(api_key),
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are Shuddho, a Bangla writing correction engine. Return strict JSON only. Do not use markdown."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_completion_tokens": 800,
                },
            )
            if response.status_code >= 400:
                status_map = {
                    400: "openrouter_http_400_bad_request",
                    401: "openrouter_http_401_invalid_key",
                    402: "openrouter_http_402_payment_required",
                    403: "openrouter_http_403_key_or_permission",
                    404: "openrouter_http_404_model_not_found",
                    408: "openrouter_http_408_timeout",
                    429: "openrouter_http_429_quota_or_rate_limit",
                    500: "openrouter_http_500_server_error",
                    502: "openrouter_http_502_bad_gateway",
                    503: "openrouter_http_503_unavailable",
                }
                return "", status_map.get(response.status_code, "openrouter_request_failed")
            payload = response.json()
            content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
            if not isinstance(content, str) or not content.strip():
                return "", "openrouter_empty_response"
            return content, None
    except httpx.TimeoutException:
        return "", "openrouter_http_408_timeout"
    except httpx.HTTPError:
        return "", "openrouter_request_failed"
    except Exception:
        return "", "openrouter_request_failed"


def parse_and_normalize(*, user_text: str, raw_text: str) -> OpenRouterResult:
    parsed, parse_warning = _parse_json_object(raw_text)
    if not parsed:
        return OpenRouterResult(suggestions=[], warnings=[parse_warning or "openrouter_invalid_json"])
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, item in enumerate(parsed.get("suggestions") or []):
        if not isinstance(item, dict):
            warnings.append("openrouter_invalid_suggestion_shape")
            continue
        suggestion_type = str(item.get("type") or "style").strip().lower()
        if suggestion_type not in _ALLOWED_TYPES:
            suggestion_type = "style"
        original = str(item.get("original") or item.get("originalText") or "").strip()
        suggested = str(item.get("replacement") or item.get("suggestedText") or "").strip()
        if not original or not suggested:
            continue
        start = item.get("start")
        end = item.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            idx = user_text.find(original)
            if idx >= 0:
                start, end = idx, idx + len(original)
            else:
                start, end = None, None
        confidence = item.get("confidence", 0.7)
        try:
            confidence_num = max(0.0, min(1.0, float(confidence)))
        except Exception:
            confidence_num = 0.7
        message = str(item.get("message") or "ওপেনরাউটার প্রস্তাবিত সংশোধন।").strip()
        stable_id = hashlib.sha1(f"openrouter|{original}|{suggested}|{index}".encode("utf-8")).hexdigest()[:16]
        out.append({
            "id": stable_id,
            "rule_id": "openrouter_smart_correction",
            "category": suggestion_type,
            "type": suggestion_type,
            "message": message,
            "original": original,
            "replacement": suggested,
            "start": start,
            "end": end,
            "originalText": original,
            "suggestedText": suggested,
            "explanationBn": message,
            "confidence": confidence_num,
            "source": "openrouter",
            "span_start": start,
            "span_end": end,
            "replacement_options": [suggested],
        })
    if parse_warning:
        warnings.append(parse_warning)
    return OpenRouterResult(suggestions=out, warnings=list(dict.fromkeys(warnings)))
