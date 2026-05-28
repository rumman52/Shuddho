from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from services.api.shuddho_api.ai_review_schema import (
    build_review_messages,
    extract_json_payload,
    required_output_schema,
    validate_ai_review_payload,
)
from services.api.shuddho_api.llm_candidates import split_bangla_sentences
from services.api.shuddho_api.llm_provider import DEFAULT_OPENROUTER_MODEL, LlmProviderResult

logger = logging.getLogger(__name__)
OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def _structured_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "shuddho_ai_review",
            "strict": True,
            "schema": required_output_schema(),
        },
    }


def _status_for_http(status: int) -> tuple[str, str]:
    if status == 429:
        return "rate_limited", "openrouter_http_429_quota_or_rate_limit"
    if status in {408, 504}:
        return "timeout", "openrouter_timeout"
    if status in {401, 403}:
        return "provider_error", f"openrouter_http_{status}_auth_or_forbidden"
    if status == 404:
        return "provider_error", "openrouter_http_404_model_not_found"
    if status >= 500:
        return "provider_error", "openrouter_provider_or_server_error"
    return "provider_error", "openrouter_http_error"


def _extract_content(response_json: dict[str, Any]) -> str | None:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(part, str):
                parts.append(part)
        joined = "".join(parts).strip()
        return joined or None
    return None


def _sentences_for_prompt(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "text": sentence.text, "start": sentence.start, "end": sentence.end}
        for idx, sentence in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "text": text, "start": 0, "end": len(text)}]


def run_openrouter_check(
    text: str,
    model: str,
    api_key: str,
    language: str = "bn",
    timeout_seconds: float = 35.0,
    *,
    request_id: str = "",
    sentences: list[dict[str, Any]] | None = None,
    local_suggestions: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    del language
    rid = request_id or os.environ.get("SHUDDHO_REQUEST_ID", "unknown")
    model = (model or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
    if not api_key or not api_key.strip():
        return LlmProviderResult(
            provider="openrouter", model=model, configured=False, status="missing_key",
            warnings=["openrouter_api_key_missing"], response_mode="json_schema",
        ).model_dump()

    messages = build_review_messages(
        request_id=rid,
        full_text=text,
        sentences=sentences or _sentences_for_prompt(text),
        local_suggestions=local_suggestions or [],
        candidate_sentences=candidates or [],
    )
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    if os.environ.get("OPENROUTER_HTTP_REFERER", "").strip():
        headers["HTTP-Referer"] = os.environ["OPENROUTER_HTTP_REFERER"].strip()
    if os.environ.get("OPENROUTER_APP_TITLE", "").strip():
        headers["X-OpenRouter-Title"] = os.environ["OPENROUTER_APP_TITLE"].strip()
    base_payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_completion_tokens": 1400,
        "stream": False,
    }
    payload = {**base_payload, "response_format": _structured_response_format()}
    warnings: list[str] = []
    response_mode = "json_schema"
    started = time.time()
    http_status: int | None = None
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(OPENROUTER_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
            http_status = response.status_code
            if response.status_code == 400:
                warnings.append("openrouter_structured_output_fallback_used")
                response_mode = "strict_json_prompt"
                response = client.post(OPENROUTER_CHAT_COMPLETIONS_URL, headers=headers, json=base_payload)
                http_status = response.status_code
    except httpx.TimeoutException:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=["openrouter_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except httpx.RequestError:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="network_error", response_mode=response_mode, warnings=["openrouter_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()

    if http_status is not None and http_status >= 400:
        status, warning = _status_for_http(http_status)
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status=status, response_mode=response_mode, http_status=http_status, warnings=[*warnings, warning], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        response_json = response.json()
    except json.JSONDecodeError:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_invalid_json"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    content = _extract_content(response_json)
    if content is None:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="invalid_schema", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_empty_choices"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        parsed = extract_json_payload(content)
    except Exception:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_invalid_json"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        review = validate_ai_review_payload(parsed, rid, text)
    except Exception:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, parsed=True, status="invalid_schema", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_invalid_schema"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    status = "completed" if review.suggestions else "completed_empty"
    return LlmProviderResult(
        suggestions=[s.model_dump() for s in review.suggestions],
        correctedText=review.correctedText,
        documentAssessment=review.documentAssessment.model_dump(),
        warnings=warnings,
        provider="openrouter",
        model=model,
        called=True,
        configured=True,
        parsed=True,
        status=status,
        response_mode=response_mode,
        http_status=http_status,
        usage=response_json.get("usage") or {},
        timings={"llm_ms": int((time.time()-started)*1000)},
    ).model_dump()
