from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.cohort_post_scale_observation import (
    PostScaleObservationError,
    activation_epoch,
    evaluate_observation,
)
from scripts.cohort_release_ledger import (
    append_event,
    append_scale_event,
    file_sha256,
)


KEY = b"k" * 32
NOW = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def plan():
    return {
        "release_id": "coworker-cohort-001",
        "max_gap_minutes": 10,
        "stale_after_minutes": 10,
        "min_enrollment_ratio": 0.75,
        "min_healthy_windows": 3,
        "min_observation_minutes": 10,
        "min_task_samples": 6,
        "min_provider_samples": 6,
        "min_agent_samples": 3,
        "min_research_samples": 0,
        "min_action_samples": 0,
    }


def activation():
    return {
        "schema_version": 1,
        "status": "bounded_expansion_verified",
        "release_id": "coworker-cohort-001",
        "verified_at": "2026-09-22T13:00:00+00:00",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
        "current_max_users": 25,
        "proposed_max_users": 40,
        "configured_members": 30,
        "configured_max_users": 40,
        "change_reference": "change-42",
        "deployment_deployed_at": "2026-09-22T12:50:00+00:00",
        "operator_status_generated_at": "2026-09-22T12:55:00+00:00",
        "artifact_sha256": {
            "scale_decision": "a" * 64,
            "deployment_change": "b" * 64,
            "operator_status": "c" * 64,
        },
    }


def row(at, *, members=30, decision="CONTINUE_COHORT", tasks=2, providers=2, agents=1):
    return {
        "decision": decision,
        "release_id": "coworker-cohort-001",
        "snapshot": {
            "generated_at": at.isoformat(),
            "cohort_members_configured": members,
            "tasks": {"samples": tasks},
            "provider": {"samples": providers},
            "agents": {"samples": agents},
            "research": {"samples": 0},
            "actions": {"samples": 0},
        },
        "breaches": [],
        "rollback": None,
    }


def history():
    start = datetime(2026, 9, 22, 13, 5, tzinfo=timezone.utc)
    return [row(start + timedelta(minutes=5 * index)) for index in range(3)]


def build_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    ledger = tmp_path / "ledger.jsonl"

    rollout = write_json(tmp_path / "rollout.json", {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    })
    canary_plan = write_json(tmp_path / "canary-plan.json", {
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "cohort-25"}],
    })
    progression = write_json(tmp_path / "progression.json", {
        "release_id": "coworker-cohort-001",
        "decision": "HOLD",
        "current_stage": "cohort-25",
        "next_stage": None,
    })
    status = write_json(tmp_path / "status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="hold",
        actor_reference="oncall",
        change_reference="change-25",
        current_stage="cohort-25",
        next_stage=None,
        rollout=rollout,
        canary_plan=canary_plan,
        progression_decision=progression,
        operator_status=status,
        created_at="2026-09-22T12:00:00+00:00",
    )

    scale_decision = write_json(tmp_path / "scale-decision.json", {
        "decision": "ELIGIBLE_FOR_BOUNDED_EXPANSION",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "current_max_users": 25,
        "proposed_stage": "cohort-40",
        "proposed_max_users": 40,
        "failures": [],
        "generated_at": "2026-09-22T12:30:00+00:00",
        "references": {"change_reference": "change-42"},
    })
    deployment = write_json(tmp_path / "deployment.json", {
        "release_id": "coworker-cohort-001",
        "change_reference": "change-42",
        "deployed_at": "2026-09-22T12:50:00+00:00",
        "stage": "cohort-40",
        "max_users": 40,
    })
    post_status = write_json(tmp_path / "post-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T12:55:00+00:00",
        "breaches": [],
    })
    activation_path = write_json(tmp_path / "activation.json", activation())
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["artifact_sha256"] = {
        "scale_decision": file_sha256(scale_decision),
        "deployment_change": file_sha256(deployment),
        "operator_status": file_sha256(post_status),
    }
    activation_path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

    append_scale_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="change-42",
        current_stage="cohort-25",
        next_stage="cohort-40",
        scale_decision=scale_decision,
        deployment_change=deployment,
        operator_status=post_status,
        scale_activation=activation_path,
        created_at="2026-09-22T13:02:00+00:00",
    )
    return ledger, activation_path


def test_post_scale_health_becomes_eligible_for_requalification():
    result = evaluate_observation(
        history(),
        activation(),
        plan(),
        epoch_start=datetime(2026, 9, 22, 13, 2, tzinfo=timezone.utc),
        now=datetime(2026, 9, 22, 13, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "ELIGIBLE_FOR_REQUALIFICATION"
    assert result["current_stage"] == "cohort-40"
    assert result["stage_max_users"] == 40
    assert result["reasons"] == []


def test_pre_activation_stop_does_not_poison_new_scale_epoch():
    rows = [
        row(datetime(2026, 9, 22, 12, 55, tzinfo=timezone.utc), decision="STOP_ROLLOUT"),
        *history(),
    ]
    result = evaluate_observation(
        rows,
        activation(),
        plan(),
        epoch_start=datetime(2026, 9, 22, 13, 2, tzinfo=timezone.utc),
        now=datetime(2026, 9, 22, 13, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "ELIGIBLE_FOR_REQUALIFICATION"


def test_post_scale_stop_fails_closed():
    rows = history()
    rows[1]["decision"] = "STOP_ROLLOUT"
    result = evaluate_observation(
        rows,
        activation(),
        plan(),
        epoch_start=datetime(2026, 9, 22, 13, 2, tzinfo=timezone.utc),
        now=datetime(2026, 9, 22, 13, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["post_scale_health_contains_stop"]


def test_post_scale_membership_overflow_stops_rollout():
    rows = history()
    rows[-1]["snapshot"]["cohort_members_configured"] = 41
    result = evaluate_observation(
        rows,
        activation(),
        plan(),
        epoch_start=datetime(2026, 9, 22, 13, 2, tzinfo=timezone.utc),
        now=datetime(2026, 9, 22, 13, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["configured_members_exceed_reviewed_stage"]


def test_post_scale_requires_meaningful_enrollment():
    rows = [row(item["snapshot"]["generated_at"] if isinstance(item["snapshot"]["generated_at"], datetime) else datetime.fromisoformat(item["snapshot"]["generated_at"]), members=29) for item in history()]
    result = evaluate_observation(
        rows,
        activation(),
        plan(),
        epoch_start=datetime(2026, 9, 22, 13, 2, tzinfo=timezone.utc),
        now=datetime(2026, 9, 22, 13, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert result["reasons"] == ["stage_not_sufficiently_enrolled"]


def test_activation_epoch_requires_ledger_binding(monkeypatch, tmp_path):
    ledger, activation_path = build_ledger(tmp_path, monkeypatch)
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    epoch = activation_epoch(activation_path, ledger, activation=value)
    assert epoch == datetime(2026, 9, 22, 13, 2, tzinfo=timezone.utc)


def test_unledgered_activation_cannot_create_epoch(monkeypatch, tmp_path):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    activation_path = write_json(tmp_path / "activation.json", activation())
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    with pytest.raises(PostScaleObservationError, match="Release ledger"):
        activation_epoch(activation_path, ledger, activation=activation())
