from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts import staging_pa10_managed_recovery as probe


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_MANAGED_RECOVERY", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    with pytest.raises(probe.ManagedRecoveryProbeFailure, match="ALLOW_MANAGED_RECOVERY"):
        probe.require_guard()


def test_restart_must_be_inside_prepared_exercise_window():
    prepared = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(probe.ManagedRecoveryProbeFailure, match="before"):
        probe.require_restart(
            name="api",
            at_value="2026-10-01T11:59:00+00:00",
            reference="deploy-1",
            prepared_at=prepared,
        )
    value = probe.require_restart(
        name="coworker-worker",
        at_value="2026-10-01T12:01:00+00:00",
        reference="worker-replace-1",
        prepared_at=prepared,
    )
    assert value["component"] == "coworker-worker"
    assert value["reference"] == "worker-replace-1"


def test_clean_https_origin_rejects_non_origin_values():
    assert probe.clean_https_origin("https://staging.example.test") == "https://staging.example.test"
    for value in (
        "http://staging.example.test",
        "https://staging.example.test/api",
        "https://user:pass@staging.example.test",
        "https://staging.example.test?secret=x",
    ):
        with pytest.raises(probe.ManagedRecoveryProbeFailure):
            probe.clean_https_origin(value)


def test_parse_time_requires_timezone():
    with pytest.raises(probe.ManagedRecoveryProbeFailure, match="timezone"):
        probe.parse_time("2026-10-01T12:00:00", "value")
    assert probe.parse_time(
        "2026-10-01T12:00:00+00:00", "value"
    ) == datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
