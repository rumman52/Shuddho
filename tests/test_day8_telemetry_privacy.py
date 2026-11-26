"""Day 8 operational telemetry: consent, strict schema, and failure isolation."""
from __future__ import annotations

from collections.abc import Mapping

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
                  approved_provider_models=frozenset({("deepseek", "deepseek-chat")}),
                  project_id="999999", approved_project_id="999999",
                  destination_region="us", approved_region="us",
                  destination_retention_days=30, approved_retention_days=30,
                  privacy_approval_sha256="a" * 64,
                  destination_ingestion_host="us.i.posthog.com",
                  approved_ingestion_host="us.i.posthog.com",
                  destination_api_host="us.posthog.com",
                  approved_api_host="us.posthog.com")
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
    ("retry_model", 2**63), ("latency_ms", 2**63),
    ("provider", "deepseek\nPRIVATE"), ("model", "model?SECRET"),
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
    {"project_id": None}, {"project_id": "abcd"},
    {"project_id": "999998"}, {"approved_project_id": "999998"},
    {"destination_region": None}, {"destination_region": "apac"},
    {"approved_region": "eu"},
    {"destination_retention_days": None},
    {"destination_retention_days": 31},
    {"approved_retention_days": None},
    {"destination_retention_days": True},
    {"privacy_approval_sha256": None},
    {"privacy_approval_sha256": "missing"},
    {"destination_ingestion_host": None},
    {"approved_ingestion_host": None},
    {"destination_api_host": None},
    {"approved_api_host": None},
    {"destination_ingestion_host": "eu.i.posthog.com"},
    {"approved_ingestion_host": "eu.i.posthog.com"},
    {"destination_api_host": "eu.posthog.com"},
    {"approved_api_host": "eu.posthog.com"},
    {"destination_ingestion_host": "https://us.i.posthog.com"},
    {"destination_ingestion_host": "us.i.posthog.com:443"},
    {"destination_api_host": "us.posthog.com.evil.test"},
    {"destination_api_host": "us.posthog.com/path"},
    {"destination_ingestion_host": "us.i.posthog.com.evil.test"},
])
def test_no_outbound_without_all_protected_configuration(overrides):
    guard = EventPolicy() if not overrides else policy(**overrides)
    emitted = []
    assert emit_operational_event(BASE, guard, lambda *args: emitted.append(args)) is False
    assert emitted == []


def test_invalid_approval_metadata_is_never_echoed_to_sink_or_errors():
    secret = "SYNTHETIC PRIVATE REVIEW NOTE"
    received = []
    invalid = policy(privacy_approval_sha256=secret)
    assert emit_operational_event(BASE, invalid, lambda *args: received.append(args)) is False
    assert received == []
    with pytest.raises(ValueError) as error:
        build_operational_event(BASE, invalid)
    assert secret not in str(error.value)


def test_approved_event_preserves_exact_canonical_name_only():
    sent = []
    assert emit_operational_event(BASE, policy(), lambda *args: sent.append(args))
    assert [entry[0] for entry in sent] == ["rukh_agent_run_operational_v1"]
    assert not any("project_id" in item or "approval" in item
                   for item in sent[0][1])


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


def test_legacy_privacy_approval_cannot_emit_without_bound_posthog_hosts():
    """A project/region/retention match alone does not select an egress host."""
    legacy = EventPolicy(
        enabled=True, environment="staging", privacy_scope_approved=True,
        consent_granted=True, kill_switch=False,
        approved_provider_models=frozenset({("deepseek", "deepseek-chat")}),
        project_id="999999", approved_project_id="999999",
        destination_region="us", approved_region="us",
        destination_retention_days=30, approved_retention_days=30,
        privacy_approval_sha256="a" * 64,
    )
    outbound = []
    assert emit_operational_event(BASE, legacy, lambda *args: outbound.append(args)) is False
    assert outbound == []


@pytest.mark.parametrize("region,ingestion,api", [
    ("us", "us.i.posthog.com", "us.posthog.com"),
    ("eu", "eu.i.posthog.com", "eu.posthog.com"),
])
def test_approved_cloud_region_requires_exact_ingestion_and_api_hosts(region, ingestion, api):
    guard = policy(
        destination_region=region, approved_region=region,
        destination_ingestion_host=ingestion, approved_ingestion_host=ingestion,
        destination_api_host=api, approved_api_host=api,
    )
    observed = []
    assert emit_operational_event(BASE, guard, lambda *args: observed.append(args)) is True
    assert len(observed) == 1
    assert observed[0][0] == "rukh_agent_run_operational_v1"
    # Destination identity is server-side policy, never an event property.
    assert not any("host" in field or "project_id" in field
                   for field in observed[0][1])


def test_host_configuration_never_appears_in_validation_errors_or_events():
    sensitive_host = "https://synthetic-secret.example.test/user:password"
    guard = policy(destination_ingestion_host=sensitive_host)
    observed = []
    assert emit_operational_event(BASE, guard, lambda *args: observed.append(args)) is False
    assert observed == []
    with pytest.raises(ValueError) as error:
        build_operational_event(BASE, guard)
    assert sensitive_host not in str(error.value)


def test_explicit_sink_rejection_is_not_reported_as_success():
    """A sink that returns False did not accept the event for delivery."""
    handoffs = []

    def rejecting_sink(name, properties):
        handoffs.append((name, properties))
        return False

    assert emit_operational_event(BASE, policy(), rejecting_sink) is False
    assert len(handoffs) == 1
    assert handoffs[0][0] == "rukh_agent_run_operational_v1"


