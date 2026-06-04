from __future__ import annotations

import json
import logging
import os
import random
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
    if status in {401, 403}:
        return "auth_or_forbidden", f"openrouter_http_{status}_auth_or_forbidden"
    if status == 402:
        return "credits_or_payment_required", "openrouter_http_402_credits_or_payment_required"
    if status == 404:
        return "model_not_found", "openrouter_http_404_model_not_found"
    if status == 429:
        return "rate_limited", "openrouter_http_429_quota_or_rate_limit"
    if status in {408, 504}:
        return "timeout", "openrouter_timeout"
    if status in {500, 502, 503}:
        return "provider_error", "openrouter_provider_or_server_error"
    if status >= 500:
        return "provider_error", "openrouter_provider_or_server_error"
    return "provider_error", "openrouter_http_error"


def _extract_content(response_json: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    error = response_json.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code") or error.get("type")
        return None, str(message) if message else "openrouter_error", None
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, "openrouter_empty_choices", None
    first = choices[0] if isinstance(choices[0], dict) else {}
    finish_reason = str(first.get("finish_reason") or "").lower()
    message = first.get("message") if isinstance(first, dict) else None
    if isinstance(message, dict) and message.get("refusal"):
        return None, "openrouter_refusal", "content_filter"
    if finish_reason in {"content_filter", "refusal", "safety"}:
        return None, "openrouter_refusal", "content_filter"
    if finish_reason in {"length", "error"}:
        return None, f"openrouter_finish_reason_{finish_reason}", "provider_error"
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip() or None, None, None
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
        return joined or None, None, None
    return None, "openrouter_empty_choices", None


def _sentences_for_prompt(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "text": sentence.text, "start": sentence.start, "end": sentence.end}
        for idx, sentence in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "text": text, "start": 0, "end": len(text)}]



def _provider_error_message(response: Any) -> str:
    try:
        body = response.json()
    except Exception:
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        parts = [error.get("message"), error.get("code"), error.get("type")]
        return " ".join(str(part) for part in parts if part)
    return str(error) if error else ""


def _looks_like_max_completion_token_error(message: str) -> bool:
    lowered = message.lower()
    return "max_completion_tokens" in lowered or ("max tokens" in lowered and "max_tokens" in lowered)


def _with_max_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    if "max_completion_tokens" not in payload:
        return payload
    copied = dict(payload)
    copied["max_tokens"] = copied.pop("max_completion_tokens")
    return copied


def _strict_json_prompt_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    strict_suffix = (
        "\n\nOpenRouter structured response_format was not accepted for this provider. "
        "You must still return strict JSON only. Do not include markdown, prose, "
        "code fences, comments, or any text outside the JSON object."
    )
    strict_messages: list[dict[str, str]] = []
    for message in messages:
        if message.get("role") == "system":
            strict_messages.append({**message, "content": f"{message.get('content', '')}{strict_suffix}"})
        else:
            strict_messages.append(dict(message))
    return strict_messages


def _retry_after_seconds(response: Any, fallback: float) -> float:
    headers = getattr(response, "headers", {}) or {}
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        if raw is not None:
            return max(0.0, min(float(raw), 2.0))
    except (TypeError, ValueError):
        pass
    return fallback


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
    background: bool = False,
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
        title = os.environ["OPENROUTER_APP_TITLE"].strip()
        headers["X-Title"] = title
        headers["X-OpenRouter-Title"] = title
    max_tokens = int(os.environ.get("SHUDDHO_LLM_MAX_COMPLETION_TOKENS", "1400") or "1400")
    base_payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_completion_tokens": max_tokens,
        "stream": False,
    }
    payload = {**base_payload, "response_format": _structured_response_format()}
    warnings: list[str] = []
    response_mode = "json_schema"
    using_max_tokens = False
    started = time.time()
    http_status: int | None = None
    response: Any = None
    max_retries = 2 if background else 1
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            attempt = 0
            while True:
                response = client.post(OPENROUTER_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
                http_status = response.status_code
                if http_status == 400:
                    provider_message = _provider_error_message(response)
                    if not using_max_tokens and _looks_like_max_completion_token_error(provider_message):
                        warnings.append("openrouter_max_tokens_fallback_used")
                        using_max_tokens = True
                        base_payload = _with_max_tokens(base_payload)
                        payload = _with_max_tokens(payload)
                        continue
                    if response_mode == "json_schema":
                        warnings.append("openrouter_structured_output_fallback_used")
                        response_mode = "strict_json_prompt"
                        base_payload = {**base_payload, "messages": _strict_json_prompt_messages(messages)}
                        payload = base_payload
                        continue
                if http_status in {429, 503} and attempt < max_retries:
                    attempt += 1
                    warnings.append(f"openrouter_retry_after_http_{http_status}")
                    time.sleep(_retry_after_seconds(response, min(2.0, 0.4 * (2 ** (attempt - 1)) + random.uniform(0, 0.2))))
                    continue
                break
    except httpx.TimeoutException:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "openrouter_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except httpx.RequestError:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="network_error", response_mode=response_mode, warnings=[*warnings, "openrouter_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()

    if http_status is not None and http_status >= 400:
        status, warning = _status_for_http(http_status)
        extra_warning = warning
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                code = body["error"].get("code") or body["error"].get("type")
                if code:
                    extra_warning = f"{warning}:{code}"
        except Exception:
            pass
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status=status, response_mode=response_mode, http_status=http_status, warnings=[*warnings, extra_warning], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        response_json = response.json()
    except json.JSONDecodeError:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_invalid_json"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    content, content_warning, content_status = _extract_content(response_json)
    if content_warning:
        status = content_status or ("invalid_schema" if content_warning == "openrouter_empty_choices" else "provider_error")
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status=status, response_mode=response_mode, http_status=http_status, warnings=[*warnings, content_warning], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    if content is None:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="invalid_schema", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_empty_choices"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        parsed = extract_json_payload(content)
    except Exception:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_invalid_json"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    raw_count = raw_suggestion_count(parsed)
    try:
        review = validate_ai_review_payload(parsed, rid, text)
    except Exception:
        return LlmProviderResult(provider="openrouter", model=model, called=True, configured=True, parsed=True, status="invalid_schema", response_mode=response_mode, http_status=http_status, warnings=[*warnings, "openrouter_invalid_schema"], usage=response_json.get("usage") or {}, timings={"llm_ms": int((time.time()-started)*1000)}, ai_raw_suggestion_count=raw_count).model_dump()
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
        ai_raw_suggestion_count=raw_count,
    ).model_dump()
