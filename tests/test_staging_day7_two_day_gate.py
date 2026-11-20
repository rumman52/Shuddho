from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.staging_day7_two_day_gate import GateFailure, verify_two_day


RELEASE = {"release_id": "test-release", "source_revision": "a" * 40,
           "environment": "staging", "deployment_reference": "deploy-123",
           "rollout_manifest_sha256": "b" * 64, "provider_policy_sha256": "c" * 64}


def evidence(day: int, version: str) -> dict:
    due = f"2026-11-{day:02d}T02:00:00+00:00"
    return {
        "schema_version": 2, "evidence_kind": "pa10_scheduled_profile",
        "scenario": "daily_coworker", "status": "passed", "release": deepcopy(RELEASE),
        "synthetic_account_label": "stage-day7-synthetic", "owner_id": "owner-1",
        "automation_id": "automation-1", "automation_revision": 1,
        "timezone": "Asia/Dhaka", "schedule": {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []},
        "run_profile": "briefing", "output_language": "en", "quiet_hours": {"start": "22:00", "end": "07:00"},
        "expires_at": "2026-11-15T02:00:00+00:00",
        "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        "prepared_at": f"2026-11-{day:02d}T01:30:00+00:00",
        "verified_at": f"2026-11-{day:02d}T02:07:00+00:00",
        "occurrence_id": f"occ-{day}", "due_at": due, "run_id": f"run-{day}",
        "run_state": "completed",
        "completion_notification_id": f"completed-{day}", "new_notification_count": 1,
        "input_version_ids": [version], "document_ids": ["doc-1"],
        "authorized_document_ids": ["doc-1"], "goal_id": "goal-1", "goal_revision": 1,
        "project_id": "project-1",
        "operator_case_reference": "CASE-7",
    }


def pause_evidence() -> dict:
    return {"status": "paused", "release": deepcopy(RELEASE), "owner_id": "owner-1",
            "synthetic_account_label": "stage-day7-synthetic",
            "automation_id": "automation-1", "goal_id": "goal-1",
            "goal_revision": 1, "authorized_document_ids": ["doc-1"],
            "project_id": "project-1", "expires_at": "2026-11-15T02:00:00+00:00",
            "schedule_applied_revision": 2, "schedule_applied_enabled": False,
            "previous_revision": 1, "paused_revision": 2,
            "paused_at": "2026-11-13T02:10:00+00:00",
            "operator_case_reference": "CASE-7"}


def valid_pair():
    first, second = evidence(12, "v1"), evidence(13, "v2")
    second["prior_run_input_version_ids"] = ["v1"]
    for item in (first, second):
        item["overlap_policy"] = "skip"
        item["catchup_window_seconds"] = 3600
    paused = pause_evidence()
    paused.update({
        "pause_baseline_occurrence_ids": ["occ-12", "occ-13"],
        "pause_baseline_run_ids": ["run-12", "run-13"],
        "pause_baseline_notification_ids": ["completed-12", "completed-13"],
        "post_pause_observation": {
            "due_at": "2026-11-14T02:00:00+00:00",
            "observed_at": "2026-11-14T03:10:00+00:00",
            "new_occurrence_count": 0, "new_run_count": 0,
            "new_notification_count": 0,
            "automation_state": "paused",
            "schedule_applied_revision": 2,
            "schedule_applied_enabled": False,
            "operator_case_reference": "CASE-7",
        },
    })
    return first, second, paused


def test_two_day_gate_rejects_multiple_document_changes():
    first, second, paused = valid_pair()
    for item in (first, second, paused):
        item["authorized_document_ids"] = ["doc-1", "doc-2"]
    first["document_ids"] = ["doc-1", "doc-2"]
    second["document_ids"] = ["doc-1", "doc-2"]
    first["input_version_ids"] = ["v1", "other-v1"]
    second["prior_run_input_version_ids"] = ["v1", "other-v1"]
    second["input_version_ids"] = ["v2", "other-v2"]
    with pytest.raises(GateFailure, match="Exactly one authorized document"):
        verify_two_day(first, second, paused)


