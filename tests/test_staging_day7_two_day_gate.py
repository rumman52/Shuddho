from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.staging_day7_two_day_gate import GateFailure, verify_two_day


RELEASE = {"release_id": "test-release", "source_revision": "a" * 40,
           "environment": "staging", "deployment_reference": "deploy-123",
           "rollout_manifest_sha256": "b" * 64, "provider_policy_sha256": "c" * 64}


def evidence(day: int, version: str) -> dict:
    due = f"2026-11-{day:02d}T02:00:00+00:00"
    return {
        "schema_version": 1, "evidence_kind": "pa10_scheduled_profile",
        "scenario": "daily_coworker", "status": "passed", "release": deepcopy(RELEASE),
        "synthetic_account_label": "stage-day7-synthetic", "owner_id": "owner-1",
        "automation_id": "automation-1", "automation_revision": 1,
        "timezone": "Asia/Dhaka", "schedule": {"kind": "daily", "hour": 8, "minute": 0, "weekdays": []},
        "run_profile": "briefing", "output_language": "en", "quiet_hours": {"start": "22:00", "end": "07:00"},
        "prepared_at": f"2026-11-{day:02d}T01:30:00+00:00",
        "verified_at": f"2026-11-{day:02d}T02:07:00+00:00",
        "occurrence_id": f"occ-{day}", "due_at": due, "run_id": f"run-{day}",
        "run_state": "completed", "started_notification_id": f"started-{day}",
        "completion_notification_id": f"completed-{day}", "new_notification_count": 2,
        "input_version_ids": [version], "document_ids": ["doc-1"],
        "operator_case_reference": "CASE-7",
    }


def pause_evidence() -> dict:
    return {"status": "paused", "release": deepcopy(RELEASE), "owner_id": "owner-1",
            "synthetic_account_label": "stage-day7-synthetic",
            "automation_id": "automation-1", "previous_revision": 1, "paused_revision": 2,
            "paused_at": "2026-11-13T02:10:00+00:00",
            "operator_case_reference": "CASE-7"}


def valid_pair():
    first, second = evidence(12, "v1"), evidence(13, "v2")
    second["prior_run_input_version_ids"] = ["v1"]
    return first, second, pause_evidence()


def test_two_day_gate_accepts_unchanged_scope_fresh_pins_and_pause():
    first, second, paused = valid_pair()
    report = verify_two_day(first, second, paused)
    assert report["status"] == "passed"
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
        "owner_id": "owner-1", "automation": {"revision": 1},
    })

    class Response:
        status_code = 200

        def json(self):
            return {"id": "automation-1", "state": "paused", "revision": 2}

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