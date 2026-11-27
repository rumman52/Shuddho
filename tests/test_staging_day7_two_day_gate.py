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
        "completion_notification_id": f"completed-{day}",
        "new_occurrence_count": 1, "new_run_count": 1,
        "new_notification_count": 1,
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
    second["authorized_source_edit"] = {
        "owner_id": "owner-1", "project_id": "project-1", "document_id": "doc-1",
        "previous_version_id": "v1", "current_version_id": "v2",
        "edited_at": "2026-11-12T10:00:00+00:00",
        "operator_case_reference": "CASE-7", "evidence_sha256": "d" * 64,
    }
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
            "owner_id": "owner-1", "automation_id": "automation-1",
            "release": deepcopy(RELEASE),
        },
    })
    return first, second, paused



@pytest.mark.parametrize(("bad_setting", "expected_error"), [
    ("weekdays_selected", "daily schedule.*weekdays"),
    ("weekdays_missing", "daily schedule.*weekdays"),
    ("weekdays_not_list", "daily schedule.*weekdays"),
    ("quiet_hours_missing", "quiet hours"),
    ("quiet_hours_incomplete", "quiet hours"),
    ("quiet_hours_invalid_clock", "quiet hours"),
    ("quiet_hours_equal", "quiet hours"),
    ("quiet_hours_unexpected_property", "quiet hours"),
])
def test_day7_two_date_gate_rejects_unauthorized_daily_calendar_or_quiet_hours(
    bad_setting, expected_error,
):
    """Matched day-one/day-two claims must still match the runtime schema."""
    first, second, paused = valid_pair()
    for evidence_record in (first, second):
        if bad_setting == "weekdays_selected":
            evidence_record["schedule"]["weekdays"] = ["mon"]
        elif bad_setting == "weekdays_missing":
            del evidence_record["schedule"]["weekdays"]
        elif bad_setting == "weekdays_not_list":
            evidence_record["schedule"]["weekdays"] = "mon"
        elif bad_setting == "quiet_hours_missing":
            evidence_record["quiet_hours"] = None
        elif bad_setting == "quiet_hours_incomplete":
            evidence_record["quiet_hours"] = {"start": "22:00"}
        elif bad_setting == "quiet_hours_invalid_clock":
            evidence_record["quiet_hours"] = {"start": "25:61", "end": "07:00"}
        elif bad_setting == "quiet_hours_equal":
            evidence_record["quiet_hours"] = {"start": "22:00", "end": "22:00"}
        else:
            evidence_record["quiet_hours"] = {
                "start": "22:00", "end": "07:00",
                "unapproved_field": "not-in-runtime-contract",
            }
    with pytest.raises(GateFailure, match=expected_error):
        verify_two_day(first, second, paused)


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
    assert report["authorized_source_edit"]["evidence_sha256"] == "d" * 64
    assert report["owner_local_receipts"]["source_edited_at"] == "2026-11-12T16:00:00+06:00"
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


