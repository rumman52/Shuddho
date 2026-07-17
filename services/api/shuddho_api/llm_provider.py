from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Literal, Protocol

LLM_STATUSES = {
    "disabled",
    "skipped",
    "missing_key",
    "unsupported_provider",
    "attempted",
    "completed",
    "completed_empty",
    "completed_rejected",
    "timeout",
    "invalid_json",
    "invalid_schema",
    "provider_error",
    "auth_or_forbidden",
    "credits_or_payment_required",
    "model_not_found",
    "content_filter",
    "network_error",
    "rate_limited",
    "failed",
}

ProviderName = Literal["gemini", "openrouter", "openai", "disabled"]
DEFAULT_GEMINI_MODEL = ""
DEFAULT_OPENROUTER_MODEL = ""
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


@dataclass
class LlmProviderResult:
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    correctedText: str | None = None
    documentAssessment: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    provider: str = "disabled"
    model: str = ""
    called: bool = False
    configured: bool = False
    parsed: bool = False
    status: str = "skipped"
    response_mode: str = "none"
    http_status: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, Any] = field(default_factory=dict)
    ai_raw_suggestion_count: int = 0
    ai_valid_suggestion_count: int = 0
    ai_rejected_suggestion_count: int = 0
    rejected_ai_suggestion_count: int = 0
    ai_empty_reason: str | None = None
    provider_attempts: list[dict[str, Any]] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "suggestions": self.suggestions,
            "correctedText": self.correctedText,
            "documentAssessment": self.documentAssessment,
            "warnings": self.warnings,
            "provider": self.provider,
            "model": self.model,
            "called": self.called,
            "configured": self.configured,
            "parsed": self.parsed,
            "status": self.status,
            "response_mode": self.response_mode,
            "http_status": self.http_status,
            "usage": self.usage,
            "timings": self.timings,
            "ai_raw_suggestion_count": self.ai_raw_suggestion_count,
            "ai_valid_suggestion_count": self.ai_valid_suggestion_count,
            "ai_rejected_suggestion_count": self.ai_rejected_suggestion_count,
            "rejected_ai_suggestion_count": self.rejected_ai_suggestion_count,
            "ai_empty_reason": self.ai_empty_reason,
            "provider_attempts": self.provider_attempts,
        }


@dataclass(frozen=True)
class LlmProviderConfig:
    enabled: bool
    provider: str
    model: str
    api_key: str | None
    configured: bool
    warnings: list[str] = field(default_factory=list)
    status: str = "completed"
    fallback_provider: str | None = None
    fallback_model: str = ""
    fallback_api_key: str | None = None
    fallback_configured: bool = False
    fallback_status: str = "skipped"
    fallback_warnings: list[str] = field(default_factory=list)


class LlmReviewProvider(Protocol):
    def review(
        self,
        text: str,
        local_suggestions: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        request_id: str,
        timeout_seconds: float,
    ) -> LlmProviderResult:
        ...


def _truthy(value: str | None) -> bool | None:
    if value is None or value.strip() == "" or value.strip().lower() == "auto":
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}



def _key_for_provider(provider: str, environ: dict[str, str]) -> str | None:
    if provider == "gemini":
        # Google Gen AI SDK precedence: GOOGLE_API_KEY wins when both are set.
        return (environ.get("GOOGLE_API_KEY") or environ.get("GEMINI_API_KEY") or "").strip() or None
    if provider == "openrouter":
        return (environ.get("OPENROUTER_API_KEY") or "").strip() or None
    if provider == "openai":
        return (environ.get("OPENAI_API_KEY") or "").strip() or None
    return None


