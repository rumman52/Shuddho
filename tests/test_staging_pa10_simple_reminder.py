from __future__ import annotations

import pytest

from scripts import staging_pa10_simple_reminder as probe


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_SIMPLE_REMINDER", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    with pytest.raises(probe.ReminderProbeFailure, match="ALLOW_SIMPLE_REMINDER"):
        probe.require_guard()


def test_clean_origin_rejects_non_https_and_paths():
    assert probe.clean_origin("https://stage.example.test") == "https://stage.example.test"
    for value in (
        "http://stage.example.test",
        "https://stage.example.test/api",
        "https://user:pass@stage.example.test",
        "https://stage.example.test?x=1",
    ):
        with pytest.raises(probe.ReminderProbeFailure):
            probe.clean_origin(value)