@pytest.mark.parametrize("defect", [
    "missing_edit", "wrong_owner", "wrong_project", "wrong_document",
    "wrong_old_version", "wrong_new_version", "wrong_case", "missing_hash",
    "bad_hash", "extra_field", "before_first_verified", "after_second_due",
    "unaware_edit_time",
])
def test_day7_gate_rejects_unqualified_document_edit_receipts(defect):
    first, second, paused = valid_pair()
    edit = second["authorized_source_edit"]
    if defect == "missing_edit":
        second.pop("authorized_source_edit")
    elif defect == "wrong_owner":
        edit["owner_id"] = "another-owner"
    elif defect == "wrong_project":
        edit["project_id"] = "another-project"
    elif defect == "wrong_document":
        edit["document_id"] = "doc-unapproved"
    elif defect == "wrong_old_version":
        edit["previous_version_id"] = "unrelated-v1"
    elif defect == "wrong_new_version":
        edit["current_version_id"] = "unrelated-v2"
    elif defect == "wrong_case":
        edit["operator_case_reference"] = "OTHER-CASE"
    elif defect == "missing_hash":
        edit.pop("evidence_sha256")
    elif defect == "bad_hash":
        edit["evidence_sha256"] = "not-a-sha256"
    elif defect == "extra_field":
        edit["raw_document_text"] = "synthetic private content"
    elif defect == "before_first_verified":
        edit["edited_at"] = first["verified_at"]
    elif defect == "after_second_due":
        edit["edited_at"] = second["due_at"]
    else:
        edit["edited_at"] = "2026-11-12T10:00:00"
    with pytest.raises(GateFailure, match="[Aa]uthorized document edit|edited_at"):
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
    second["authorized_source_edit"]["edited_at"] = "2026-10-31T15:00:00+00:00"
    paused["paused_at"] = "2026-11-01T14:00:00+00:00"
    paused["post_pause_observation"]["due_at"] = "2026-11-02T13:00:00+00:00"
    paused["post_pause_observation"]["observed_at"] = "2026-11-02T14:10:00+00:00"
    report = verify_two_day(first, second, paused)
    assert report["scheduled_local_dates"] == ["2026-10-31", "2026-11-01"]
    # A local date is not enough to audit a natural Temporal timer near DST.
    # Every observed due/verification/pause timestamp must retain the IANA offset.
    assert report["owner_local_receipts"] == {
        "day7_due_at": "2026-10-31T08:00:00-04:00",
        "day7_verified_at": "2026-10-31T08:07:00-04:00",
        "day8_due_at": "2026-11-01T08:00:00-05:00",
        "day8_verified_at": "2026-11-01T08:07:00-05:00",
        "source_edited_at": "2026-10-31T11:00:00-04:00",
        "paused_at": "2026-11-01T09:00:00-05:00",
        "post_pause_due_at": "2026-11-02T08:00:00-05:00",
        "post_pause_observed_at": "2026-11-02T09:10:00-05:00",
    }



def test_two_day_gate_rejects_ambiguous_next_due_time_during_dst_fall_back():
    # At 01:30 on 2026-11-01 New York repeats the same civil time with
    # two *different* UTC offsets, so selecting fold=0 would falsely assert a
    # verified Temporal opportunity without the operator resolving the fold.
    first, second, paused = valid_pair()
    for day in (first, second):
        day["timezone"] = "America/New_York"
        day["schedule"] = {"kind": "daily", "hour": 1, "minute": 30, "weekdays": []}
        day["expires_at"] = "2026-11-03T00:00:00+00:00"
    paused["expires_at"] = "2026-11-03T00:00:00+00:00"
    first.update({
        "due_at": "2026-10-30T05:30:00+00:00",
        "prepared_at": "2026-10-30T05:00:00+00:00",
        "verified_at": "2026-10-30T05:37:00+00:00",
    })
    second.update({
        "due_at": "2026-10-31T05:30:00+00:00",
        "prepared_at": "2026-10-31T05:00:00+00:00",
        "verified_at": "2026-10-31T05:37:00+00:00",
    })
    second["authorized_source_edit"]["edited_at"] = "2026-10-30T06:00:00+00:00"
    paused["paused_at"] = "2026-10-31T05:45:00+00:00"
    paused["post_pause_observation"].update({
        "due_at": "2026-11-01T05:30:00+00:00",
        "observed_at": "2026-11-01T07:10:00+00:00",
    })
    with pytest.raises(GateFailure, match="ambiguous"):
        verify_two_day(first, second, paused)


def test_day7_preflight_does_not_invent_post_pause_observation_offset():
    first, second, paused = valid_pair()
    del paused["post_pause_observation"]
    report = verify_two_day(first, second, paused, require_paused_opportunity=False)
    assert report["status"] == "preflight_only"
    assert report["owner_local_receipts"]["day7_due_at"] == "2026-11-12T08:00:00+06:00"
    assert report["owner_local_receipts"]["post_pause_observed_at"] is None