def test_two_day_gate_tracks_changed_document_across_reordered_sources():
    first, second, paused = valid_pair()
    for item in (first, second, paused):
        item["authorized_document_ids"] = ["doc-1", "doc-2"]
    first["document_ids"] = ["doc-1", "doc-2"]
    first["input_version_ids"] = ["v1", "other-v1"]
    second["document_ids"] = ["doc-2", "doc-1"]
    second["prior_run_input_version_ids"] = ["v1", "other-v1"]
    second["input_version_ids"] = ["other-v1", "v2"]
    result = verify_two_day(first, second, paused)
    assert result["changed_document_id"] == "doc-1"


def test_two_day_gate_accepts_unchanged_scope_fresh_pins_and_pause():
    first, second, paused = valid_pair()
    report = verify_two_day(first, second, paused)
    assert report["status"] == "passed"
    assert report["changed_document_id"] == "doc-1"
    assert report["first_input_version_ids"] == ["v1"]
    assert report["second_input_version_ids"] == ["v2"]
    assert report["scheduled_local_dates"] == ["2026-11-12", "2026-11-13"]


@pytest.mark.parametrize("mutation", [
    lambda a, b, p: b.update(input_version_ids=["v1"]),
    lambda a, b, p: b.update(prior_run_input_version_ids=["wrong"]),
    lambda a, b, p: b.update(document_ids=["doc-other"]),
    lambda a, b, p: b.update(run_id=a["run_id"]),
    lambda a, b, p: b.update(occurrence_id=a["occurrence_id"]),
    lambda a, b, p: b.update(due_at="2026-11-14T02:00:00+00:00"),
    lambda a, b, p: b.update(due_at="2026-11-13T02:01:00+00:00"),
    lambda a, b, p: b.update(release=dict(b["release"], release_id="changed")),
    lambda a, b, p: b.update(status="failed"),
    lambda a, b, p: p.update(status="active"),
    lambda a, b, p: p.update(paused_at="2026-11-12T10:00:00+00:00"),
    lambda a, b, p: b.update(prior_run_input_version_ids=[]),
    lambda a, b, p: b.update(new_notification_count=3),
    lambda a, b, p: b.update(automation_id="someone-else"),
    lambda a, b, p: b.update(project_id="project-other"),
    lambda a, b, p: b.update(expires_at="2026-11-12T02:00:00+00:00"),
    lambda a, b, p: b.update(schedule_applied_enabled=False),
    lambda a, b, p: p.update(schedule_applied_enabled=True),
    lambda a, b, p: p.update(paused_revision=1),
])
def test_two_day_gate_rejects_invalid_operator_evidence(mutation):
    first, second, paused = valid_pair()
    mutation(first, second, paused)
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)


def test_two_day_gate_rejects_missing_run_source_evidence():
    first, second, paused = valid_pair()
    del first["input_version_ids"]
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)


@pytest.mark.parametrize("field", ["future_verification", "future_pause", "boolean_revision"])
def test_two_day_gate_rejects_unobserved_times_and_invalid_revision(field):
    first, second, paused = valid_pair()
    future = datetime.now(timezone.utc) + timedelta(days=2)
    if field == "future_verification":
        second["verified_at"] = future.isoformat()
        paused["paused_at"] = (future + timedelta(minutes=1)).isoformat()
    elif field == "future_pause":
        paused["paused_at"] = future.isoformat()
    else:
        second["automation_revision"] = True
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)


def test_two_day_gate_checks_dst_local_calendar_not_24_hours():
    first, second, paused = valid_pair()
    for e in (first, second):
        e["timezone"] = "America/New_York"
        e["schedule"] = {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []}
    first["due_at"] = "2026-10-31T12:00:00+00:00"
    second["due_at"] = "2026-11-01T13:00:00+00:00"
    first["prepared_at"] = "2026-10-31T11:30:00+00:00"
    first["verified_at"] = "2026-10-31T12:07:00+00:00"
    second["prepared_at"] = "2026-11-01T12:30:00+00:00"
    second["verified_at"] = "2026-11-01T13:07:00+00:00"
    paused["paused_at"] = "2026-11-01T14:00:00+00:00"
    paused["post_pause_observation"]["due_at"] = "2026-11-02T13:00:00+00:00"
    paused["post_pause_observation"]["observed_at"] = "2026-11-02T14:10:00+00:00"
    assert verify_two_day(first, second, paused)["scheduled_local_dates"] == ["2026-10-31", "2026-11-01"]


