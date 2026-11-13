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


def test_clean_origin_rejects_non_https_or_path():
    assert probe.clean_origin("https://stage.example.test") == "https://stage.example.test"
    for value in (
        "http://stage.example.test",
        "https://stage.example.test/api",
        "https://user:pass@stage.example.test",
    ):
        with pytest.raises(probe.ScheduledProfileProbeFailure):
            probe.clean_origin(value)


def test_simple_reminder_is_not_misclassified_as_agent_backed_goal_run():
    assert "scheduled_reminder" not in probe.SCENARIOS


class _ScopeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


@pytest.mark.parametrize("change", ["connector", "memory", "stale_revision", "empty_documents", "wrong_goal"])
def test_daily_scope_fails_closed_on_unapproved_read_authority(change):
    automation = {
        "goal_id": "goal-1", "goal_revision": 2,
        "connector_read_grant_ids": [],
    }
    goal = {"id": "goal-1", "revision": 2, "state": "active",
            "authorized_resources": [{"kind": "document", "reference": "doc-1"}]}
    if change == "connector":
        automation["connector_read_grant_ids"] = ["external-read-grant"]
    elif change == "memory":
        goal["authorized_resources"].append({"kind": "memory_namespace", "reference": "private"})
    elif change == "stale_revision":
        goal["revision"] = 3
    elif change == "empty_documents":
        goal["authorized_resources"] = []
    elif change == "wrong_goal":
        goal["id"] = "goal-2"

    class Client:
        def get(self, path, **kwargs):
            assert path == "/api/v1/goals/goal-1"
            assert kwargs["headers"]["Authorization"] == "Bearer synthetic-token"
            return _ScopeResponse(goal)

    with pytest.raises(probe.ScheduledProfileProbeFailure):
        probe.load_authorized_daily_scope(Client(), "synthetic-token", automation)


def test_daily_scope_is_bound_to_live_owner_goal_and_pinned_documents():
    automation = {"goal_id": "goal-1", "goal_revision": 2,
                  "connector_read_grant_ids": []}
    goal = {"id": "goal-1", "revision": 2, "state": "active",
            "authorized_resources": [{"kind": "document", "reference": "doc-1"},
                                     {"kind": "document", "reference": "doc-2"}]}

    class Client:
        def get(self, path, **kwargs):
            return _ScopeResponse(goal)

    scope = probe.load_authorized_daily_scope(Client(), "synthetic-token", automation)
    assert scope == {"goal_id": "goal-1", "goal_revision": 2,
                     "authorized_document_ids": ["doc-1", "doc-2"]}
    probe.require_daily_run_scope(["doc-1", "doc-2"], scope)
    with pytest.raises(probe.ScheduledProfileProbeFailure):
        probe.require_daily_run_scope(["doc-1", "not-approved"], scope)


def test_verify_rejects_unapproved_daily_run_pins_before_writing_evidence(monkeypatch, tmp_path):
    from argparse import Namespace
    import json

    class Response:
        status_code = 200

        def json(self):
            return {"id": "run-1", "state": "completed",
                    "document_ids": ["doc-evil"], "input_version_ids": ["v-evil"]}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, path, **_kwargs):
            assert path == "/api/v1/agent-runs/run-1"
            return Response()

    release = {"release_id": "release-1"}
    state = {
        "schema_version": 1, "scenario": "daily_coworker",
        "release": release, "owner_id": "owner-1", "automation_id": "automation-1",
        "automation_revision": 1, "timezone": "Asia/Dhaka",
        "schedule": {"kind": "daily", "hour": 8, "minute": 0},
        "run_profile": "briefing", "output_language": "en", "quiet_hours": None,
        "synthetic_account_label": "test-synthetic", "prepared_at": "2026-11-12T01:30:00Z",
        "baseline_occurrence_ids": [], "baseline_notification_ids": [],
        "goal_id": "goal-1", "goal_revision": 1,
        "authorized_document_ids": ["doc-1"],
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    current = {
        "owner_id": "owner-1", "automation": {"revision": 1},
        "daily_scope": {"goal_id": "goal-1", "goal_revision": 1,
                        "authorized_document_ids": ["doc-1"]},
        "history": [{"occurrence_id": "occ-1", "trigger_type": "schedule",
                     "occurrence_state": "accepted", "run_state": "completed",
                     "run_id": "run-1", "due_at": "2026-11-12T02:00:00Z"}],
        "notifications": [
            {"id": "start", "automation_id": "automation-1", "occurrence_id": "occ-1",
             "kind": "automation_started"},
            {"id": "done", "automation_id": "automation-1", "occurrence_id": "occ-1",
             "kind": "automation_completed"},
        ],
    }
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://stage.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "fake-token")
    monkeypatch.setattr(probe.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(probe, "release_identity", lambda *_args: release)
    monkeypatch.setattr(probe, "load_owned", lambda *_args: current)
    clock = iter((0, 0, 2))
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(probe.time, "sleep", lambda *_args: None)
    args = Namespace(
        state=path, rollout=tmp_path / "rollout.json",
        provider_policy_plan=tmp_path / "plan.json",
        output=tmp_path / "evidence.json", prior_evidence=None,
        operator_case_reference="CASE-7", timeout=1, poll_interval=1,
    )
    with pytest.raises(probe.ScheduledProfileProbeFailure,
                       match="owner-approved documents"):
        probe.verify(args)
    assert not args.output.exists()
