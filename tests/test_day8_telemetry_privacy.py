"""Day 8 operational telemetry: consent, strict schema, and failure isolation."""
from __future__ import annotations

import pytest

from services.coworker.day8_telemetry import (
    EventPolicy,
    build_operational_event,
    emit_operational_event,
)


BASE = {
    "workflow": "research",
    "outcome": "completed",
    "provider": "deepseek",
    "model": "deepseek-chat",
    "latency_ms": 2300,
    "error_category": "none",
    "input_tokens": 17,
    "output_tokens": 9,
    "retry_model": 0,
    "retry_tool": 1,
    "retry_dispatch": 0,
    "all_in_cost_microusd": 22,
}


def policy(**overrides):
    values = dict(enabled=True, environment="staging", privacy_scope_approved=True,
                  consent_granted=True, kill_switch=False,
                  approved_provider_models=frozenset({("deepseek", "deepseek-chat")}))
    values.update(overrides)
    return EventPolicy(**values)


def test_allowlist_schema_fixed_event_and_buckets():
    name, props = build_operational_event(BASE, policy())
    assert name == "rukh_agent_run_operational_v1"
    assert props == {
        "event_schema_version": 1, "environment": "staging", "workflow": "research",
        "outcome": "completed", "provider": "deepseek", "model": "deepseek-chat",
        "latency_bucket": "1s_5s", "error_category": "none", "input_tokens": 17,
        "output_tokens": 9, "retry_model": 0, "retry_tool": 1,
        "retry_dispatch": 0, "all_in_cost_microusd": 22,
    }


@pytest.mark.parametrize("secret", [
    "prompt", "document_text", "filename", "owner_id", "account_id", "run_id",
    "source_ids", "email", "recipient", "url", "access_token", "oauth_secret",
    "connector_payload", "raw_exception", "api_key", "extra",
])
def test_unknown_sensitive_fields_are_rejected_not_redacted(secret):
    payload = {**BASE, secret: "SYNTHETIC_PRIVATE_INPUT@example.test"}
    with pytest.raises(ValueError, match="invalid operational event"):
        build_operational_event(payload, policy())
    observed = []
    assert emit_operational_event(payload, policy(), lambda *args: observed.append(args)) is False
    assert observed == []


@pytest.mark.parametrize("field,bad", [
    ("provider", "deepseek\\nAuthorization: fake-token"),
    ("model", "deepseek-chat plus arbitrary user content"),
    ("workflow", "my private document"),
    ("outcome", "some user text"),
    ("error_category", "timeout on secret-key-123"),
    ("input_tokens", "17"), ("input_tokens", True), ("output_tokens", -1),
    ("all_in_cost_microusd", -10), ("latency_ms", float("nan")),
    ("retry_tool", 1.2), ("retry_dispatch", True),
])
def test_invalid_values_cannot_be_emitted(field, bad):
    observed = []
    payload = {**BASE, field: bad}
    assert emit_operational_event(payload, policy(), lambda *args: observed.append(args)) is False
    assert observed == []


@pytest.mark.parametrize("overrides", [
    {}, {"enabled": False}, {"environment": "production"},
    {"environment": "development"}, {"privacy_scope_approved": False},
    {"consent_granted": False}, {"kill_switch": True},
    {"approved_provider_models": frozenset()},
])
def test_no_outbound_without_all_protected_configuration(overrides):
    guard = EventPolicy() if not overrides else policy(**overrides)
    emitted = []
    assert emit_operational_event(BASE, guard, lambda *args: emitted.append(args)) is False
    assert emitted == []


def test_missing_usage_is_unknown_not_zero():
    payload = {**BASE}
    for key in ("input_tokens", "output_tokens", "all_in_cost_microusd", "retry_model", "retry_tool", "retry_dispatch", "latency_ms"):
        payload.pop(key)
    name, properties = build_operational_event(payload, policy())
    assert name == "rukh_agent_run_operational_v1"
    for key in ("input_tokens", "output_tokens", "all_in_cost_microusd", "retry_model", "retry_tool", "retry_dispatch"):
        assert properties[key] is None
    assert properties["latency_bucket"] == "unknown"


def test_invalid_and_failed_sinks_do_not_break_task_execution():
    sink = lambda *_: (_ for _ in ()).throw(RuntimeError("fake secret in sink exception"))
    assert emit_operational_event(BASE, policy(), sink) is False
    assert emit_operational_event(BASE, policy(), None) is False
    received = []
    assert emit_operational_event(BASE, policy(), lambda *args: received.append(args)) is True
    assert len(received) == 1
    assert all("SYNTHETIC_PRIVATE" not in str(part) for part in received[0])