def test_async_sink_is_not_silently_reported_as_delivered():
    """An unawaited coroutine is not proof of accepted transport delivery."""
    executed = []

    async def async_sink(name, properties):
        executed.append((name, properties))

    assert emit_operational_event(BASE, policy(), async_sink) is False
    assert executed == []


def test_sync_sink_returning_awaitable_is_not_counted_as_delivery():
    """Close a returned coroutine rather than leak it or claim success."""
    executed = []

    async def deferred_send():
        executed.append("executed")

    assert emit_operational_event(
        BASE, policy(), lambda *_: deferred_send(),
    ) is False
    assert executed == []


def test_positive_explicit_sink_acknowledgement_remains_supported():
    assert emit_operational_event(BASE, policy(), lambda *_: True) is True


class _ChangingOperationalMapping(Mapping):
    """Return a valid value during validation, then change the source."""

    def __init__(self, key):
        self.key = key
        self.reads = 0

    def __iter__(self):
        return iter(BASE)

    def __len__(self):
        return len(BASE)

    def __getitem__(self, key):
        value = BASE[key]
        if key == self.key:
            self.reads += 1
            if self.reads > 2:
                return "SYNTHETIC_PRIVATE_INPUT@example.test"
        return value


@pytest.mark.parametrize("key", ["workflow", "outcome", "error_category"])
def test_emitted_enums_are_the_same_values_validated_from_one_snapshot(key):
    raw = _ChangingOperationalMapping(key)
    received = []
    assert emit_operational_event(raw, policy(), lambda *args: received.append(args))
    assert received[0][1][key] == BASE[key]
    assert raw.reads == 1


class _SpoofedPolicyString(str):
    def __eq__(self, _other):
        return True

    __hash__ = str.__hash__


@pytest.mark.parametrize("overrides", [
    {"environment": _SpoofedPolicyString("SYNTHETIC_PRIVATE_INPUT@example.test")},
    {"approved_retention_days": True, "destination_retention_days": 1},
    {"approved_provider_models": {("deepseek", "deepseek-chat")}},
    {"approved_provider_models": frozenset({(_SpoofedPolicyString("deepseek"), "deepseek-chat")})},
    {"approved_ingestion_host": _SpoofedPolicyString("wrong.example.test")},
    {"approved_project_id": _SpoofedPolicyString("wrong")},
    {"approved_region": _SpoofedPolicyString("wrong")},
])
def test_policy_requires_exact_immutable_authorization_types(overrides):
    observed = []
    assert emit_operational_event(BASE, policy(**overrides), lambda *args: observed.append(args)) is False
    assert observed == []


def test_policy_subclass_cannot_override_default_deny():
    class AlwaysPermit(EventPolicy):
        def permits(self):
            return True

    guard = AlwaysPermit(approved_provider_models=frozenset({("deepseek", "deepseek-chat")}))
    observed = []
    assert emit_operational_event(BASE, guard, lambda *args: observed.append(args)) is False
    assert observed == []


def test_failed_mapping_snapshot_does_not_echo_private_exception():
    class BrokenMapping(_ChangingOperationalMapping):
        def __getitem__(self, _key):
            raise RuntimeError("SYNTHETIC_PRIVATE_INPUT@example.test")

    with pytest.raises(ValueError, match="^invalid operational event$"):
        build_operational_event(BrokenMapping("workflow"), policy())
    received = []
    assert emit_operational_event(BrokenMapping("workflow"), policy(),
                                  lambda *args: received.append(args)) is False
    assert received == []


def test_snapshot_rejects_non_plain_string_keys():
    class NonPlainKey(str):
        pass

    raw = dict(BASE)
    del raw["workflow"]
    raw[NonPlainKey("workflow")] = "research"
    with pytest.raises(ValueError, match="^invalid operational event$"):
        build_operational_event(raw, policy())


def test_snapshot_preserves_read_only_mapping_support():
    from types import MappingProxyType

    assert build_operational_event(MappingProxyType(BASE), policy()) == build_operational_event(BASE, policy())


def test_sink_introspection_failure_is_isolated_before_any_send(monkeypatch):
    from services.coworker import day8_telemetry as telemetry

    def broken_inspection(_sink):
        raise RuntimeError("SYNTHETIC_PRIVATE_INPUT@example.test")

    monkeypatch.setattr(telemetry.inspect, "iscoroutinefunction", broken_inspection)
    received = []
    assert emit_operational_event(BASE, policy(), lambda *args: received.append(args)) is False
    assert received == []


def test_denied_policy_never_touches_the_sink(monkeypatch):
    from services.coworker import day8_telemetry as telemetry

    inspected = []
    received = []
    monkeypatch.setattr(telemetry.inspect, "iscoroutinefunction",
                        lambda sink: inspected.append(sink))
    assert emit_operational_event(BASE, EventPolicy(), lambda *args: received.append(args)) is False
    assert inspected == received == []


@pytest.mark.parametrize("field", ["workflow", "model", "error_category", "input_tokens", "latency_ms"])
def test_nested_payload_does_not_reach_sink(field):
    raw = {**BASE, field: {"secret": ["SYNTHETIC_PRIVATE_INPUT@example.test"]}}
    received = []
    assert emit_operational_event(raw, policy(), lambda *args: received.append(args)) is False
    assert received == []