def _model_for_provider(provider: str, environ: dict[str, str]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if provider == "gemini":
        raw = environ.get("GEMINI_MODEL")
        model = (raw or DEFAULT_GEMINI_MODEL).strip()
        if not model:
            warnings.append("gemini_model_missing")
        if environ.get("GOOGLE_API_KEY") and environ.get("GEMINI_API_KEY"):
            warnings.append("google_api_key_takes_precedence_over_gemini_api_key")
        return model, warnings
    if provider == "openrouter":
        raw = environ.get("OPENROUTER_MODEL")
        model = (raw or DEFAULT_OPENROUTER_MODEL).strip()
        if not model:
            warnings.append("openrouter_model_missing")
        return model, warnings
    if provider == "openai":
        raw = environ.get("OPENAI_MODEL")
        model = (raw or DEFAULT_OPENAI_MODEL).strip()
        if raw is not None and not model:
            warnings.append("openai_model_missing")
        if "/" in model or ":free" in model:
            warnings.append("openai_model_id_suspicious_use_openrouter_provider")
        return model, warnings
    return "", []


def _provider_status(provider: str, model: str, api_key: str | None, warnings: list[str]) -> tuple[bool, str, list[str]]:
    if provider not in {"gemini", "openrouter", "openai"}:
        return False, "unsupported_provider", [*warnings, "unsupported_llm_provider"]
    if provider == "openai" and ("/" in model or ":free" in model):
        return False, "unsupported_provider", warnings
    if not model:
        return False, "missing_key", warnings
    if not api_key:
        missing = {
            "gemini": "gemini_api_key_missing",
            "openrouter": "openrouter_api_key_missing",
            "openai": "openai_api_key_missing",
        }[provider]
        return False, "missing_key", [*warnings, missing]
    return True, "completed", warnings


def resolve_llm_config(env: dict[str, str] | None = None) -> LlmProviderConfig:
    environ = env if env is not None else os.environ
    raw_provider = (environ.get("SHUDDHO_LLM_PROVIDER") or "").strip().lower()
    provider_explicit = bool(raw_provider)
    if raw_provider:
        provider = raw_provider
    elif _key_for_provider("openrouter", environ) and not _key_for_provider("openai", environ):
        provider = "openrouter"
    elif _key_for_provider("gemini", environ) and not _key_for_provider("openai", environ):
        provider = "gemini"
    else:
        provider = "openai"
    enabled_flag = _truthy(environ.get("SHUDDHO_ENABLE_LLM"))

    if provider in {"disabled", "none", "off"}:
        return LlmProviderConfig(False, "disabled", "", None, False, ["llm_disabled"], "disabled")
    if provider not in {"gemini", "openrouter", "openai"}:
        return LlmProviderConfig(False, provider, "", None, False, ["unsupported_llm_provider"], "unsupported_provider")

    model, warnings = _model_for_provider(provider, environ)
    api_key = _key_for_provider(provider, environ)
    configured, status, warnings = _provider_status(provider, model, api_key, warnings)
    enabled = (provider_explicit or bool(api_key)) if enabled_flag is None else enabled_flag

    fallback_raw = (environ.get("SHUDDHO_LLM_FALLBACK_PROVIDER") or "").strip().lower()
    fallback_provider: str | None = None
    fallback_model = ""
    fallback_api_key: str | None = None
    fallback_configured = False
    fallback_status = "skipped"
    fallback_warnings: list[str] = []
    if fallback_raw:
        if fallback_raw in {"disabled", "none", "off"}:
            fallback_status = "disabled"
        elif fallback_raw == provider:
            warnings.append("fallback_provider_same_as_primary")
            fallback_provider = fallback_raw
            fallback_status = "unsupported_provider"
        elif fallback_raw not in {"gemini", "openrouter", "openai"}:
            warnings.append("unsupported_llm_provider")
            fallback_provider = fallback_raw
            fallback_status = "unsupported_provider"
        else:
            fallback_provider = fallback_raw
            fallback_model, fallback_warnings = _model_for_provider(fallback_provider, environ)
            fallback_api_key = _key_for_provider(fallback_provider, environ)
            fallback_configured, fallback_status, fallback_warnings = _provider_status(fallback_provider, fallback_model, fallback_api_key, fallback_warnings)
            if not fallback_configured:
                warnings.append("fallback_provider_not_configured")

    if not enabled:
        status = "disabled"
        if "llm_disabled" not in warnings:
            warnings.append("llm_disabled")
    return LlmProviderConfig(
        enabled,
        provider,
        model,
        api_key if configured or api_key else None,
        configured,
        warnings,
        status,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        fallback_api_key=fallback_api_key if fallback_configured or fallback_api_key else None,
        fallback_configured=fallback_configured,
        fallback_status=fallback_status,
        fallback_warnings=fallback_warnings,
    )