def test_pause_two_day_verifies_evidence_before_mutating_staging(monkeypatch, tmp_path):
    import argparse
    import json
    from scripts import staging_pa10_scheduled_profile as probe

    first, second, _ = valid_pair()
    first_path, second_path, state_path = (tmp_path / p for p in ("first.json", "second.json", "state.json"))
    first_path.write_text(json.dumps(first))
    second_path.write_text(json.dumps(second))
    state_path.write_text(json.dumps({
        "scenario": "daily_coworker", "release": RELEASE,
        "owner_id": "owner-1", "automation_id": "automation-1",
        "automation_revision": 1,
        "synthetic_account_label": "stage-day7-synthetic",
        "goal_id": "goal-1", "goal_revision": 1,
        "authorized_document_ids": ["doc-1"], "project_id": "project-1",
        "expires_at": "2026-11-15T02:00:00+00:00",
    }))
    args = argparse.Namespace(
        state=state_path, first_evidence=first_path, second_evidence=second_path,
        rollout=tmp_path / "rollout.json", provider_policy_plan=tmp_path / "policy.json",
        operator_case_reference="CASE-7", output=tmp_path / "paused.json",
    )
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://staging.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "test-fake-token")
    monkeypatch.setattr(probe, "utcnow_iso", lambda: "2026-11-13T02:10:00+00:00")
    monkeypatch.setattr(probe, "release_identity", lambda *_args: deepcopy(RELEASE))
    monkeypatch.setattr(probe, "load_owned", lambda *_args: {
        "owner_id": "owner-1", "automation": {
            "revision": 1, "expires_at": "2026-11-15T02:00:00+00:00",
            "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        },
        "daily_scope": {"goal_id": "goal-1", "goal_revision": 1,
                        "authorized_document_ids": ["doc-1"], "project_id": "project-1"},
    })

    class Response:
        status_code = 200

        def json(self):
            return {
                "id": "automation-1", "state": "paused", "revision": 2,
                "schedule_applied_revision": 2, "schedule_applied_enabled": False,
                "schedule_error_code": None,
            }

    class Client:
        def __init__(self):
            self.posts = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, path, **kwargs):
            self.posts.append((path, kwargs["json"]))
            return Response()

        def get(self, path, **kwargs):
            assert path == "/api/v1/automations/automation-1"
            return Response()

    client = Client()
    monkeypatch.setattr(probe.httpx, "Client", lambda **_args: client)
    result = probe.pause_two_day(args)
    assert result["paused_revision"] == 2
    assert client.posts == [(
        "/api/v1/automations/automation-1/pause", {"expected_revision": 1},
    )]
    assert json.loads(args.output.read_text())["status"] == "paused"

    second["input_version_ids"] = ["v1"]
    second_path.write_text(json.dumps(second))
    with pytest.raises(probe.ScheduledProfileProbeFailure, match="rejected before pause"):
        probe.pause_two_day(args)
    assert len(client.posts) == 1  # no second pause on failed preflight


def test_staging_script_requires_prior_evidence_option_for_recheck():
    from scripts.staging_pa10_scheduled_profile import build_parser

    parsed = build_parser().parse_args([
        "verify", "--rollout", "rollout.json", "--provider-policy-plan", "policy.json",
        "--state", "state.json", "--operator-case-reference", "CASE-7",
        "--output", "day8.json", "--prior-evidence", "day7.json",
    ])
    assert str(parsed.prior_evidence) == "day7.json"

@pytest.mark.parametrize("broken", ["empty_release", "empty_deployment_reference", "blank_synthetic_account", "mismatched_operator_case"])
def test_two_day_gate_rejects_unbound_staging_evidence(broken):
    first, second, paused = valid_pair()
    if broken == "empty_release":
        first["release"] = second["release"] = paused["release"] = {}
    elif broken == "empty_deployment_reference":
        for entry in (first, second, paused):
            entry["release"]["deployment_reference"] = ""
    elif broken == "blank_synthetic_account":
        for entry in (first, second, paused):
            entry["synthetic_account_label"] = " "
    else:
        second["operator_case_reference"] = "UNRELATED-CASE"
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)

