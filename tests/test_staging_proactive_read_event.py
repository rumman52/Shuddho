from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import staging_proactive_read_event as probe


def test_guard_requires_explicit_staging_and_synthetic_account(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_PROACTIVE_READ_EVENTS", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    with pytest.raises(probe.ProactiveReadProbeFailure, match="ALLOW_PROACTIVE_READ_EVENTS"):
        probe.require_guard()

    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_PROACTIVE_READ_EVENTS", "true")
    with pytest.raises(probe.ProactiveReadProbeFailure, match="SYNTHETIC_ACCOUNT"):
        probe.require_guard()

    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    probe.require_guard()


def test_require_https_base_rejects_non_https_and_credentials():
    assert probe.require_https_base("https://staging.example.test/") == "https://staging.example.test"
    with pytest.raises(probe.ProactiveReadProbeFailure, match="clean HTTPS"):
        probe.require_https_base("http://staging.example.test")
    with pytest.raises(probe.ProactiveReadProbeFailure, match="clean HTTPS"):
        probe.require_https_base("https://user:pass@staging.example.test")


def test_rollout_identity_hashes_exact_file(tmp_path: Path):
    rollout = tmp_path / "rollout.json"
    rollout.write_text(json.dumps({"release_id": "staging-20261001"}) + "\n", encoding="utf-8")
    value = probe.rollout_identity(rollout)
    assert value["release_id"] == "staging-20261001"
    assert len(value["rollout_manifest_sha256"]) == 64


def test_select_grant_requires_exact_active_provider_capability():
    grants = [
        {
            "id": "grant-google-email",
            "provider": "google",
            "capability": "email_read",
            "state": "active",
        },
        {
            "id": "grant-google-calendar",
            "provider": "google",
            "capability": "calendar_read",
            "state": "active",
        },
    ]
    assert probe.select_grant(grants, "google", "email_read", None)["id"] == "grant-google-email"
    with pytest.raises(probe.ProactiveReadProbeFailure, match="exactly one"):
        probe.select_grant(grants + [grants[0] | {"id": "duplicate"}], "google", "email_read", None)


def test_select_automation_requires_exact_trigger_grant():
    automations = [
        {
            "id": "automation-1",
            "state": "active",
            "run_profile": "email",
            "schedule": {"kind": "event", "grant_id": "grant-1"},
            "connector_read_grant_ids": ["grant-1"],
        },
        {
            "id": "automation-2",
            "state": "active",
            "run_profile": "email",
            "schedule": {"kind": "event", "grant_id": "grant-2"},
            "connector_read_grant_ids": ["grant-1", "grant-2"],
        },
    ]
    assert probe.select_automation(automations, "grant-1", "email_read", None)["id"] == "automation-1"


def test_transition_evidence_requires_one_completed_occurrence_and_completion_notice():
    state = {
        "capability": "email_read",
        "automation_id": "automation-1",
        "baseline": {
            "snapshot_signatures": ["old|1|abc"],
            "occurrence_ids": ["occ-old"],
            "notification_ids": ["notice-old"],
            "run_ids": ["run-old"],
        },
    }
    current = {
        "snapshots": [
            {"id": "new", "provider_version": "2", "sha256": "def"},
            {"id": "old", "provider_version": "1", "sha256": "abc"},
        ],
        "history": [
            {
                "occurrence_id": "occ-new",
                "trigger_type": "event",
                "run_id": "run-new",
                "run_state": "completed",
            },
            {
                "occurrence_id": "occ-old",
                "trigger_type": "event",
                "run_id": "run-old",
                "run_state": "completed",
            },
        ],
        "notifications": [
            {
                "id": "notice-new",
                "automation_id": "automation-1",
                "occurrence_id": "occ-new",
                "kind": "automation_completed",
            },
            {
                "id": "notice-old",
                "automation_id": "automation-1",
                "occurrence_id": "occ-old",
                "kind": "automation_completed",
            },
        ],
        "runs": [{"id": "run-new"}, {"id": "run-old"}],
    }
    evidence = probe.transition_evidence(state, current)
    assert evidence["occurrence_id"] == "occ-new"
    assert evidence["run_id"] == "run-new"
    assert evidence["completion_notification_id"] == "notice-new"


def test_transition_evidence_rejects_duplicate_new_occurrences():
    state = {
        "capability": "email_read",
        "automation_id": "automation-1",
        "baseline": {
            "snapshot_signatures": [],
            "occurrence_ids": [],
            "notification_ids": [],
            "run_ids": [],
        },
    }
    current = {
        "snapshots": [{"id": "new", "provider_version": "1", "sha256": "abc"}],
        "history": [
            {"occurrence_id": "occ-1", "trigger_type": "event", "run_id": "run-1", "run_state": "completed"},
            {"occurrence_id": "occ-2", "trigger_type": "event", "run_id": "run-2", "run_state": "completed"},
        ],
        "notifications": [],
        "runs": [{"id": "run-1"}, {"id": "run-2"}],
    }
    with pytest.raises(probe.ProactiveReadProbeFailure, match="exactly one"):
        probe.transition_evidence(state, current)
