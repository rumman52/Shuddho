"""Privacy-first Day 8 *candidate* operational event contract.

No SDK, network client, scheduler or global sink is registered here. The only
possible delivery is an explicitly injected callable, after every gate passes.
Owner/Founder approval of the actual project, retention, egress and consent
remains an external operational prerequisite; setting these synthetic gates
in tests does not constitute that approval.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

EVENT_NAME = "rukh_agent_run_operational_v1"
WORKFLOWS = frozenset({"research", "report_email", "daily_briefing", "general_agent"})
OUTCOMES = frozenset({"completed", "failed", "needs_input", "blocked", "cancelled", "unknown"})
ERROR_CATEGORIES = frozenset({
    "none", "provider_unavailable", "provider_rate_limited", "provider_timeout",
    "tool_timeout", "authorization", "validation", "cancelled", "unknown",
})
REQUIRED_FIELDS = frozenset({"workflow", "outcome", "provider", "model", "error_category"})
OPTIONAL_FIELDS = frozenset({
    "latency_ms", "input_tokens", "output_tokens", "retry_model", "retry_tool",
    "retry_dispatch", "all_in_cost_microusd",
})


@dataclass(frozen=True, slots=True)
class EventPolicy:
    """Default-deny switches; never infer approval from observed event hosts."""

    enabled: bool = False
    environment: str = "development"
    privacy_scope_approved: bool = False
    consent_granted: bool = False
    kill_switch: bool = True
    approved_provider_models: frozenset[tuple[str, str]] = field(default_factory=frozenset)

    def permits(self) -> bool:
        return (
            self.enabled is True and self.privacy_scope_approved is True
            and self.consent_granted is True and self.kill_switch is False
            and self.environment == "staging" and bool(self.approved_provider_models)
        )


def _invalid() -> ValueError:
    # Never interpolate a raw property name/value in logs or raised errors.
    return ValueError("invalid operational event")


def _nullable_count(raw: Mapping[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _invalid()
    return value


def _latency_bucket(raw: Mapping[str, Any]) -> str:
    value = _nullable_count(raw, "latency_ms")
    if value is None:
        return "unknown"
    if value < 1000:
        return "lt_1s"
    if value < 5000:
        return "1s_5s"
    if value < 30000:
        return "5s_30s"
    if value < 120000:
        return "30s_120s"
    return "gte_120s"


def build_operational_event(
    raw: Mapping[str, Any], policy: EventPolicy,
) -> tuple[str, dict[str, str | int | None]]:
    """Construct, rather than recursively scrub, an exact fixed-key event.

    An arbitrary exception, account ID, source pin, prompt or connector record
    never becomes an event field. Unknown numeric usage remains null, not zero.
    """
    if not isinstance(policy, EventPolicy) or not policy.permits():
        raise _invalid()
    if not isinstance(raw, Mapping) or set(raw) - (REQUIRED_FIELDS | OPTIONAL_FIELDS):
        raise _invalid()
    if not REQUIRED_FIELDS.issubset(raw):
        raise _invalid()
    if (type(raw["workflow"]) is not str or raw["workflow"] not in WORKFLOWS
        or type(raw["outcome"]) is not str or raw["outcome"] not in OUTCOMES
        or type(raw["error_category"]) is not str or raw["error_category"] not in ERROR_CATEGORIES):
        raise _invalid()
    provider, model = raw["provider"], raw["model"]
    if (type(provider) is not str or type(model) is not str
        or (provider, model) not in policy.approved_provider_models):
        raise _invalid()
    properties: dict[str, str | int | None] = {
        "event_schema_version": 1,
        "environment": policy.environment,
        "workflow": raw["workflow"],
        "outcome": raw["outcome"],
        "provider": provider,
        "model": model,
        "latency_bucket": _latency_bucket(raw),
        "error_category": raw["error_category"],
    }
    for key in ("input_tokens", "output_tokens", "retry_model", "retry_tool",
                "retry_dispatch", "all_in_cost_microusd"):
        properties[key] = _nullable_count(raw, key)
    return EVENT_NAME, properties


def emit_operational_event(
    raw: Mapping[str, Any],
    policy: EventPolicy,
    sink: Callable[[str, dict[str, str | int | None]], object] | None,
) -> bool:
    """Nonblocking, fail-closed opt-in delivery. Never log raw payloads."""
    if sink is None:
        return False
    try:
        event_name, properties = build_operational_event(raw, policy)
        sink(event_name, properties)
    except Exception:  # noqa: BLE001 - external diagnostics must never affect the task
        return False
    return True
