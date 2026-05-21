from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

_ALLOWED_TYPES = {"grammar", "spelling", "style", "tone", "rewrite", "punctuation", "spacing"}

PROMPT_TEMPLATE = """You are Shuddho, a Bangla writing assistant.
Return corrections for Bangla writing only.
Return strict JSON only with this exact top-level shape:
{"suggestions":[{"type":"grammar","message":"...","original":"...","replacement":"...","start":null,"end":null,"confidence":0.85,"source":"openrouter"}]}
Rules:
- No markdown.
- No extra keys outside the JSON object.
- Focus on grammar, spelling, punctuation, spacing, style.
- Keep meaning unchanged.
- If no correction is needed return {"suggestions":[]}.
User text:
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


def call_openrouter(*, text: str, api_key: str, model: str, timeout_seconds: float = 20.0) -> tuple[str, str | None]:
    prompt = PROMPT_TEMPLATE.replace("{{TEXT}}", text)
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://shuddho-web-editor.vercel.app",
                    "X-Title": "Shuddho",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You only correct Bangla writing and return strict JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
            )
            if response.status_code >= 400:
                status_map = {
                    400: "openrouter_http_400_bad_request",
                    401: "openrouter_http_401_invalid_key",
                    403: "openrouter_http_403_key_or_permission",
                    404: "openrouter_http_404_model_not_found",
                    429: "openrouter_http_429_quota_or_rate_limit",
                }
                return "", status_map.get(response.status_code, "openrouter_request_failed")
            payload = response.json()
            content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
            return content if isinstance(content, str) else "", None
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