@pytest.mark.parametrize("unexpected", [
    None, "occurrence", "run", "notification",
    "policy_timezone", "policy_schedule", "policy_run_profile",
    "policy_output_language", "policy_quiet_hours", "policy_overlap_policy",
    "policy_catchup_window_seconds",
    "after_pause_run_profile", "after_pause_output_language",
    "after_pause_quiet_hours",
    "revision_prepared_float", "revision_prepared_bool", "revision_prepared_schema",
    "revision_live_float", "revision_live_bool", "revision_live_applied_float",
    "revision_live_goal_bool", "revision_pause_response_float", "revision_pause_response_jump",
])
def test_pause_two_day_verifies_evidence_before_mutating_staging(monkeypatch, tmp_path, unexpected):
    import argparse
    import json
    from scripts import staging_pa10_scheduled_profile as probe

    first, second, _ = valid_pair()
    first_path, second_path, state_path = (tmp_path / p for p in ("first.json", "second.json", "state.json"))
    first_path.write_text(json.dumps(first))
    second_path.write_text(json.dumps(second))
    state_path.write_text(json.dumps({
        "schema_version": 1.0 if unexpected == "revision_prepared_schema" else 1,
        "scenario": "daily_coworker", "release": RELEASE,
        "owner_id": "owner-1", "automation_id": "automation-1",
        "automation_revision": {"revision_prepared_float": 1.9, "revision_prepared_bool": True}.get(unexpected, 1),
        "schedule_applied_revision": 1, "schedule_applied_enabled": True,
        "synthetic_account_label": "stage-day7-synthetic",
        "goal_id": "goal-1", "goal_revision": 1,
        "authorized_document_ids": ["doc-1"], "project_id": "project-1",
        "expires_at": "2026-11-15T02:00:00+00:00",
        **{name: deepcopy(first[name]) for name in (
            "timezone", "schedule", "run_profile", "output_language",
            "quiet_hours", "overlap_policy", "catchup_window_seconds",
        )},
    }))
    live_profile = {name: deepcopy(first[name]) for name in (
        "timezone", "schedule", "run_profile", "output_language",
        "quiet_hours", "overlap_policy", "catchup_window_seconds",
    )}
    if unexpected and unexpected.startswith("policy_"):
        field = unexpected.removeprefix("policy_")
        changed = {
            "timezone": "UTC",
            "schedule": {"kind": "daily", "hour": 9, "minute": 0, "weekdays": []},
            "run_profile": "deadline",
            "output_language": "bn",
            "quiet_hours": {"start": "23:00", "end": "07:00"},
            "overlap_policy": "buffer_one",
            "catchup_window_seconds": 7200,
        }
        live_profile[field] = changed[field]
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
            **live_profile,
            "revision": {"revision_live_float": 1.9, "revision_live_bool": True}.get(unexpected, 1),
            "expires_at": "2026-11-15T02:00:00+00:00",
            "schedule_applied_revision": 1.0 if unexpected == "revision_live_applied_float" else 1,
            "schedule_applied_enabled": True,
        },
        "daily_scope": {"goal_id": "goal-1", "goal_revision": True if unexpected == "revision_live_goal_bool" else 1,
                        "authorized_document_ids": ["doc-1"], "project_id": "project-1"},
    })

    class Response:
        status_code = 200

        def __init__(self, payload=None):
            self.payload = payload

        def json(self):
            if self.payload is not None:
                return self.payload
            policy = deepcopy(live_profile)
            if unexpected and unexpected.startswith("after_pause_"):
                field = unexpected.removeprefix("after_pause_")
                policy[field] = {
                    "run_profile": "deadline",
                    "output_language": "bn",
                    "quiet_hours": {"start": "23:00", "end": "07:00"},
                }[field]
            return {
                "id": "automation-1", "state": "paused",
                "revision": {"revision_pause_response_float": 2.0, "revision_pause_response_jump": 3}.get(unexpected, 2),
                "schedule_applied_revision": {"revision_pause_response_float": 2.0, "revision_pause_response_jump": 3}.get(unexpected, 2),
                "schedule_applied_enabled": False,
                "schedule_error_code": None, **policy,
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
            if path == "/api/v1/automations/automation-1":
                return Response()
            if path == "/api/v1/automations/automation-1/history":
                history = [
                    {"occurrence_id": "occ-12", "run_id": "run-12"},
                    {"occurrence_id": "occ-13", "run_id": "run-13"},
                ]
                if unexpected == "occurrence":
                    history.append({"occurrence_id": "occ-unexpected", "run_id": "run-unexpected"})
                if unexpected == "run":
                    history.append({"occurrence_id": "occ-13", "run_id": "run-unexpected"})
                return Response({"history": history})
            if path == "/api/v1/notifications":
                notices = [
                    {"id": "completed-12", "automation_id": "automation-1"},
                    {"id": "completed-13", "automation_id": "automation-1"},
                ]
                if unexpected == "notification":
                    notices.append({"id": "completed-unexpected", "automation_id": "automation-1"})
                return Response({"notifications": notices})
            raise AssertionError(f"Unexpected request: {path}")

    client = Client()
    monkeypatch.setattr(probe.httpx, "Client", lambda **_args: client)
    if unexpected and unexpected.startswith("revision_"):
        with pytest.raises(probe.ScheduledProfileProbeFailure, match="[Rr]evision|schema"):
            probe.pause_two_day(args)
        expected_posts = [("/api/v1/automations/automation-1/pause", {"expected_revision": 1})] if unexpected.startswith("revision_pause_response_") else []
        assert client.posts == expected_posts
        assert not args.output.exists()
        return
    if unexpected and unexpected.startswith("policy_"):
        with pytest.raises(probe.ScheduledProfileProbeFailure, match="prepared|drift"):
            probe.pause_two_day(args)
        assert client.posts == []  # policy drift must block before pause mutation
        assert not args.output.exists()
        return
    if unexpected and unexpected.startswith("after_pause_"):
        with pytest.raises(probe.ScheduledProfileProbeFailure, match="prepared|drift"):
            probe.pause_two_day(args)
        assert client.posts == [(
            "/api/v1/automations/automation-1/pause", {"expected_revision": 1},
        )]
        assert not args.output.exists()  # never certify drifted applied-pause
        return
    if unexpected:
        with pytest.raises(probe.ScheduledProfileProbeFailure, match="Pause baseline"):
            probe.pause_two_day(args)
        assert client.posts == [(
            "/api/v1/automations/automation-1/pause", {"expected_revision": 1},
        )]
        assert not args.output.exists()
        return
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
    assert parsed.source_edit_receipt is None

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



@pytest.mark.parametrize(("baseline_field", "extra_id"), [
    ("pause_baseline_occurrence_ids", "occ-unexpected"),
    ("pause_baseline_run_ids", "run-unexpected"),
    ("pause_baseline_notification_ids", "completed-unexpected"),
])
def test_two_day_gate_rejects_unexpected_pause_baseline_activity(
    baseline_field, extra_id,
):
    # The synthetic profile begins with Day 7's first occurrence. Any extra
    # occurrence, execution or notice already stored by the pause readback
    # cannot silently become an approved baseline for the zero-admission gate.
    first, second, paused = valid_pair()
    paused[baseline_field].append(extra_id)
    with pytest.raises(GateFailure, match="baseline"):
        verify_two_day(first, second, paused)



def test_two_day_gate_does_not_qualify_pause_acknowledgement_alone():
    first, second, paused = valid_pair()
    del paused["post_pause_observation"]
    with pytest.raises(GateFailure, match="Post-pause"):
        verify_two_day(first, second, paused)


@pytest.mark.parametrize("defect", [
    "due_earlier", "observed_too_early", "future_observation", "new_occurrence",
    "new_run", "new_notification", "resumed", "wrong_applied_revision",
    "wrong_case", "missing_history_baseline", "removed_first_occurrence",
    "wrong_overlap", "missing_catchup_bound", "pause_after_opportunity",
    "expiry_before_opportunity", "expiry_inside_catchup",
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
    elif defect == "expiry_inside_catchup":
        for item in (first, second, paused):
            item["expires_at"] = "2026-11-14T02:30:00+00:00"
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)


@pytest.mark.parametrize("policy_drift", [
    None, "run_profile", "output_language", "quiet_hours",
])
def test_read_only_paused_opportunity_collector_proves_zero_or_rejects_new_activity(
    monkeypatch, tmp_path, policy_drift,
):
    import argparse
    import json
    from scripts import staging_day7_paused_opportunity as check

    first, second, paused = valid_pair()
    del paused["post_pause_observation"]
    paths = [tmp_path / name for name in ("first.json", "second.json", "pause.json")]
    for path, value in zip(paths, (first, second, paused)):
        path.write_text(json.dumps(value), encoding="utf-8")
    args = argparse.Namespace(
        first_evidence=paths[0], second_evidence=paths[1], pause_evidence=paths[2],
        rollout=tmp_path / "rollout.json", provider_policy_plan=tmp_path / "policy.json",
        operator_case_reference="CASE-7", output=tmp_path / "observed.json",
    )
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL", "stage-day7-synthetic")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://staging.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "not-a-real-token")
    monkeypatch.setattr(check, "release_identity", lambda *_args: deepcopy(RELEASE))

    history = [
        {"occurrence_id": "occ-12", "run_id": "run-12"},
        {"occurrence_id": "occ-13", "run_id": "run-13"},
    ]
    notices = [
        {"id": "completed-12", "automation_id": "automation-1"},
        {"id": "completed-13", "automation_id": "automation-1"},
    ]
    paths_read = []
    live_profile = {name: deepcopy(first[name]) for name in (
        "timezone", "schedule", "run_profile", "output_language",
        "quiet_hours", "overlap_policy", "catchup_window_seconds",
    )}
    if policy_drift:
        changed = {
            "run_profile": "deadline",
            "output_language": "bn",
            "quiet_hours": {"start": "23:00", "end": "07:00"},
        }
        live_profile[policy_drift] = changed[policy_drift]

    class Response:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, path, **_kwargs):
            paths_read.append(path)
            if path == "/api/v1/me":
                return Response({"account_id": "owner-1"})
            if path == "/api/v1/automations/automation-1":
                return Response({
                    "id": "automation-1", "state": "paused", "revision": 2,
                    "schedule_applied_revision": 2, "schedule_applied_enabled": False,
                    "schedule_error_code": None, **live_profile,
                    "expires_at": first["expires_at"], "goal_id": first["goal_id"],
                    "goal_revision": first["goal_revision"],
                })
            if path == "/api/v1/automations/automation-1/history":
                return Response({"history": history})
            if path == "/api/v1/notifications":
                return Response({"notifications": notices})
            raise AssertionError(f"Unexpected network operation: {path}")

        def post(self, *_args, **_kwargs):
            raise AssertionError("The post-pause observer must be read-only.")

    monkeypatch.setattr(check.httpx, "Client", lambda **_kwargs: Client())
    import os
    import stat

    # Exercise the real paused-opportunity collector with the normal 022
    # operator umask: sensitive owner/run/notification evidence must be 0600.
    previous_umask = os.umask(0o022)
    try:
        if policy_drift:
            with pytest.raises(check.ScheduledProfileProbeFailure, match="prepared|drift"):
                check.collect_paused_opportunity(args)
            assert not args.output.exists()
            assert paths_read == ["/api/v1/me", "/api/v1/automations/automation-1"]
            return
        qualified = check.collect_paused_opportunity(args)
    finally:
        os.umask(previous_umask)
    if os.name == "posix":
        assert stat.S_IMODE(args.output.stat().st_mode) == 0o600
    observation = qualified["post_pause_observation"]
    assert observation["new_occurrence_count"] == 0
    assert observation["new_run_count"] == 0
    assert observation["new_notification_count"] == 0
    assert observation["due_at"] == "2026-11-14T02:00:00+00:00"
    assert json.loads(args.output.read_text()) == qualified
    assert paths_read == [
        "/api/v1/me", "/api/v1/automations/automation-1",
        "/api/v1/automations/automation-1/history", "/api/v1/notifications",
    ]

    # A later accepted run and a third notice must never certify a quiet pause.
    history.append({"occurrence_id": "occ-14", "run_id": "run-14"})
    notices.append({"id": "completed-14", "automation_id": "automation-1"})
    args.output = tmp_path / "must-not-exist.json"
    with pytest.raises(check.ScheduledProfileProbeFailure, match="did not qualify"):
        check.collect_paused_opportunity(args)
    assert not args.output.exists()


def test_paused_opportunity_collector_refuses_early_read_before_network(
    monkeypatch, tmp_path,
):
    import argparse
    import json
    from scripts import staging_day7_paused_opportunity as check

    first, second, paused = valid_pair()
    del paused["post_pause_observation"]
    # The source pair passes offline preflight, but the controlled read-only
    # observer's local clock is still inside the following catch-up window.
    class EarlyObservationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 14, 2, 5, tzinfo=timezone.utc)

    monkeypatch.setattr(check, "datetime", EarlyObservationClock)
    files = [tmp_path / name for name in ("first.json", "second.json", "pause.json")]
    for path, item in zip(files, (first, second, paused)):
        path.write_text(json.dumps(item), encoding="utf-8")
    args = argparse.Namespace(
        first_evidence=files[0], second_evidence=files[1], pause_evidence=files[2],
        operator_case_reference="CASE-7", output=tmp_path / "never.json",
        rollout=tmp_path / "rollout.json", provider_policy_plan=tmp_path / "policy.json",
    )
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setattr(check.httpx, "Client", lambda **_kw: (_ for _ in ()).throw(
        AssertionError("No network access allowed before the due opportunity")
    ))
    with pytest.raises(check.ScheduledProfileProbeFailure, match="full catch-up window"):
        check.collect_paused_opportunity(args)
    assert not args.output.exists()


