from __future__ import annotations

import json
import os
import socket
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any

from services.api.shuddho_api.ai_review_schema import (
    build_review_messages,
    extract_json_payload,
    required_output_schema,
    raw_suggestion_count,
    validate_ai_review_payload,
)
from services.api.shuddho_api.llm_candidates import split_bangla_sentences
from services.api.shuddho_api.llm_provider import DEFAULT_GEMMA_MODEL, LlmProviderResult


def _sentences_for_prompt(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "text": sentence.text, "start": sentence.start, "end": sentence.end}
        for idx, sentence in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "text": text, "start": 0, "end": len(text)}]


def _is_schema_400(status: int | None, message: str = "") -> bool:
    lowered = message.lower()
    return status == 400 and any(marker in lowered for marker in ("schema", "response_schema", "response_json_schema", "json schema"))


def _status_for_http(status: int, message: str = "") -> tuple[str, str]:
    lowered = message.lower()
    if status == 400 and ("safety" in lowered or "blocked" in lowered or "prohibited" in lowered):
        return "content_filter", "gemma_safety_blocked"
    if _is_schema_400(status, message):
        return "invalid_schema", "gemma_invalid_schema"
    if status in {401, 403}:
        return "auth_or_forbidden", f"gemma_http_{status}_auth_or_forbidden"
    if status == 404:
        return "model_not_found", "gemma_http_404_model_not_found"
    if status == 429:
        return "rate_limited", "gemma_http_429_quota_or_rate_limit"
    if status in {408, 504}:
        return "timeout", "gemma_timeout"
    if status >= 500:
        return "provider_error", "gemma_provider_or_server_error"
    return "provider_error", "gemma_http_error"



def _retry_after_from_exc(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or getattr(exc, "headers", None) or {}
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
        except Exception:
            return None

def _http_status(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _response_text(response: Any) -> str | None:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    parts: list[str] = []
    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, list):
        for candidate in candidates:
            content = getattr(candidate, "content", None) or (candidate.get("content") if isinstance(candidate, dict) else None)
            cparts = getattr(content, "parts", None) or (content.get("parts") if isinstance(content, dict) else None)
            if isinstance(cparts, list):
                for part in cparts:
                    value = getattr(part, "text", None) or (part.get("text") if isinstance(part, dict) else None)
                    if isinstance(value, str):
                        parts.append(value)
    joined = "".join(parts).strip()
    return joined or None


def _safety_blocked(response: Any) -> bool:
    prompt_feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(prompt_feedback, "block_reason", None) or (prompt_feedback.get("block_reason") if isinstance(prompt_feedback, dict) else None)
    if block_reason:
        return True
    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, list):
        for candidate in candidates:
            reason = getattr(candidate, "finish_reason", None) or (candidate.get("finish_reason") if isinstance(candidate, dict) else None)
            if str(reason).lower() in {"safety", "blocked", "prohibited_content", "recitation"}:
                return True
    return False