@pytest.mark.parametrize("defect", [
    "missing_completion_notification_id",
    "cross_day_duplicate_notification_id",
    "wrong_notification_count",
    "legacy_started_notification",
    "legacy_schema_v1",
    "stale_day8_baseline",
])
def test_two_day_gate_rejects_invalid_completion_notices_and_stale_baseline(defect):
    first, second, paused = valid_pair()
    if defect == "missing_completion_notification_id":
        first["completion_notification_id"] = ""
    elif defect == "cross_day_duplicate_notification_id":
        second["completion_notification_id"] = first["completion_notification_id"]
    elif defect == "wrong_notification_count":
        second["new_notification_count"] = 2
    elif defect == "legacy_started_notification":
        second["started_notification_id"] = "started-13"
    elif defect == "legacy_schema_v1":
        first["schema_version"] = 1
    else:
        # A second-day baseline must be captured after the first day's verified run,
        # otherwise it cannot prove the second independent natural occurrence.
        second["prepared_at"] = first["prepared_at"]
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)


@pytest.mark.parametrize("defect", [
    "run_uses_unapproved_document", "missing_owner_approved_scope",
    "approval_changed_between_days",
])
def test_day7_gate_rejects_unapproved_goal_scope(defect):
    first, second, paused = valid_pair()
    if defect == "run_uses_unapproved_document":
        first["document_ids"] = second["document_ids"] = ["doc-evil"]
    elif defect == "missing_owner_approved_scope":
        for item in (first, second):
            del item["authorized_document_ids"]
    else:
        second["authorized_document_ids"] = ["doc-evil"]
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)


def test_two_day_gate_does_not_qualify_pause_acknowledgement_alone():
    first, second, paused = valid_pair()
    del paused["post_pause_observation"]
    with pytest.raises(GateFailure, match="post-pause"):
        verify_two_day(first, second, paused)


@pytest.mark.parametrize("defect", [
    "due_earlier", "observed_too_early", "future_observation", "new_occurrence",
    "new_run", "new_notification", "resumed", "wrong_applied_revision",
    "wrong_case", "missing_history_baseline", "removed_first_occurrence",
    "wrong_overlap", "missing_catchup_bound", "pause_after_opportunity",
    "expiry_before_opportunity",
])
def test_two_day_gate_rejects_unproven_paused_opportunity(defect):
    first, second, paused = valid_pair()
    observation = paused["post_pause_observation"]
    if defect == "due_earlier":
        observation["due_at"] = "2026-11-13T02:00:00+00:00"
    elif defect == "observed_too_early":
        observation["observed_at"] = "2026-11-14T02:05:00+00:00"
    elif defect == "future_observation":
        observation["observed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif defect == "new_occurrence":
        observation["new_occurrence_count"] = 1
    elif defect == "new_run":
        observation["new_run_count"] = 1
    elif defect == "new_notification":
        observation["new_notification_count"] = 1
    elif defect == "resumed":
        observation["automation_state"] = "active"
    elif defect == "wrong_applied_revision":
        observation["schedule_applied_revision"] = 1
    elif defect == "wrong_case":
        observation["operator_case_reference"] = "someone-else"
    elif defect == "missing_history_baseline":
        del paused["pause_baseline_run_ids"]
    elif defect == "removed_first_occurrence":
        paused["pause_baseline_occurrence_ids"] = ["occ-13"]
    elif defect == "wrong_overlap":
        first["overlap_policy"] = "buffer_one"
    elif defect == "missing_catchup_bound":
        del second["catchup_window_seconds"]
    elif defect == "pause_after_opportunity":
        paused["paused_at"] = "2026-11-14T02:01:00+00:00"
    elif defect == "expiry_before_opportunity":
        for item in (first, second, paused):
            item["expires_at"] = "2026-11-14T01:59:00+00:00"
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)