# Day 7 operator evidence includes owner/run/document identities. Exercise the
# actual CLI, not a monkeypatched output helper, so the file mode and symlink
# behavior cannot be bypassed by a different writer in main().
def _run_day7_gate_cli(monkeypatch, tmp_path, output):
    import json
    import sys
    from scripts import staging_day7_two_day_gate as gate

    first, second, paused = valid_pair()
    paths = [tmp_path / name for name in ("first.json", "second.json", "pause.json")]
    for path, payload in zip(paths, (first, second, paused)):
        path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "staging_day7_two_day_gate", "--first", str(paths[0]),
        "--second", str(paths[1]), "--pause", str(paths[2]),
        "--output", str(output),
    ])
    gate.main()


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX file mode contract")
def test_day7_cli_creates_private_operator_report_with_umask_022(monkeypatch, tmp_path):
    import os
    import stat
    import json

    output = tmp_path / "private-day7.json"
    previous = os.umask(0o022)
    try:
        _run_day7_gate_cli(monkeypatch, tmp_path, output)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["owner_id"] == "owner-1"


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX file mode contract")
def test_day7_cli_restricts_existing_world_readable_operator_report(monkeypatch, tmp_path):
    import os
    import stat

    output = tmp_path / "private-day7.json"
    output.write_text("old-private-operator-evidence", encoding="utf-8")
    output.chmod(0o644)
    previous = os.umask(0o022)
    try:
        _run_day7_gate_cli(monkeypatch, tmp_path, output)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert "old-private-operator-evidence" not in output.read_text(encoding="utf-8")


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX symlink contract")
def test_day7_cli_never_follows_output_symlink_into_another_file(monkeypatch, tmp_path):
    import stat

    target = tmp_path / "unrelated-private-target.json"
    target.write_text("DO NOT OVERWRITE", encoding="utf-8")
    output = tmp_path / "private-day7.json"
    output.symlink_to(target)
    _run_day7_gate_cli(monkeypatch, tmp_path, output)
    assert target.read_text(encoding="utf-8") == "DO NOT OVERWRITE"
    assert not output.is_symlink()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX file replacement contract")