def _usage(response: Any) -> dict[str, Any]:
    meta = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
    if isinstance(meta, dict):
        get = meta.get
    else:
        get = lambda k, d=None: getattr(meta, k, d) if meta is not None else d
    usage = {
        "input_tokens": get("prompt_token_count", get("input_tokens", 0)) or 0,
        "output_tokens": get("candidates_token_count", get("output_tokens", 0)) or 0,
        "thought_tokens": get("thoughts_token_count", get("thought_tokens", 0)) or 0,
        "total_tokens": get("total_token_count", get("total_tokens", 0)) or 0,
    }
    return usage


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or str(default))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _config(response_json_schema: bool, timeout_seconds: float, system_instruction: str) -> Any:
    from google.genai import types
    thinking_level = (os.environ.get("SHUDDHO_GEMMA_THINKING_LEVEL") or "minimal").strip().lower()
    if thinking_level not in {"minimal", "low", "medium", "high"}:
        thinking_level = "minimal"
    kwargs: dict[str, Any] = {
        "temperature": 1.0, "top_p": 0.95, "top_k": 64,
        "response_mime_type": "application/json",
        "max_output_tokens": _bounded_int("SHUDDHO_LLM_MAX_COMPLETION_TOKENS", 1400, 256, 8192),
        "thinking_config": types.ThinkingConfig(thinking_level=thinking_level),
        "http_options": types.HttpOptions(
            timeout=int(max(1, timeout_seconds) * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
        "system_instruction": system_instruction,
    }
    if response_json_schema:
        kwargs["response_json_schema"] = required_output_schema()
    return types.GenerateContentConfig(**kwargs)


def _call(client: Any, model: str, messages: list[dict[str, str]], timeout_seconds: float, structured: bool) -> Any:
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    config = _config(structured, timeout_seconds, system)
    return client.models.generate_content(model=model, contents=user, config=config)


def run_gemma_check(
    text: str,
    model: str,
    api_key: str,
    timeout_seconds: float = 40.0,
    *,
    request_id: str = "",
    sentences: list[dict[str, Any]] | None = None,
    local_suggestions: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rid = request_id or "unknown"
    model = (model or DEFAULT_GEMMA_MODEL).strip() or DEFAULT_GEMMA_MODEL
    if model.lower().startswith("gemini-") or not model.lower().startswith("gemma-"):
        return LlmProviderResult(provider="gemma", model=model, configured=False, status="unsupported_provider", warnings=["unsupported_model_gemma_only"]).model_dump()
    if not api_key or not api_key.strip():
        return LlmProviderResult(provider="gemma", model=model, configured=False, status="missing_key", response_mode="json_mime", warnings=["google_api_key_missing"]).model_dump()
    messages = build_review_messages(request_id=rid, full_text=text, sentences=sentences or _sentences_for_prompt(text), local_suggestions=local_suggestions or [], candidate_sentences=candidates or [])
    started = time.time()
    warnings: list[str] = []
    response_mode = (os.environ.get("SHUDDHO_GEMMA_RESPONSE_MODE") or "json_mime").strip().lower()
    if response_mode not in {"json_mime", "json_schema"}:
        response_mode = "json_mime"
    try:
        try:
            from google import genai
        except ImportError:
            return LlmProviderResult(provider="gemma", model=model, called=False, configured=True, status="dependency_missing", response_mode=response_mode, warnings=[*warnings, "google_genai_dependency_missing"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
        client = genai.Client(api_key=api_key.strip())
        response = _call(client, model, messages, timeout_seconds, response_mode == "json_schema")
    except TimeoutError:
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "gemma_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except (socket.timeout,):
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "gemma_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except (OSError, ConnectionError) as exc:
        if "timeout" in type(exc).__name__.lower():
            return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "gemma_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
        if _http_status(exc) is None:
            return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="network_error", response_mode=response_mode, warnings=[*warnings, "gemma_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
        raise
    except Exception as exc:
        if "timeout" in type(exc).__name__.lower():
            return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "gemma_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
        status_code = _http_status(exc)
        if status_code is not None:
            status, warning = _status_for_http(status_code, str(exc))
            return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status=status, response_mode=response_mode, http_status=status_code, warnings=[*warnings, warning], timings={"llm_ms": int((time.time()-started)*1000)}, error_code=warning, retry_after_seconds=_retry_after_from_exc(exc)).model_dump()
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="network_error", response_mode=response_mode, warnings=[*warnings, "gemma_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()

    usage = _usage(response)
    if _safety_blocked(response):
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="content_filter", response_mode=response_mode, warnings=[*warnings, "gemma_safety_blocked"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    content = _response_text(response)
    if content is None:
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="invalid_schema", response_mode=response_mode, warnings=[*warnings, "gemma_empty_output"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        parsed = extract_json_payload(content)
    except json.JSONDecodeError:
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, warnings=[*warnings, "gemma_invalid_json"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except Exception:
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, warnings=[*warnings, "gemma_invalid_json"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    raw_count = raw_suggestion_count(parsed)
    try:
        review = validate_ai_review_payload(parsed, rid, text)
    except Exception:
        return LlmProviderResult(provider="gemma", model=model, called=True, configured=True, parsed=True, status="invalid_schema", response_mode=response_mode, warnings=[*warnings, "gemma_invalid_schema"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}, ai_raw_suggestion_count=raw_count).model_dump()
    return LlmProviderResult(suggestions=[s.model_dump() for s in review.suggestions], correctedText=review.correctedText, documentAssessment=review.documentAssessment.model_dump(), warnings=warnings, provider="gemma", model=model, called=True, configured=True, parsed=True, status="completed" if review.suggestions else "completed_empty", response_mode=response_mode, usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}, ai_raw_suggestion_count=raw_count).model_dump()
