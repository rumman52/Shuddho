"""Proposed Day 8 private operational telemetry contract (NO network integration).

No SDK, HTTP client, task hook, auto-capture, or environment-variable activation
is installed here. A future, separately approved server-side integration may
inject a sink after verifying project ownership, privacy policy, retention and
consent with the Founder/C. The default-off gate prevents every sink call.
This module does not itself attest the authenticity of an approval receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Mapping

EVENT_NAME = "shuddho_operational_result_v1"
REQUIRED = frozenset({
    "workflow", "outcome", "provider", "model", "latency_bucket",
    "error_category",
})
OPTIONAL_NUMERIC = frozenset({
    "input_tokens", "output_tokens", "retry_model", "retry_tool",
    "retry_dispatch", "all_in_cost_microusd",
})
ENUMS = {
    "workflow": frozenset({"research_brief", "project_report_email", "daily_briefing"}),
    "outcome": frozenset({"completed", "failed", "blocked", "cancelled", "needs_input"}),
    "provider": frozenset({"deepseek"}),
    "latency_bucket": frozenset({"lt_1s", "1s_5s", "5s_30s", "30s_120s", "gte_120s", "unknown"}),
    "error_category": frozenset({
        "none", "timeout", "rate_limited", "provider_unavailable",
        "tool_failed", "validation", "unknown",
    }),
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PROJECT_ID = re.compile(r"^[0-9]{1,20}$")
_MODEL_ID = re.compile(r"^[a-zA-Z0-9._-]{1,80}$")
MAX_METRIC = 2**63 - 1


class TelemetryValidationError(ValueError):
    """A candidate event contains unapproved fields or values."""


@dataclass(frozen=True)
class TelemetryGate:
    enabled: bool = False
    owner_approved: bool = False
    consent_confirmed: bool = False
    kill_switch: bool = True
    environment: str = "development"
    project_id: str | None = None
    approved_project_id: str | None = None
    approval_receipt_sha256: str | None = None
    approved_model: str | None = None

    def ready(self) -> bool:
        """All gates must be explicitly set by an authenticated integration."""
        return (
            self.enabled is True
            and self.owner_approved is True
            and self.consent_confirmed is True
            and self.kill_switch is False
            and self.environment == "staging"
            and isinstance(self.project_id, str)
            and bool(_PROJECT_ID.fullmatch(self.project_id))
            and self.project_id == self.approved_project_id
            and isinstance(self.approval_receipt_sha256, str)
            and bool(_DIGEST.fullmatch(self.approval_receipt_sha256))
            and isinstance(self.approved_model, str)
            and bool(_MODEL_ID.fullmatch(self.approved_model))
        )


def build_properties(source: Mapping[str, object], gate: TelemetryGate) -> dict[str, object]:
    """Reject, never recursively redact, unknown keys and untrusted values.

    Missing measurements remain absent. No prompt, owner/run/document IDs,
    filenames, token strings, URLs, connector payloads or arbitrary errors may
    flow through the allowlist.
    """
    if not isinstance(source, dict) or set(source) - REQUIRED - OPTIONAL_NUMERIC:
        raise TelemetryValidationError("unapproved operational telemetry field")
    if not REQUIRED.issubset(source):
        raise TelemetryValidationError("missing required operational telemetry field")
    for field, allowed in ENUMS.items():
        value = source[field]
        if type(value) is not str or value not in allowed:
            raise TelemetryValidationError("invalid operational telemetry enum")
    if type(source["model"]) is not str or source["model"] != gate.approved_model:
        raise TelemetryValidationError("model does not match approved identity")
    for key in OPTIONAL_NUMERIC & source.keys():
        value = source[key]
        if type(value) is not int or not 0 <= value <= MAX_METRIC:
            raise TelemetryValidationError("invalid operational telemetry measurement")
    return {
        "event_schema_version": 1,
        "environment": "staging",
        **{key: source[key] for key in sorted(REQUIRED)},
        **{key: source[key] for key in sorted(OPTIONAL_NUMERIC & source.keys())},
    }


def emit_operational_event(
    gate: TelemetryGate,
    source: Mapping[str, object],
    sink: Callable[[str, dict[str, object]], object],
) -> bool:
    """Never let telemetry errors affect work; never send when unapproved.

    The caller must independently authenticate the privacy approval and
    destination. This function has no built-in PostHog or other outbound path.
    """
    if not isinstance(gate, TelemetryGate) or not gate.ready():
        return False
    try:
        properties = build_properties(source, gate)
        sink(EVENT_NAME, properties)
    except Exception:
        # No arbitrary exception, source payload or credentials are logged.
        return False
    return True
