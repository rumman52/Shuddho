from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Protocol

LLM_STATUSES = {
    "disabled", "skipped", "missing_key", "unsupported_provider", "attempted",
    "completed", "completed_empty", "completed_rejected", "timeout", "invalid_json",
    "invalid_schema", "provider_error", "auth_or_forbidden", "credits_or_payment_required",
    "model_not_found", "content_filter", "network_error", "rate_limited", "failed",
    "circuit_open", "dependency_missing", "truncated",
}
DEFAULT_GEMMA_MODEL = "gemma-4-26b-a4b-it"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"

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
    error_code: str | None = None
    retry_after_seconds: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    def model_dump(self) -> dict[str, Any]:
        return self.__dict__.copy()

@dataclass(frozen=True)
class LlmProviderConfig:
    enabled: bool
    provider: str
    model: str
    api_key: str | None = field(repr=False)
    configured: bool
    warnings: list[str] = field(default_factory=list)
    status: str = "completed"
    # Retained as empty diagnostics fields to preserve the health response contract.
    fallback_provider: str | None = None
    fallback_model: str = ""
    fallback_api_key: str | None = field(default=None, repr=False)
    fallback_configured: bool = False
    fallback_status: str = "disabled"
    fallback_warnings: list[str] = field(default_factory=list)

class LlmReviewProvider(Protocol):
    def review(self, text: str, local_suggestions: list[dict[str, Any]], candidates: list[dict[str, Any]], request_id: str, timeout_seconds: float) -> LlmProviderResult: ...


@dataclass(frozen=True)
class LlmResponseMode:
    requested: str
    effective: str
    warnings: tuple[str, ...] = ()


def resolve_llm_response_mode(config: LlmProviderConfig, env: dict[str, str] | None = None) -> LlmResponseMode:
    if config.provider == "gemma":
        from services.api.shuddho_api.gemma_response_mode import resolve_gemma_response_mode
        mode = resolve_gemma_response_mode(env if env is not None else os.environ)
        return LlmResponseMode(mode.requested, mode.effective, mode.warnings)
    if config.provider == "deepseek":
        return LlmResponseMode("json_object", "json_object")
    return LlmResponseMode("none", "none")

def _truthy(value: str | None) -> bool | None:
    if value is None or value.strip() == "" or value.strip().lower() == "auto": return None
    return value.strip().lower() in {"1", "true", "yes", "on"}

def resolve_llm_config(env: dict[str, str] | None = None) -> LlmProviderConfig:
    environ = env if env is not None else os.environ
    provider = (environ.get("SHUDDHO_LLM_PROVIDER") or "deepseek").strip().lower()
    enabled_flag = _truthy(environ.get("SHUDDHO_ENABLE_LLM"))
    if provider in {"disabled", "none", "off"}:
        return LlmProviderConfig(False, "disabled", "", None, False, ["llm_disabled"], "disabled")
    if provider not in {"gemma", "deepseek"}:
        return LlmProviderConfig(False, provider, "", None, False, ["unsupported_llm_provider"], "unsupported_provider")
    if provider == "deepseek":
        model = (environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
        key = (environ.get("DEEPSEEK_API_KEY") or "").strip() or None
        missing_warning = "deepseek_api_key_missing"
        model_prefix = "deepseek-"
    else:
        model = (environ.get("GEMMA_MODEL") or DEFAULT_GEMMA_MODEL).strip()
        key = (environ.get("GOOGLE_API_KEY") or "").strip() or None
        missing_warning = "google_api_key_missing"
        model_prefix = "gemma-"
    if not model.lower().startswith(model_prefix):
        return LlmProviderConfig(False, provider, model, None, False, [f"unsupported_model_{provider}_only"], "unsupported_provider")
    warnings = [] if key else [missing_warning]
    configured = bool(key)
    status = "completed" if configured else "missing_key"
    enabled = bool(key) if enabled_flag is None else enabled_flag
    if not enabled:
        status = "disabled"
        warnings.append("llm_disabled")
    return LlmProviderConfig(enabled, provider, model, key, configured, warnings, status)
