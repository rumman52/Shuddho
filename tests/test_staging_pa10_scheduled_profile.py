from __future__ import annotations

import pytest

from scripts import staging_pa10_scheduled_profile as probe


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="ALLOW_SCHEDULED_PROFILES"):
        probe.require_guard()


def test_scenario_contracts_are_explicit_and_bounded():
    assert probe.SCENARIOS["daily_coworker"] == {
        "profile": "briefing",
        "schedule": {"daily"},
    }
    assert probe.SCENARIOS["weekly_coworker"] == {
        "profile": "briefing",
        "schedule": {"weekly"},
    }
    assert probe.SCENARIOS["deadline_coworker"]["profile"] == "deadline"
    assert probe.SCENARIOS["goal_driven_proactivity"]["profile"] == "proactive"
    assert probe.SCENARIOS["scheduled_reminder"]["profile"] == "goal"


def test_clean_origin_rejects_non_https_or_path():
    assert probe.clean_origin("https://stage.example.test") == "https://stage.example.test"
    for value in (
        "http://stage.example.test",
        "https://stage.example.test/api",
        "https://user:pass@stage.example.test",
    ):
        with pytest.raises(probe.ScheduledProfileProbeFailure):
            probe.clean_origin(value)
