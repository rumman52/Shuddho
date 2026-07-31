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


def _function_schema() -> dict[str, Any]:
    suggestion = {
        "type": "object",
        "properties": {
            "id": {"type": "string"}, "sentenceId": {"type": "string"},
            "original": {"type": "string"}, "replacement": {"type": "string"},
            "issueType": {"type": "string"}, "severity": {"type": "string"},
            "explanation": {"type": "string"}, "confidence": {"type": "number"},
            "start": {"type": "integer"}, "end": {"type": "integer"},
        },
        "required": ["id", "sentenceId", "original", "replacement", "issueType", "severity", "explanation", "confidence", "start", "end"],
    }
    return {
        "type": "object",
        "properties": {
            "requestId": {"type": "string"}, "correctedText": {"type": "string"},
            "documentAssessment": {
                "type": "object", "properties": {
                    "summary": {"type": "string"}, "overallQuality": {"type": "string"}, "language": {"type": "string"},
                }, "required": ["summary", "overallQuality", "language"],
            },
            "suggestions": {"type": "array", "items": suggestion},
        },
        "required": ["requestId", "correctedText", "documentAssessment", "suggestions"],
    }


def _config(response_mode: str, timeout_seconds: float, system_instruction: str) -> Any:
    from google.genai import types
    thinking_level = (os.environ.get("SHUDDHO_GEMMA_THINKING_LEVEL") or "minimal").strip().lower()
    if thinking_level not in {"minimal", "low", "medium", "high"}:
        thinking_level = "minimal"
    kwargs: dict[str, Any] = {
        "temperature": 1.0, "top_p": 0.95, "top_k": 64,
        "max_output_tokens": _bounded_int("SHUDDHO_LLM_MAX_COMPLETION_TOKENS", 1400, 256, 8192),
        "thinking_config": types.ThinkingConfig(thinking_level=thinking_level),
        "http_options": types.HttpOptions(timeout=int(max(1, timeout_seconds) * 1000), retry_options=types.HttpRetryOptions(attempts=1)),
        "system_instruction": system_instruction,
    }
    if response_mode == "function_call":
        name = "submit_shuddho_review"
        kwargs["tools"] = [types.Tool(function_declarations=[{"name": name, "description": "Submit the complete Shuddho Bangla review.", "parameters": _function_schema()}])]
        kwargs["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=[name]))
    else:
        kwargs["response_mime_type"] = "application/json"
        if response_mode == "json_schema":
            kwargs["response_json_schema"] = required_output_schema()
    return types.GenerateContentConfig(**kwargs)


def _call(client: Any, model: str, messages: list[dict[str, str]], timeout_seconds: float, response_mode: str) -> Any:
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    return client.models.generate_content(model=model, contents=user, config=_config(response_mode, timeout_seconds, system))


def _value(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _finish_metadata(response: Any) -> tuple[str | None, int]:
    candidates = _value(response, "candidates", []) or []
    reason = _value(candidates[0], "finish_reason") if candidates else None
    reason = _value(reason, "value", reason)
    return (str(reason) if reason is not None else None), len(candidates)


def _function_payload(response: Any) -> tuple[dict[str, Any] | None, str | None]:
    calls = _value(response, "function_calls", []) or []
    for call in calls:
        name = _value(call, "name")
        if name == "submit_shuddho_review":
            args = _value(call, "args")
            return (dict(args) if isinstance(args, dict) else None), name
    return None, (_value(calls[0], "name") if calls else None)


def _result(*, model: str, status: str, response_mode: str, started: float, timeout_seconds: float,
            warning: str, called: bool = True, usage: dict[str, Any] | None = None,
            diagnostics: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    safe = {"response_mode": response_mode, "provider_timeout_seconds": timeout_seconds, **(diagnostics or {})}
    safe.update(usage or {})
    return LlmProviderResult(provider="gemma", model=model, called=called, configured=True, status=status,
        response_mode=response_mode, warnings=[warning] if warning else [], usage=usage or {},
        timings={"llm_ms": int((time.time()-started)*1000)}, diagnostics=safe, **kwargs).model_dump()


def run_gemma_check(text: str, model: str, api_key: str, timeout_seconds: float = 40.0, *, request_id: str = "",
                    sentences: list[dict[str, Any]] | None = None, local_suggestions: list[dict[str, Any]] | None = None,
                    candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rid = request_id or "unknown"
    model = (model or DEFAULT_GEMMA_MODEL).strip() or DEFAULT_GEMMA_MODEL
    response_mode = (os.environ.get("SHUDDHO_GEMMA_RESPONSE_MODE") or "function_call").strip().lower()
    if response_mode not in {"function_call", "json_mime", "json_schema"}: response_mode = "function_call"
    if model.lower().startswith("gemini-") or not model.lower().startswith("gemma-"):
        return LlmProviderResult(provider="gemma", model=model, configured=False, status="unsupported_provider", warnings=["unsupported_model_gemma_only"]).model_dump()
    if not api_key or not api_key.strip():
        return LlmProviderResult(provider="gemma", model=model, configured=False, status="missing_key", response_mode=response_mode, warnings=["google_api_key_missing"]).model_dump()
    messages = build_review_messages(request_id=rid, full_text=text, sentences=sentences or _sentences_for_prompt(text), local_suggestions=local_suggestions or [], candidate_sentences=candidates or [])
    started = time.time()
    try:
        from google import genai
        client = genai.Client(api_key=api_key.strip())
        response = _call(client, model, messages, timeout_seconds, response_mode)
    except ImportError:
        return _result(model=model, status="dependency_missing", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="google_genai_dependency_missing", called=False)
    except (TimeoutError, socket.timeout):
        return _result(model=model, status="timeout", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_timeout", diagnostics={"exception_class": "TimeoutError"})
    except Exception as exc:
        code = _http_status(exc)
        diag = {"exception_class": type(exc).__name__}
        if isinstance(exc, (AttributeError, TypeError)):
            return _result(model=model, status="provider_error", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_client_configuration_error", diagnostics=diag)
        if code is not None:
            status, warning = _status_for_http(code, str(exc))
            return _result(model=model, status=status, response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning=warning, http_status=code, error_code=warning, retry_after_seconds=_retry_after_from_exc(exc), diagnostics=diag)
        if isinstance(exc, (OSError, ConnectionError)):
            if "timeout" in type(exc).__name__.lower():
                return _result(model=model, status="timeout", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_timeout", diagnostics=diag)
            return _result(model=model, status="network_error", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_request_failed", diagnostics=diag)
        return _result(model=model, status="provider_error", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_client_configuration_error", diagnostics=diag)

    usage = _usage(response)
    finish_reason, candidate_count = _finish_metadata(response)
    parsed, function_name = _function_payload(response)
    content = _response_text(response)
    diag: dict[str, Any] = {"finish_reason": finish_reason, "candidate_count": candidate_count,
        "has_function_call": parsed is not None or function_name is not None, "function_call_name": function_name,
        "provider_output_chars": len(content or ""), "truncated": str(finish_reason).upper().endswith("MAX_TOKENS")}
    if _safety_blocked(response):
        return _result(model=model, status="content_filter", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_safety_blocked", usage=usage, diagnostics=diag)
    if diag["truncated"]:
        return _result(model=model, status="truncated", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_truncated", usage=usage, diagnostics=diag)
    if parsed is None and response_mode == "function_call":
        return _result(model=model, status="invalid_schema", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_missing_function_call", usage=usage, diagnostics=diag)
    if parsed is None:
        if content is None:
            return _result(model=model, status="invalid_schema", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_empty_output", usage=usage, diagnostics=diag)
        cleaned = content.lstrip("\ufeff").strip()
        diag.update({"starts_with_object": cleaned.startswith("{"), "ends_with_object": cleaned.endswith("}"), "had_markdown_fence": cleaned.startswith("```")})
        try:
            parsed = extract_json_payload(content)
        except Exception as exc:
            diag.update({"json_error_class": type(exc).__name__, "json_error_message": str(exc)[:160], "json_error_position": getattr(exc, "pos", None)})
            return _result(model=model, status="invalid_json", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_invalid_json", usage=usage, diagnostics=diag)
    raw_count = raw_suggestion_count(parsed)
    try:
        review = validate_ai_review_payload(parsed, rid, text)
    except Exception as exc:
        diag["exception_class"] = type(exc).__name__
        return _result(model=model, status="invalid_schema", response_mode=response_mode, started=started, timeout_seconds=timeout_seconds, warning="gemma_invalid_schema", usage=usage, diagnostics=diag, parsed=True, ai_raw_suggestion_count=raw_count)
    return _result(model=model, status="completed" if review.suggestions else "completed_empty", response_mode=response_mode,
        started=started, timeout_seconds=timeout_seconds, warning="", usage=usage, diagnostics=diag, parsed=True,
        suggestions=[s.model_dump() for s in review.suggestions], correctedText=review.correctedText,
        documentAssessment=review.documentAssessment.model_dump(), ai_raw_suggestion_count=raw_count)
