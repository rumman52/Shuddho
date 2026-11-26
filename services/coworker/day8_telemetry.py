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
import inspect
import re

EVENT_NAME = "rukh_agent_run_operational_v1"
# These validation checks are not a signature verifier or proof of human approval.
_PROJECT_ID = re.compile(r"[0-9]{1,20}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_METRIC_MAX = 2**63 - 1
# Cloud-only until a separately reviewed self-hosted/proxy egress contract exists.
# Keep private API hosts separate from public event-ingestion endpoints.
_POSTHOG_CLOUD_HOSTS = {
    "us": ("us.i.posthog.com", "us.posthog.com"),
    "eu": ("eu.i.posthog.com", "eu.posthog.com"),
}
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
    # Set only by the reviewed server-side integration after verifying the
    # dated Founder/C decision and actual destination configuration. A test
    # fixture containing this shape is NOT an owner approval.
    project_id: str | None = None
    approved_project_id: str | None = None
    destination_region: str | None = None
    approved_region: str | None = None
    destination_retention_days: int | None = None
    approved_retention_days: int | None = None
    privacy_approval_sha256: str | None = None
    # Two independently supplied pieces of configuration: actual intended
    # cloud hosts and the hosts in the dated Founder/C authorization. A
    # metadata match does not authenticate an injected sink or its network
    # routing; that requires separate adapter/egress verification.
    destination_ingestion_host: str | None = None
    approved_ingestion_host: str | None = None
    destination_api_host: str | None = None
    approved_api_host: str | None = None

    def permits(self) -> bool:
        # Type annotations and a frozen dataclass do not validate runtime
        # values or freeze a mutable allowlist supplied by a caller. Reject
        # non-primitive approval metadata before invoking any equality checks.
        if not all(type(value) is str for value in (
            self.environment, self.project_id, self.approved_project_id,
            self.destination_region, self.approved_region,
            self.privacy_approval_sha256, self.destination_ingestion_host,
            self.approved_ingestion_host, self.destination_api_host,
            self.approved_api_host,
        )):
            return False
        if type(self.approved_provider_models) is not frozenset or not all(
            type(pair) is tuple and len(pair) == 2
            and all(type(value) is str for value in pair)
            for pair in self.approved_provider_models
        ):
            return False
        cloud_hosts = _POSTHOG_CLOUD_HOSTS.get(self.destination_region)
        return (
            self.enabled is True and self.privacy_scope_approved is True
            and self.consent_granted is True and self.kill_switch is False
            and self.environment == "staging" and bool(self.approved_provider_models)
            and _PROJECT_ID.fullmatch(self.project_id) is not None
            and self.project_id == self.approved_project_id
            and self.destination_region in ("us", "eu")
            and self.destination_region == self.approved_region
            and cloud_hosts is not None
            and self.destination_ingestion_host == cloud_hosts[0]
            and self.approved_ingestion_host == cloud_hosts[0]
            and self.destination_api_host == cloud_hosts[1]
            and self.approved_api_host == cloud_hosts[1]
            and type(self.destination_retention_days) is int
            and 1 <= self.destination_retention_days <= 3650
            and type(self.approved_retention_days) is int
            and self.destination_retention_days == self.approved_retention_days
            and _SHA256.fullmatch(self.privacy_approval_sha256) is not None
        )


def _invalid() -> ValueError:
    # Never interpolate a raw property name/value in logs or raised errors.
    return ValueError("invalid operational event")


def _nullable_count(raw: Mapping[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= _METRIC_MAX:
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
    if type(policy) is not EventPolicy or not policy.permits():
        raise _invalid()
    if not isinstance(raw, Mapping):
        raise _invalid()
    # Validate and construct from the same private snapshot, never reread a
    # caller-controlled mapping after its values passed the allowlist checks.
    try:
        raw = dict(raw)
    except Exception:
        raise _invalid() from None
    if any(type(key) is not str for key in raw) or set(raw) - (REQUIRED_FIELDS | OPTIONAL_FIELDS):
        raise _invalid()
    if not REQUIRED_FIELDS.issubset(raw):
        raise _invalid()
    if (type(raw["workflow"]) is not str or raw["workflow"] not in WORKFLOWS
        or type(raw["outcome"]) is not str or raw["outcome"] not in OUTCOMES
        or type(raw["error_category"]) is not str or raw["error_category"] not in ERROR_CATEGORIES):
        raise _invalid()
    provider, model = raw["provider"], raw["model"]
    if (type(provider) is not str or type(model) is not str
        or re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", provider) is None
        or re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", model) is None
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
    """Fail-closed synchronous handoff, never proof of remote delivery.

    Approval and transport confirmation remain external operator gates. A
    false sink acknowledgement or unawaited async result cannot qualify an
    operational receipt; never log raw payloads or sink exceptions.
    """
    try:
        if sink is None:
            return False
        event_name, properties = build_operational_event(raw, policy)
        if inspect.iscoroutinefunction(sink):
            return False
        acknowledgement = sink(event_name, properties)
        if inspect.isawaitable(acknowledgement):
            # An async callable wrapped by a sync function must not be
            # treated as a completed send. Close bare coroutines to avoid
            # leaked/unawaited coroutine warnings; do not run an event loop.
            if inspect.iscoroutine(acknowledgement):
                acknowledgement.close()
            return False
        if acknowledgement is False:
            return False
    except Exception:  # noqa: BLE001 - external diagnostics must never affect the task
        return False
    return True
