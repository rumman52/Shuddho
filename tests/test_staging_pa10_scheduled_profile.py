from __future__ import annotations

import pytest

from scripts import staging_pa10_scheduled_profile as probe


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="ALLOW_SCHEDULED_PROFILES"):
        probe.require_guard()


@pytest.mark.parametrize(("scenario", "has_prior", "has_edit", "error"), [
    ("daily_coworker", True, False, "requires an independently reviewed source-edit"),
    ("daily_coworker", False, True, "permitted only for a second daily"),
    ("weekly_coworker", False, True, "permitted only for a second daily"),
])
def test_source_edit_receipt_is_required_only_for_second_daily_probe(
    monkeypatch, tmp_path, scenario, has_prior, has_edit, error,
):
    # These config failures must occur before any authenticated network call.
    from argparse import Namespace
    import json

    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": 1, "scenario": scenario}))
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://stage.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "fake-token")
    monkeypatch.setattr(probe.httpx, "Client", lambda **_: (_ for _ in ()).throw(
        AssertionError("no network before source-edit configuration is validated")))
    args = Namespace(
        state=state,
        prior_evidence=tmp_path / "day7.json" if has_prior else None,
        source_edit_receipt=tmp_path / "edit.json" if has_edit else None,
    )
    with pytest.raises(probe.ScheduledProfileProbeFailure, match=error):
        probe.verify(args)


def test_second_day_verify_parser_exposes_source_edit_receipt():
    parsed = probe.build_parser().parse_args([
        "verify", "--rollout", "rollout.json", "--provider-policy-plan", "plan.json",
        "--state", "state.json", "--operator-case-reference", "CASE-7",
        "--output", "day8.json", "--prior-evidence", "day7.json",
        "--source-edit-receipt", "edit.json",
    ])
    assert str(parsed.source_edit_receipt) == "edit.json"


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


def test_future_expiry_rejects_missing_naive_or_past_values():
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="explicit expiry"):
        probe.require_future_expiry(None)
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="timezone-aware"):
        probe.require_future_expiry("2030-01-01T00:00:00")
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="future"):
        probe.require_future_expiry("2020-01-01T00:00:00+00:00")
    assert probe.require_future_expiry("2030-01-01T00:00:00+00:00")


def test_clean_origin_rejects_non_https_or_path():
    assert probe.clean_origin("https://stage.example.test") == "https://stage.example.test"
    for value in (
        "http://stage.example.test",
        "https://stage.example.test/api",
        "https://user:pass@stage.example.test",
    ):
        with pytest.raises(probe.ScheduledProfileProbeFailure):
            probe.clean_origin(value)



@pytest.mark.parametrize("unsafe_origin", [
    "https://localhost",
    "https://127.0.0.1",
    "https://10.0.0.1",
    "https://192.168.1.1",
    "https://stage.example.test\t",
    "https://stage.example.test\n",
    "https://stage.example.test:99999",
    "https://stage.example.test///",
    "https://stage.example.test?",
    "https://stage.example.test#",
])
def test_clean_origin_rejects_unsafe_credential_destinations(unsafe_origin):
    # The daily briefing probe sends SHUDDHO_STAGING_TOKEN_A to this origin.
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="SHUDDHO_STAGING_API_BASE_URL"):
        probe.clean_origin(unsafe_origin)


def test_clean_origin_accepts_single_slash_and_valid_tls_port():
    assert probe.clean_origin("https://stage.example.test/") == "https://stage.example.test"
    assert probe.clean_origin("https://stage.example.test:443/") == "https://stage.example.test:443"


def test_simple_reminder_is_not_misclassified_as_agent_backed_goal_run():
    assert "scheduled_reminder" not in probe.SCENARIOS


def test_one_completion_notification_contract_accepts_one_completed_notice():
    notice = {"id": "notice-1", "kind": "automation_completed"}
    assert probe.require_one_completion_notification([notice]) is notice