def test_day7_cli_failed_atomic_commit_preserves_previous_report(monkeypatch, tmp_path):
    import os

    output = tmp_path / "private-day7.json"
    output.write_text("verified-original-report", encoding="utf-8")
    output.chmod(0o600)
    def deny_replace(*_args, **_kwargs):
        raise OSError("simulated output replacement failure")
    monkeypatch.setattr(os, "replace", deny_replace)
    with pytest.raises(SystemExit) as exc:
        _run_day7_gate_cli(monkeypatch, tmp_path, output)
    assert exc.value.code == 1
    assert output.read_text(encoding="utf-8") == "verified-original-report"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "first.json", "pause.json", "private-day7.json", "second.json",
    ]


@pytest.mark.parametrize("day_index", [0, 1])
@pytest.mark.parametrize(("field", "bad_value"), [
    ("new_occurrence_count", None),
    ("new_occurrence_count", 0),
    ("new_occurrence_count", 2),
    ("new_occurrence_count", True),
    ("new_occurrence_count", "1"),
    ("new_run_count", None),
    ("new_run_count", 0),
    ("new_run_count", 2),
    ("new_run_count", True),
    ("new_run_count", "1"),
])
def test_day7_gate_refuses_missing_or_invalid_daily_occurrence_and_run_counts(
    day_index, field, bad_value,
):
    """One receipt ID cannot conceal zero or duplicate admitted work."""
    first, second, paused = valid_pair()
    day = (first, second)[day_index]
    if bad_value is None:
        day.pop(field)
    else:
        day[field] = bad_value
    with pytest.raises(GateFailure, match="one new occurrence|one new run"):
        verify_two_day(first, second, paused)


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX symlink and file mode contract")
def test_paused_opportunity_private_writer_does_not_follow_existing_output_link(tmp_path):
    import stat
    from scripts import staging_day7_paused_opportunity as check

    sensitive_target = tmp_path / "must-remain-unchanged.txt"
    sensitive_target.write_text("original-sensitive-record", encoding="utf-8")
    output = tmp_path / "paused-observation.json"
    output.symlink_to(sensitive_target)

    check.write_private_paused_evidence(output, {
        "owner_id": "synthetic-owner", "automation_id": "synthetic-automation",
    })

    assert sensitive_target.read_text(encoding="utf-8") == "original-sensitive-record"
    assert not output.is_symlink()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_text(encoding="utf-8").find("synthetic-owner") >= 0


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX file mode contract")
def test_paused_opportunity_private_writer_restricts_existing_world_readable_file(tmp_path):
    import stat
    from scripts import staging_day7_paused_opportunity as check

    output = tmp_path / "paused-observation.json"
    output.write_text("obsolete-evidence", encoding="utf-8")
    output.chmod(0o644)
    check.write_private_paused_evidence(output, {
        "owner_id": "synthetic-owner", "automation_id": "synthetic-automation",
    })

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert "synthetic-owner" in output.read_text(encoding="utf-8")
    assert "obsolete-evidence" not in output.read_text(encoding="utf-8")


