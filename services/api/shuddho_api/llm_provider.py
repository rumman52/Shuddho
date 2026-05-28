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
    "timeout",
    "invalid_json",
    "invalid_schema",
    "provider_error",
    "network_error",
    "rate_limited",
    "failed",
}

ProviderName = Literal["openrouter", "openai", "disabled"]
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
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


def resolve_llm_config(env: dict[str, str] | None = None) -> LlmProviderConfig:
    environ = env if env is not None else os.environ
    provider = (environ.get("SHUDDHO_LLM_PROVIDER") or "openai").strip().lower() or "openai"
    enabled_flag = _truthy(environ.get("SHUDDHO_ENABLE_LLM"))
    warnings: list[str] = []

    if provider in {"disabled", "none", "off"}:
        return LlmProviderConfig(False, "disabled", "", None, False, [], "disabled")
    if provider not in {"openrouter", "openai"}:
        return LlmProviderConfig(False, provider, "", None, False, ["unsupported_llm_provider"], "unsupported_provider")

    if provider == "openrouter":
        model = (environ.get("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
        api_key = (environ.get("OPENROUTER_API_KEY") or "").strip() or None
        missing_warning = "openrouter_api_key_missing"
    else:
        model = (environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
        api_key = (environ.get("OPENAI_API_KEY") or "").strip() or None
        missing_warning = "openai_api_key_missing"
        if "/" in model or ":free" in model:
            warnings.append("openai_model_id_suspicious_use_openrouter_provider")

    configured = bool(api_key) and not (provider == "openai" and ("/" in model or ":free" in model))
    enabled = configured if enabled_flag is None else enabled_flag
    if not enabled:
        return LlmProviderConfig(False, provider, model, api_key, configured, warnings, "disabled")
    if not api_key:
        return LlmProviderConfig(True, provider, model, None, False, [*warnings, missing_warning], "missing_key")
    if provider == "openai" and ("/" in model or ":free" in model):
        return LlmProviderConfig(True, provider, model, api_key, False, warnings, "unsupported_provider")
    return LlmProviderConfig(True, provider, model, api_key, True, warnings, "completed")