@pytest.mark.parametrize("notices", [
    [],
    [{"id": "start-1", "kind": "automation_started"}],
    [{"id": "done-1", "kind": "automation_completed"},
     {"id": "done-2", "kind": "automation_completed"}],
    [{"id": "start-1", "kind": "automation_started"},
     {"id": "done-1", "kind": "automation_completed"}],
    [{"kind": "automation_completed"}],
])
def test_one_completion_notification_contract_rejects_noncanonical_notices(notices):
    with pytest.raises(probe.ScheduledProfileProbeFailure,
                       match="exactly one completion notification"):
        probe.require_one_completion_notification(notices)


class _ScopeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


@pytest.mark.parametrize("change", [
    "connector", "memory", "stale_revision", "empty_documents", "wrong_goal",
    "missing_project", "unlinked_project_document",
])
def test_daily_scope_fails_closed_on_unapproved_read_authority(change):
    automation = {
        "goal_id": "goal-1", "goal_revision": 2,
        "connector_read_grant_ids": [],
    }
    goal = {"id": "goal-1", "revision": 2, "state": "active", "project_id": "project-1",
            "authorized_resources": [{"kind": "document", "reference": "doc-1"}]}
    project = {"id": "project-1", "resources": [
        {"resource_type": "document", "resource_id": "doc-1", "title": "Doc 1"},
    ]}
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
    elif change == "missing_project":
        goal["project_id"] = None
    elif change == "unlinked_project_document":
        project["resources"] = []

    class Client:
        def get(self, path, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer synthetic-token"
            if path == "/api/v1/goals/goal-1":
                return _ScopeResponse(goal)
            if path == "/api/v1/projects/project-1":
                return _ScopeResponse(project)
            raise AssertionError(f"Unexpected GET {path}")

    with pytest.raises(probe.ScheduledProfileProbeFailure):
        probe.load_authorized_daily_scope(Client(), "synthetic-token", automation)


def test_daily_scope_is_bound_to_live_owner_goal_and_pinned_documents():
    automation = {"goal_id": "goal-1", "goal_revision": 2,
                  "connector_read_grant_ids": []}
    goal = {"id": "goal-1", "revision": 2, "state": "active", "project_id": "project-1",
            "authorized_resources": [{"kind": "document", "reference": "doc-1"},
                                     {"kind": "document", "reference": "doc-2"}]}
    project = {"id": "project-1", "resources": [
        {"resource_type": "document", "resource_id": "doc-1"},
        {"resource_type": "document", "resource_id": "doc-2"},
    ]}

    class Client:
        def get(self, path, **kwargs):
            return _ScopeResponse(goal if path == "/api/v1/goals/goal-1" else project)

    scope = probe.load_authorized_daily_scope(Client(), "synthetic-token", automation)
    assert scope == {"goal_id": "goal-1", "goal_revision": 2, "project_id": "project-1",
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
        "schedule": {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []},
        "run_profile": "briefing", "output_language": "en",
        "quiet_hours": {"start": "22:00", "end": "07:00"},
        "overlap_policy": "skip", "catchup_window_seconds": 3600,
        "expires_at": "2030-01-01T00:00:00+00:00",
        "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        "synthetic_account_label": "test-synthetic", "prepared_at": "2026-11-12T01:30:00Z",
        "baseline_occurrence_ids": [], "baseline_notification_ids": [],
        "goal_id": "goal-1", "goal_revision": 1, "project_id": "project-1",
        "authorized_document_ids": ["doc-1"],
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    current = {
        "owner_id": "owner-1", "automation": {
            "revision": 1, "expires_at": "2030-01-01T00:00:00+00:00",
            "schedule_applied_revision": 1, "schedule_applied_enabled": True,
            "timezone": state["timezone"], "schedule": state["schedule"],
            "run_profile": state["run_profile"], "output_language": state["output_language"],
            "quiet_hours": state["quiet_hours"], "overlap_policy": state["overlap_policy"],
            "catchup_window_seconds": state["catchup_window_seconds"],
        },
        "daily_scope": {"goal_id": "goal-1", "goal_revision": 1, "project_id": "project-1",
                        "authorized_document_ids": ["doc-1"]},
        "history": [{"occurrence_id": "occ-1", "trigger_type": "schedule",
                     "occurrence_state": "accepted", "run_state": "completed",
                     "run_id": "run-1", "due_at": "2026-11-12T02:00:00Z"}],
        "notifications": [
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


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX mode contract")
def test_scheduled_profile_prepare_state_is_private_with_umask_022(
    monkeypatch, tmp_path,
):
    """Real prepare() must not expose owner, automation or document scope."""
    import argparse
    import os
    import stat

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    snapshot = {
        "owner_id": "owner-synthetic",
        "automation": {
            "revision": 1, "timezone": "Asia/Dhaka",
            "schedule": {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []},
            "run_profile": "briefing", "output_language": "en",
            "quiet_hours": {"start": "22:00", "end": "07:00"},
            "overlap_policy": "skip", "catchup_window_seconds": 3600,
            "expires_at": "2030-01-01T00:00:00+00:00",
            "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        },
        "daily_scope": {
            "goal_id": "goal-1", "goal_revision": 1, "project_id": "project-1",
            "authorized_document_ids": ["private-doc-1"],
        },
        "history": [], "notifications": [],
    }
    monkeypatch.setattr(probe, "require_guard", lambda: None)
    monkeypatch.setattr(probe, "clean_origin", lambda origin: origin)
    monkeypatch.setattr(probe, "env", lambda name: {
        "SHUDDHO_STAGING_API_BASE_URL": "https://stage.example.test",
        "SHUDDHO_STAGING_TOKEN_A": "synthetic-token",
        "SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL": "synthetic-label",
    }[name])
    monkeypatch.setattr(probe.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(probe, "release_identity", lambda *_args: {"release_id": "release-1"})
    monkeypatch.setattr(probe, "load_owned", lambda *_args: snapshot)
    state_path = tmp_path / "schedule-state.json"
    args = argparse.Namespace(
        scenario="daily_coworker", automation_id="automation-1",
        rollout=tmp_path / "rollout.json",
        provider_policy_plan=tmp_path / "provider.json", state=state_path,
    )
    old_mask = os.umask(0o022)
    try:
        result = probe.prepare(args)
    finally:
        os.umask(old_mask)
    assert result["owner_id"] == "owner-synthetic"
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert "private-doc-1" in state_path.read_text(encoding="utf-8")


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX mode contract")
def test_scheduled_profile_private_writer_replaces_world_readable_file(tmp_path):
    import stat

    output = tmp_path / "verified-evidence.json"
    output.write_text("old-sensitive-evidence", encoding="utf-8")
    output.chmod(0o644)
    probe.write_private_evidence(output, {"owner_id": "new-synthetic-owner"})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_text(encoding="utf-8").find("new-synthetic-owner") >= 0
    assert "old-sensitive-evidence" not in output.read_text(encoding="utf-8")


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX symlink contract")
def test_scheduled_profile_private_writer_cannot_follow_preexisting_symlink(tmp_path):
    import stat

    target = tmp_path / "other-private-file.json"
    target.write_text("DO NOT ALTER", encoding="utf-8")
    output = tmp_path / "scheduled-evidence.json"
    output.symlink_to(target)
    probe.write_private_evidence(output, {"run_id": "synthetic-run-1"})
    assert target.read_text(encoding="utf-8") == "DO NOT ALTER"
    assert not output.is_symlink()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX atomicity contract")
def test_scheduled_profile_private_writer_failed_replace_keeps_original(
    monkeypatch, tmp_path,
):
    import os

    output = tmp_path / "schedule-state.json"
    output.write_text("verified-original", encoding="utf-8")
    output.chmod(0o600)

    def deny_replace(*_args, **_kwargs):
        raise OSError("synthetic-private-path-token")

    monkeypatch.setattr(os, "replace", deny_replace)
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="private operator evidence") as exc:
        probe.write_private_evidence(output, {"owner_id": "synthetic-owner"})
    assert "synthetic-private-path-token" not in str(exc.value)
    assert output.read_text(encoding="utf-8") == "verified-original"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["schedule-state.json"]


@pytest.mark.parametrize(("case", "should_pass"), [
    ("new_unmatched_same_automation", False),
    ("new_notice_other_automation", True),
    ("old_notice_in_prepared_baseline", True),
])
def test_daily_verify_counts_all_new_notices_for_selected_automation(
    monkeypatch, tmp_path, case, should_pass,
):
    """An orphan/duplicate owner notice must not disappear behind occurrence filtering."""
    from argparse import Namespace
    import json

    release = {"release_id": "synthetic-release"}
    existing = {
        "id": "old-notice", "automation_id": "automation-1",
        "occurrence_id": "old-occ", "kind": "automation_completed",
    }
    extra = {
        "id": "extra-notice",
        "automation_id": (
            "automation-other" if case == "new_notice_other_automation" else "automation-1"
        ),
        "occurrence_id": "unexpected-occurrence",
        "kind": "automation_completed",
    }
    state = {
        "schema_version": 1, "scenario": "daily_coworker",
        "release": release, "owner_id": "owner-1", "automation_id": "automation-1",
        "automation_revision": 1, "timezone": "Asia/Dhaka",
        "schedule": {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []},
        "run_profile": "briefing", "output_language": "en",
        "quiet_hours": {"start": "22:00", "end": "07:00"},
        "overlap_policy": "skip", "catchup_window_seconds": 3600,
        "expires_at": "2030-01-01T00:00:00+00:00",
        "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        "synthetic_account_label": "synthetic-owner",
        "prepared_at": "2026-11-12T01:30:00+00:00",
        "baseline_occurrence_ids": [],
        "baseline_notification_ids": (
            ["old-notice"] if case == "old_notice_in_prepared_baseline" else []
        ),
        "goal_id": "goal-1", "goal_revision": 1, "project_id": "project-1",
        "authorized_document_ids": ["doc-1"],
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    current = {
        "owner_id": "owner-1",
        "automation": {
            "revision": 1,
            "expires_at": "2030-01-01T00:00:00+00:00",
            "schedule_applied_revision": 1, "schedule_applied_enabled": True,
            "timezone": state["timezone"], "schedule": state["schedule"],
            "run_profile": state["run_profile"], "output_language": state["output_language"],
            "quiet_hours": state["quiet_hours"], "overlap_policy": state["overlap_policy"],
            "catchup_window_seconds": state["catchup_window_seconds"],
        },
        "daily_scope": {
            "goal_id": "goal-1", "goal_revision": 1,
            "project_id": "project-1", "authorized_document_ids": ["doc-1"],
        },
        "history": [{
            "occurrence_id": "occ-1", "trigger_type": "schedule",
            "occurrence_state": "accepted", "run_state": "completed",
            "run_id": "run-1", "due_at": "2026-11-12T02:00:00+00:00",
        }],
        "notifications": [
            {"id": "completed-1", "automation_id": "automation-1",
             "occurrence_id": "occ-1", "kind": "automation_completed"},
            existing if case == "old_notice_in_prepared_baseline" else extra,
        ],
    }

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, path, **_kwargs):
            assert path == "/api/v1/agent-runs/run-1"
            return _ScopeResponse({
                "id": "run-1", "state": "completed",
                "document_ids": ["doc-1"], "input_version_ids": ["v1"],
            })

    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://stage.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "synthetic-token")
    monkeypatch.setattr(probe.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(probe, "release_identity", lambda *_args: release)
    monkeypatch.setattr(probe, "load_owned", lambda *_args: current)
    clock = iter((0, 0, 2))
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(probe.time, "sleep", lambda *_args: None)
    args = Namespace(
        state=state_path, rollout=tmp_path / "rollout.json",
        provider_policy_plan=tmp_path / "provider.json",
        output=tmp_path / "verified.json", prior_evidence=None,
        operator_case_reference="CASE-7", timeout=1, poll_interval=1,
    )
    if should_pass:
        report = probe.verify(args)
        assert report["status"] == "passed"
        assert report["new_notification_count"] == 1
        assert args.output.exists()
    else:
        with pytest.raises(
            probe.ScheduledProfileProbeFailure,
            match="unexpected new notification|one new notification",
        ):
            probe.verify(args)
        assert not args.output.exists()


PREPARED_DAILY_PROFILE = {
    "timezone": "Asia/Dhaka",
    "schedule": {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []},
    "run_profile": "briefing",
    "output_language": "en",
    "quiet_hours": {"start": "22:00", "end": "07:00"},
    "overlap_policy": "skip",
    "catchup_window_seconds": 3600,
}


def test_daily_prepared_profile_accepts_identical_owner_authorized_runtime_readback():
    from copy import deepcopy

    state = deepcopy(PREPARED_DAILY_PROFILE)
    automation = deepcopy(PREPARED_DAILY_PROFILE)
    probe.require_prepared_daily_profile(state, automation)


@pytest.mark.parametrize(("field", "unexpected"), [
    ("timezone", "UTC"),
    ("schedule", {"kind": "daily", "hour": 9, "minute": 0, "weekdays": []}),
    ("run_profile", "deadline"),
    ("output_language", "bn"),
    ("quiet_hours", {"start": "23:00", "end": "07:00"}),
    ("overlap_policy", "allow"),
    ("catchup_window_seconds", 7200),
])
def test_daily_prepared_profile_rejects_unrevisioned_policy_drift(
    field, unexpected,
):
    from copy import deepcopy

    state = deepcopy(PREPARED_DAILY_PROFILE)
    automation = deepcopy(PREPARED_DAILY_PROFILE)
    automation[field] = unexpected
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="prepared|drift"):
        probe.require_prepared_daily_profile(state, automation)


@pytest.mark.parametrize("missing", [
    "timezone", "schedule", "run_profile", "output_language",
    "quiet_hours", "overlap_policy", "catchup_window_seconds",
])
def test_daily_prepared_profile_rejects_incomplete_runtime_or_evidence_scope(missing):
    from copy import deepcopy

    state = deepcopy(PREPARED_DAILY_PROFILE)
    automation = deepcopy(PREPARED_DAILY_PROFILE)
    automation.pop(missing)
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="prepared|drift"):
        probe.require_prepared_daily_profile(state, automation)


def test_day7_verify_invokes_prepared_profile_readback_gate(monkeypatch, tmp_path):
    """A changed timezone must block an otherwise valid owner/run/notice receipt."""
    from argparse import Namespace
    from copy import deepcopy
    import json

    release = {"release_id": "synthetic-release"}
    state = {
        "schema_version": 1, "scenario": "daily_coworker",
        "release": release, "owner_id": "owner-1",
        "automation_id": "automation-1", "automation_revision": 1,
        **deepcopy(PREPARED_DAILY_PROFILE),
        "expires_at": "2030-01-01T00:00:00+00:00",
        "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        "synthetic_account_label": "synthetic-owner",
        "prepared_at": "2026-11-12T01:30:00+00:00",
        "baseline_occurrence_ids": [], "baseline_notification_ids": [],
        "goal_id": "goal-1", "goal_revision": 1, "project_id": "project-1",
        "authorized_document_ids": ["doc-1"],
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    current = {
        "owner_id": "owner-1",
        "automation": {
            **deepcopy(PREPARED_DAILY_PROFILE),
            "timezone": "UTC",  # runtime drift, but revision stays unchanged
            "revision": 1,
            "expires_at": "2030-01-01T00:00:00+00:00",
            "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        },
        "daily_scope": {
            "goal_id": "goal-1", "goal_revision": 1,
            "project_id": "project-1", "authorized_document_ids": ["doc-1"],
        },
        "history": [{
            "occurrence_id": "occ-1", "trigger_type": "schedule",
            "occurrence_state": "accepted", "run_state": "completed",
            "run_id": "run-1", "due_at": "2026-11-12T02:00:00+00:00",
        }],
        "notifications": [{
            "id": "completed-1", "automation_id": "automation-1",
            "occurrence_id": "occ-1", "kind": "automation_completed",
        }],
    }

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, path, **_kwargs):
            assert path == "/api/v1/agent-runs/run-1"
            return _ScopeResponse({
                "id": "run-1", "state": "completed",
                "document_ids": ["doc-1"], "input_version_ids": ["v1"],
            })

    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://stage.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "synthetic-token")
    monkeypatch.setattr(probe.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(probe, "release_identity", lambda *_args: release)
    monkeypatch.setattr(probe, "load_owned", lambda *_args: current)
    clock = iter((0, 0, 2))
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(probe.time, "sleep", lambda *_args: None)
    args = Namespace(
        state=state_path, rollout=tmp_path / "rollout.json",
        provider_policy_plan=tmp_path / "provider.json",
        output=tmp_path / "verified.json", prior_evidence=None,
        operator_case_reference="CASE-7", timeout=1, poll_interval=1,
    )
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="prepared|drift"):
        probe.verify(args)
    assert not args.output.exists()


@pytest.mark.parametrize(("field", "invalid"), [
    ("timezone", "Invalid/Zone"),
    ("timezone", 123),
    ("schedule", {"kind": "daily", "hour": True, "minute": 0, "weekdays": []}),
    ("schedule", {"kind": "daily", "hour": 8, "minute": 60, "weekdays": []}),
    ("schedule", {"kind": "daily", "hour": 8, "minute": 0}),
    ("schedule", {"kind": "daily", "hour": 8, "minute": 0, "weekdays": ["mon"]}),
    ("schedule", {"kind": "daily", "hour": 8, "minute": 0, "weekdays": [], "extra": True}),
    ("quiet_hours", None),
    ("quiet_hours", {"start": "22:00", "end": "22:00"}),
    ("quiet_hours", {"start": "25:00", "end": "07:00"}),
    ("overlap_policy", "buffer_one"),
    ("catchup_window_seconds", 60),
    ("catchup_window_seconds", 7200),
    ("catchup_window_seconds", 3600.0),
])
def test_matching_daily_profile_must_still_meet_pilot_contract(field, invalid):
    from copy import deepcopy

    state = deepcopy(PREPARED_DAILY_PROFILE)
    state[field] = invalid
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="Daily briefing"):
        probe.require_prepared_daily_profile(state, deepcopy(state))


def test_daily_profile_rejects_equal_but_wrongly_typed_prepared_value():
    from copy import deepcopy

    state = deepcopy(PREPARED_DAILY_PROFILE)
    state["catchup_window_seconds"] = 3600.0
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="Daily briefing"):
        probe.require_prepared_daily_profile(state, deepcopy(PREPARED_DAILY_PROFILE))


def test_prepare_rejects_noncontract_daily_policy_before_writing_state(monkeypatch, tmp_path):
    from argparse import Namespace
    from copy import deepcopy

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    snapshot = {
        "owner_id": "synthetic-owner",
        "automation": {
            **deepcopy(PREPARED_DAILY_PROFILE),
            "revision": 1,
            "expires_at": "2030-01-01T00:00:00+00:00",
            "schedule_applied_revision": 1,
            "schedule_applied_enabled": True,
            "catchup_window_seconds": 60,
        },
        "daily_scope": {
            "goal_id": "goal-1", "goal_revision": 1, "project_id": "project-1",
            "authorized_document_ids": ["doc-1"],
        },
        "history": [], "notifications": [],
    }
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://stage.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "synthetic-token")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL", "synthetic-owner")
    monkeypatch.setattr(probe.httpx, "Client", lambda **_kwargs: Client())
    monkeypatch.setattr(probe, "release_identity", lambda *_args: {"release_id": "release-1"})
    monkeypatch.setattr(probe, "load_owned", lambda *_args: snapshot)
    state = tmp_path / "state.json"
    args = Namespace(
        scenario="daily_coworker", automation_id="automation-1",
        rollout=tmp_path / "rollout.json",
        provider_policy_plan=tmp_path / "provider.json", state=state,
    )
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="Daily briefing"):
        probe.prepare(args)
    assert not state.exists()