def test_paused_opportunity_private_writer_failed_replace_retains_original_and_hides_paths(
    monkeypatch, tmp_path,
):
    import os
    from scripts import staging_day7_paused_opportunity as check

    output = tmp_path / "private-operator-secret-path.json"
    output.write_text("previous-good-evidence", encoding="utf-8")

    def failed_replace(*_args, **_kwargs):
        raise OSError("sensitive-exception-token")

    monkeypatch.setattr(os, "replace", failed_replace)
    with pytest.raises(check.ScheduledProfileProbeFailure,
                       match="private paused-opportunity evidence") as exc:
        check.write_private_paused_evidence(output, {"owner_id": "synthetic-owner"})
    assert "sensitive-exception-token" not in str(exc.value)
    assert "private-operator-secret-path" not in str(exc.value)
    assert output.read_text(encoding="utf-8") == "previous-good-evidence"
    assert sorted(path.name for path in tmp_path.iterdir()) == [output.name]


@pytest.mark.parametrize("catchup", [60, 3599, 3601, 7200, True, 3600.0, "3600"])
def test_day7_gate_requires_exact_approved_catchup_window(catchup):
    first, second, paused = valid_pair()
    for item in (first, second):
        item["catchup_window_seconds"] = catchup
    # Even a sufficiently late observation must not qualify the wrong policy.
    paused["post_pause_observation"]["observed_at"] = "2026-11-14T05:10:00+00:00"
    with pytest.raises(GateFailure, match="3600"):
        verify_two_day(first, second, paused)
    with pytest.raises(GateFailure, match="3600"):
        verify_two_day(first, second, paused, require_paused_opportunity=False)


