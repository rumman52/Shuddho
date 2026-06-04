from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from services.api.shuddho_api.ai_review_schema import (
    build_review_messages,
    extract_json_payload,
    required_output_schema,
    raw_suggestion_count,
    validate_ai_review_payload,
)
from services.api.shuddho_api.llm_candidates import split_bangla_sentences
from services.api.shuddho_api.llm_provider import DEFAULT_OPENAI_MODEL, LlmProviderResult

OPENAI_URL = "https://api.openai.com/v1/responses"


def _extract_response_content(response_json: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Return (text, parsed, refusal) from known Responses API shapes."""
    refusal = response_json.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return None, None, refusal.strip()

    for key in ("output_parsed", "parsed"):
        parsed = response_json.get(key)
        if isinstance(parsed, dict):
            return json.dumps(parsed, ensure_ascii=False), parsed, None

    value = response_json.get("output_text")
    if isinstance(value, str) and value.strip():
        return value.strip(), None, None

    output = response_json.get("output")
    parts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            item_refusal = item.get("refusal")
            if isinstance(item_refusal, str) and item_refusal.strip():
                return None, None, item_refusal.strip()
            parsed = item.get("parsed")
            if isinstance(parsed, dict):
                return json.dumps(parsed, ensure_ascii=False), parsed, None
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_refusal = block.get("refusal")
                    if isinstance(block_refusal, str) and block_refusal.strip():
                        return None, None, block_refusal.strip()
                    if block.get("type") in {"refusal", "output_refusal"}:
                        text = block.get("text") or block.get("content")
                        return None, None, str(text or "openai_refusal")
                    parsed = block.get("parsed")
                    if isinstance(parsed, dict):
                        return json.dumps(parsed, ensure_ascii=False), parsed, None
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
                    if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                        parts.append(block["text"])
    joined = "".join(parts).strip()
    if joined:
        return joined, None, None
    return None, None, None


def _extract_output_text(response_json: dict[str, Any]) -> str | None:
    content, _parsed, _refusal = _extract_response_content(response_json)
    return content

def _sentences_for_prompt(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "text": sentence.text, "start": sentence.start, "end": sentence.end}
        for idx, sentence in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "text": text, "start": 0, "end": len(text)}]


def _status_for_http(status: int) -> tuple[str, str]:
    if status == 429:
        return "rate_limited", "openai_http_429_quota_or_rate_limit"
    if status in {408, 504}:
        return "timeout", "openai_timeout"
    if status in {401, 403}:
        return "auth_or_forbidden", f"openai_http_{status}_auth_or_forbidden"
    if status >= 500:
        return "provider_error", "openai_server_error"
    return "provider_error", "openai_http_error"


def run_openai_check(
    text: str,
    model: str,
    api_key: str,
    timeout_seconds: float = 35.0,
    *,
    request_id: str = "",
    sentences: list[dict[str, Any]] | None = None,
    local_suggestions: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rid = request_id or "unknown"
    model = (model or DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    if "/" in model or ":free" in model:
        return LlmProviderResult(provider="openai", model=model, configured=False, status="unsupported_provider", response_mode="json_schema", warnings=["openai_model_id_suspicious_use_openrouter_provider"]).model_dump()
    if not api_key or not api_key.strip():
        return LlmProviderResult(provider="openai", model=model, configured=False, status="missing_key", response_mode="json_schema", warnings=["openai_api_key_missing"]).model_dump()
    messages = build_review_messages(
        request_id=rid,
        full_text=text,
        sentences=sentences or _sentences_for_prompt(text),
        local_suggestions=local_suggestions or [],
        candidate_sentences=candidates or [],
    )
    payload = {
        "model": model,
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "shuddho_ai_review",
                "strict": True,
                "schema": required_output_schema(),
            }
        },
        "max_output_tokens": int(os.environ.get("SHUDDHO_LLM_MAX_COMPLETION_TOKENS", "1400") or "1400"),
    }
    started = time.time()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(OPENAI_URL, headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}, json=payload)
    except httpx.TimeoutException:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="timeout", response_mode="json_schema", warnings=["openai_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except httpx.RequestError:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="network_error", response_mode="json_schema", warnings=["openai_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    if response.status_code >= 400:
        status, warning = _status_for_http(response.status_code)
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status=status, response_mode="json_schema", http_status=response.status_code, warnings=[warning], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        response_json = response.json()
    except json.JSONDecodeError:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="invalid_json", response_mode="json_schema", http_status=response.status_code, warnings=["openai_invalid_json"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    incomplete = str(response_json.get("status") or "").lower() == "incomplete" or response_json.get("incomplete_details")
    if incomplete:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="provider_error", response_mode="json_schema", http_status=response.status_code, warnings=["openai_incomplete_response"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    content, parsed_direct, refusal = _extract_response_content(response_json)
    if refusal:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="content_filter", response_mode="json_schema", http_status=response.status_code, warnings=["openai_refusal"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    if content is None and parsed_direct is None:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="invalid_schema", response_mode="json_schema", http_status=response.status_code, warnings=["openai_empty_output"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        parsed = parsed_direct if parsed_direct is not None else extract_json_payload(content or "")
    except json.JSONDecodeError:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="invalid_json", response_mode="json_schema", http_status=response.status_code, warnings=["openai_invalid_json"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except Exception:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, status="invalid_json", response_mode="json_schema", http_status=response.status_code, warnings=["openai_invalid_json"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    raw_count = raw_suggestion_count(parsed)
    try:
        review = validate_ai_review_payload(parsed, rid, text)
    except Exception:
        return LlmProviderResult(provider="openai", model=model, called=True, configured=True, parsed=True, status="invalid_schema", response_mode="json_schema", http_status=response.status_code, warnings=["openai_invalid_schema"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}, ai_raw_suggestion_count=raw_count).model_dump()
    return LlmProviderResult(
        suggestions=[s.model_dump() for s in review.suggestions],
        correctedText=review.correctedText,
        documentAssessment=review.documentAssessment.model_dump(),
        warnings=[],
        provider="openai",
        model=model,
        called=True,
        configured=True,
        parsed=True,
        status="completed" if review.suggestions else "completed_empty",
        response_mode="json_schema",
        http_status=response.status_code,
        usage=response_json.get("usage") or {},
        timings={"llm_ms": int((time.time()-started)*1000)},
        ai_raw_suggestion_count=raw_count,
    ).model_dump()
