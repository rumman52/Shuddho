from __future__ import annotations

import json
import socket
import time
from typing import Any

from services.api.shuddho_api.ai_review_schema import (
    build_review_messages,
    extract_json_payload,
    required_output_schema,
    raw_suggestion_count,
    validate_ai_review_payload,
)
from services.api.shuddho_api.llm_candidates import split_bangla_sentences
from services.api.shuddho_api.llm_provider import DEFAULT_GEMINI_MODEL, LlmProviderResult


def _sentences_for_prompt(text: str) -> list[dict[str, Any]]:
    return [
        {"sentenceId": f"s_{idx}", "text": sentence.text, "start": sentence.start, "end": sentence.end}
        for idx, sentence in enumerate(split_bangla_sentences(text))
    ] or [{"sentenceId": "s_0", "text": text, "start": 0, "end": len(text)}]


def _status_for_http(status: int, message: str = "") -> tuple[str, str]:
    lowered = message.lower()
    if status == 400 and ("schema" in lowered or "json" in lowered or "response_schema" in lowered):
        return "invalid_schema", "gemini_invalid_schema"
    if status in {401, 403}:
        return "auth_or_forbidden", f"gemini_http_{status}_auth_or_forbidden"
    if status == 404:
        return "model_not_found", "gemini_http_404_model_not_found"
    if status == 429:
        return "rate_limited", "gemini_http_429_quota_or_rate_limit"
    if status in {408, 504}:
        return "timeout", "gemini_timeout"
    if status >= 500:
        return "provider_error", "gemini_provider_or_server_error"
    return "provider_error", "gemini_http_error"


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
        "total_tokens": get("total_token_count", get("total_tokens", 0)) or 0,
    }
    return usage


def _config(response_schema: bool, timeout_seconds: float) -> Any:
    from google.genai import types
    kwargs: dict[str, Any] = {
        "temperature": 0.1,
        "response_mime_type": "application/json",
        "http_options": types.HttpOptions(timeout=int(max(1, timeout_seconds) * 1000)),
    }
    if response_schema:
        kwargs["response_schema"] = required_output_schema()
    return types.GenerateContentConfig(**kwargs)


def _call(client: Any, model: str, messages: list[dict[str, str]], timeout_seconds: float, structured: bool) -> Any:
    from google.genai import types
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    user = next((m["content"] for m in messages if m.get("role") == "user"), "")
    config = _config(structured, timeout_seconds)
    if hasattr(config, "system_instruction"):
        config.system_instruction = system
        return client.models.generate_content(model=model, contents=user, config=config)
    return client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part(text=user)])],
        config=config,
        system_instruction=system,
    )


def run_gemini_check(
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
    model = (model or DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
    if not api_key or not api_key.strip():
        return LlmProviderResult(provider="gemini", model=model, configured=False, status="missing_key", response_mode="json_schema", warnings=["gemini_api_key_missing"]).model_dump()
    messages = build_review_messages(request_id=rid, full_text=text, sentences=sentences or _sentences_for_prompt(text), local_suggestions=local_suggestions or [], candidate_sentences=candidates or [])
    started = time.time()
    warnings: list[str] = []
    response_mode = "json_schema"
    try:
        from google import genai
        client = genai.Client(api_key=api_key.strip())
        try:
            response = _call(client, model, messages, timeout_seconds, True)
        except Exception as exc:
            status = _http_status(exc)
            message = str(exc)
            if status == 400 and ("schema" in message.lower() or "response_schema" in message.lower() or "json schema" in message.lower()):
                warnings.append("gemini_structured_output_fallback_used")
                response_mode = "json_mime"
                response = _call(client, model, messages, timeout_seconds, False)
            else:
                raise
    except TimeoutError:
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "gemini_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except (socket.timeout,):
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="timeout", response_mode=response_mode, warnings=[*warnings, "gemini_timeout"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except (OSError, ConnectionError) as exc:
        if _http_status(exc) is None:
            return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="network_error", response_mode=response_mode, warnings=[*warnings, "gemini_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
        raise
    except Exception as exc:
        status_code = _http_status(exc)
        if status_code is not None:
            status, warning = _status_for_http(status_code, str(exc))
            return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status=status, response_mode=response_mode, http_status=status_code, warnings=[*warnings, warning], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="network_error", response_mode=response_mode, warnings=[*warnings, "gemini_request_failed"], timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()

    usage = _usage(response)
    if _safety_blocked(response):
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="content_filter", response_mode=response_mode, warnings=[*warnings, "gemini_safety_blocked"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    content = _response_text(response)
    if content is None:
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="invalid_schema", response_mode=response_mode, warnings=[*warnings, "gemini_empty_output"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    try:
        parsed = extract_json_payload(content)
    except json.JSONDecodeError:
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, warnings=[*warnings, "gemini_invalid_json"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    except Exception:
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, status="invalid_json", response_mode=response_mode, warnings=[*warnings, "gemini_invalid_json"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}).model_dump()
    raw_count = raw_suggestion_count(parsed)
    try:
        review = validate_ai_review_payload(parsed, rid, text)
    except Exception:
        return LlmProviderResult(provider="gemini", model=model, called=True, configured=True, parsed=True, status="invalid_schema", response_mode=response_mode, warnings=[*warnings, "gemini_invalid_schema"], usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}, ai_raw_suggestion_count=raw_count).model_dump()
    return LlmProviderResult(suggestions=[s.model_dump() for s in review.suggestions], correctedText=review.correctedText, documentAssessment=review.documentAssessment.model_dump(), warnings=warnings, provider="gemini", model=model, called=True, configured=True, parsed=True, status="completed" if review.suggestions else "completed_empty", response_mode=response_mode, usage=usage, timings={"llm_ms": int((time.time()-started)*1000)}, ai_raw_suggestion_count=raw_count).model_dump()