@pytest.mark.parametrize("day_index", [0, 1])
def test_day7_gate_rejects_fractional_due_instant(day_index):
    first, second, paused = valid_pair()
    day = (first, second)[day_index]
    day["due_at"] = day["due_at"].replace(":00+00:00", ":00.000001+00:00")
    with pytest.raises(GateFailure, match="owner-approved local schedule time"):
        verify_two_day(first, second, paused)


def test_day7_paused_opportunity_requires_exact_approved_catchup_window():
    from scripts.staging_day7_two_day_gate import next_paused_opportunity

    first, second, _ = valid_pair()
    first["catchup_window_seconds"] = 60
    with pytest.raises(GateFailure, match="3600"):
        next_paused_opportunity(first, second)


@pytest.mark.parametrize("field", ["hour", "minute", "catchup_window_seconds"])
def test_two_day_gate_rejects_numeric_type_drift_in_second_receipt(field):
    first, second, paused = valid_pair()
    # Python considers 8 == 8.0; identical values do not establish schema validity.
    target = second if field == "catchup_window_seconds" else second["schedule"]
    target[field] = float(target[field])
    with pytest.raises(GateFailure, match="calendar time|3600"):
        verify_two_day(first, second, paused)


@pytest.mark.parametrize(("receipt", "field", "value"), [
    ("first", "schema_version", 2.0),
    ("second", "schema_version", 2.0),
    ("first", "schedule_applied_revision", True),
    ("first", "schedule_applied_revision", 1.0),
    ("second", "schedule_applied_revision", True),
    ("second", "schedule_applied_revision", 1.0),
    ("second", "goal_revision", True),
    ("second", "goal_revision", 1.0),
    ("pause", "goal_revision", True),
    ("pause", "goal_revision", 1.0),
    ("pause", "schedule_applied_revision", 2.0),
    ("observation", "schedule_applied_revision", 2.0),
])
def test_two_day_gate_rejects_equal_but_noninteger_receipt_revision(receipt, field, value):
    first, second, paused = valid_pair()
    target = {
        "first": first, "second": second, "pause": paused,
        "observation": paused["post_pause_observation"],
    }[receipt]
    target[field] = value
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused)
    if receipt != "observation":
        with pytest.raises(GateFailure):
            verify_two_day(first, second, paused, require_paused_opportunity=False)


