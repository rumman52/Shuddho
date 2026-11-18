"""Synthetic contract tests: NO PostHog event or external request is sent."""
from __future__ import annotations

from dataclasses import replace

import pytest

from services.coworker.operational_telemetry import (
    EVENT_NAME, TelemetryGate, TelemetryValidationError,
    build_properties, emit_operational_event,
)


def approved_test_gate():
    # A synthetic approval proves only code behavior, not real owner consent.
    return TelemetryGate(
        enabled=True, owner_approved=True, consent_confirmed=True,
        kill_switch=False, environment="staging", project_id="999999",
        approved_project_id="999999", approval_receipt_sha256="a" * 64,
        approved_model="deepseek-chat",
    )


def minimal_event():
    return {
        "workflow": "research_brief", "outcome": "completed",
        "provider": "deepseek", "model": "deepseek-chat",
        "latency_bucket": "5s_30s", "error_category": "none",
        "input_tokens": 93, "output_tokens": 14,
        "retry_model": 0, "retry_tool": 0, "retry_dispatch": 0,
        "all_in_cost_microusd": 42,
    }


def test_default_gate_never_invokes_sink_even_with_private_source():
    seen = []
    private = {**minimal_event(), "prompt": "PRIVATE prompt", "token": "sk-fake"}
    assert not emit_operational_event(TelemetryGate(), private, lambda *a: seen.append(a))
    assert seen == []


@pytest.mark.parametrize("changes", [
    {"enabled": False}, {"owner_approved": False},
    {"consent_confirmed": False}, {"kill_switch": True},
    {"environment": "production"}, {"environment": "development"},
    {"project_id": "999998"}, {"approval_receipt_sha256": None},
    {"approval_receipt_sha256": "unapproved"}, {"approved_model": None},
    {"approved_model": "https://secret.invalid"},
])
def test_gate_missing_any_independent_requirement_is_silent(changes):
    gate = replace(approved_test_gate(), **changes)
    called = []
    assert not emit_operational_event(gate, minimal_event(), lambda *a: called.append(a))
    assert not called


def test_approved_synthetic_staging_sends_only_allowlisted_properties():
    seen = []
    assert emit_operational_event(
        approved_test_gate(), minimal_event(), lambda name, fields: seen.append((name, fields)),
    )
    assert len(seen) == 1
    name, fields = seen[0]
    assert name == EVENT_NAME
    assert fields == {"event_schema_version": 1, "environment": "staging", **minimal_event()}
    assert "run_id" not in fields and "prompt" not in fields


@pytest.mark.parametrize("private_field", [
    "prompt", "document_text", "email", "account_id", "run_id", "source_pin",
    "filename", "url", "oauth_token", "connector_payload", "review_receipt",
    "exception", "recipient",
])
def test_redaction_is_fail_closed_for_sensitive_fields(private_field):
    secret = "SYNTHETIC-SECRET-DO-NOT-EMIT@example.invalid"
    row = {**minimal_event(), private_field: secret}
    seen = []
    assert not emit_operational_event(approved_test_gate(), row, lambda *a: seen.append(a))
    assert seen == []
    with pytest.raises(TelemetryValidationError) as err:
        build_properties(row, approved_test_gate())
    assert secret not in str(err.value)


@pytest.mark.parametrize("field,bad", [
    ("workflow", "PRIVATE DOCUMENT"),
    ("outcome", "someone@example.invalid"),
    ("provider", "https://api.example.invalid"),
    ("error_category", "Bearer fake-token"),
    ("latency_bucket", "200ms: /private/file"),
    ("model", "deepseek-other"),
    ("input_tokens", True),
    ("input_tokens", -1),
    ("output_tokens", "14"),
    ("retry_dispatch", None),
    ("all_in_cost_microusd", 2**63),
])
def test_invalid_values_do_not_egress(field, bad):
    row = {**minimal_event(), field: bad}
    out = []
    assert not emit_operational_event(approved_test_gate(), row, lambda *x: out.append(x))
    assert out == []


def test_missing_usage_remains_absent_not_zero():
    event = minimal_event()
    del event["input_tokens"]
    del event["output_tokens"]
    result = build_properties(event, approved_test_gate())
    assert "input_tokens" not in result
    assert "output_tokens" not in result


def test_telemetry_transport_failure_cannot_break_run():
    def failed_sink(*_args):
        raise RuntimeError("token=synthetic-secret")
    assert not emit_operational_event(approved_test_gate(), minimal_event(), failed_sink)


def test_invalid_gate_types_never_enable_transport():
    for gate in (None, {"enabled": True}, replace(approved_test_gate(), enabled=1)):
        seen = []
        assert not emit_operational_event(gate, minimal_event(), lambda *a: seen.append(a))
        assert not seen