@pytest.mark.parametrize("day_index", [0, 1])
@pytest.mark.parametrize("field", ["occurrence_id", "run_id", "completion_notification_id"])
@pytest.mark.parametrize("invalid", [True, 123, ["id"], " ", " padded-id ", "id\n"])
def test_two_day_preflight_rejects_noncanonical_admission_and_delivery_ids(day_index, field, invalid):
    first, second, paused = valid_pair()
    (first, second)[day_index][field] = invalid
    # This path guards the staging pause POST, before baseline identity lists
    # exist. A truthy non-string or a whitespace alias is not a durable ID.
    with pytest.raises(GateFailure):
        verify_two_day(first, second, paused, require_paused_opportunity=False)



def test_two_day_gate_rejects_skipped_pause_revision():
    first, second, paused = valid_pair()
    # A pause advances the exact accepted revision once; a later matching
    # applied revision could instead be an unrelated owner edit.
    paused["paused_revision"] = paused["schedule_applied_revision"] = 3
    paused["post_pause_observation"]["schedule_applied_revision"] = 3
    with pytest.raises(GateFailure, match="Pause must follow"):
        verify_two_day(first, second, paused)
    with pytest.raises(GateFailure, match="Pause must follow"):
        verify_two_day(first, second, paused, require_paused_opportunity=False)
