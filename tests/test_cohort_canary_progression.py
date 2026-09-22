from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.cohort_canary_progression import evaluate_progression, load_recovery_epoch
from scripts.cohort_release_ledger import (
    append_event,
    append_recovery_event,
    append_rollback_event,
    file_sha256,
)


def rollout():
    return {
        "release_id": "coworker-cohort-001",
        "cohort": {"reference": "ticket", "max_users": 25},
        "rollback": {"global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false"},
    }


def plan():
    return {
        "release_id": "coworker-cohort-001",
        "max_gap_minutes": 10,
        "stale_after_minutes": 10,
        "stages": [
            {
                "name": "canary-5",
                "min_members": 5,
                "max_users": 5,
                "min_healthy_windows": 3,
                "min_observation_minutes": 10,
                "min_task_samples": 6,
                "min_provider_samples": 6,
                "min_agent_samples": 3,
                "min_research_samples": 0,
                "min_action_samples": 0,
            },
            {
                "name": "canary-10",
                "min_members": 10,
                "max_users": 10,
                "min_healthy_windows": 3,
                "min_observation_minutes": 10,
                "min_task_samples": 12,
                "min_provider_samples": 12,
                "min_agent_samples": 6,
                "min_research_samples": 0,
                "min_action_samples": 0,
            },
        ],
    }


def row(at: datetime, *, members=5, decision="CONTINUE_COHORT", task_samples=2, provider_samples=2, agent_samples=1):
    return {
        "decision": decision,
        "release_id": "coworker-cohort-001",
        "snapshot": {
            "generated_at": at.isoformat(),
            "cohort_members_configured": members,
            "tasks": {"samples": task_samples},
            "provider": {"samples": provider_samples},
            "agents": {"samples": agent_samples},
            "research": {"samples": 0},
            "actions": {"samples": 0},
        },
        "breaches": [],
        "rollback": None,
    }


def healthy_history():
    start = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    return [row(start + timedelta(minutes=5 * index)) for index in range(3)]


def test_sustained_healthy_stage_becomes_eligible_for_expansion():
    history = healthy_history()
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "ELIGIBLE_FOR_EXPANSION"
    assert result["next_stage"] == "canary-10"
    assert result["reasons"] == []


def test_any_stop_window_stops_rollout():
    history = healthy_history()
    history[1]["decision"] = "STOP_ROLLOUT"
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert "health_history_contains_stop" in result["reasons"]


def test_stale_latest_snapshot_stops_rollout():
    result = evaluate_progression(
        healthy_history(),
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 30, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["latest_health_snapshot_stale"]


def test_monitoring_gap_holds_stage():
    history = healthy_history()
    history[2]["snapshot"]["generated_at"] = datetime(2026, 9, 22, 4, 25, tzinfo=timezone.utc).isoformat()
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 27, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert "monitoring_gap" in result["reasons"]


def test_insufficient_real_samples_hold_stage():
    history = healthy_history()
    for item in history:
        item["snapshot"]["tasks"]["samples"] = 0
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert "insufficient_task_samples" in result["reasons"]


def test_stage_member_limit_is_hard_stop():
    history = [row(datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc), members=6)]
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 2, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["configured_members_exceed_current_stage"]


def test_final_stage_never_auto_expands():
    value = plan()
    history = []
    start = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    for index in range(3):
        history.append(row(start + timedelta(minutes=5 * index), members=10, task_samples=4, provider_samples=4, agent_samples=2))
    result = evaluate_progression(
        history,
        rollout(),
        value,
        current_stage="canary-10",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert result["next_stage"] is None
    assert result["reasons"] == ["final_stage_reached"]


def test_latest_membership_drop_holds_even_after_earlier_healthy_windows():
    history = healthy_history()
    history.append(row(datetime(2026, 9, 22, 4, 15, tzinfo=timezone.utc), members=4))
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert result["reasons"] == ["stage_not_fully_enrolled"]


def test_stop_before_full_enrollment_still_stops_release():
    start = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    history = [
        row(start, members=4, decision="STOP_ROLLOUT"),
        row(start + timedelta(minutes=5), members=5),
        row(start + timedelta(minutes=10), members=5),
        row(start + timedelta(minutes=15), members=5),
    ]
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["health_history_contains_stop"]


KEY = b"k" * 32


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def recovery_epoch_files(tmp_path):
    rollout_path = write_json(tmp_path / "rollout.json", {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    })
    plan_path = write_json(tmp_path / "plan.json", {
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "canary-5"}, {"name": "canary-10"}],
    })
    progression = write_json(tmp_path / "stop.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
        "current_stage": "canary-5",
        "next_stage": None,
    })
    stop_status = write_json(tmp_path / "stop-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
    })
    rollback_status = write_json(tmp_path / "rollback-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    rollback_completion = write_json(tmp_path / "rollback-completion.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout_path),
            "operator_status": file_sha256(rollback_status),
        },
    })
    recovery_status = write_json(tmp_path / "recovery-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    recovery_verification = write_json(tmp_path / "recovery.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "recovery_verified",
        "current_stage": "canary-5",
        "verified_at": "2026-09-22T05:00:00+00:00",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout_path),
            "canary_plan": file_sha256(plan_path),
            "rollback_completion": file_sha256(rollback_completion),
            "operator_status": file_sha256(recovery_status),
        },
    })
    return (
        rollout_path,
        plan_path,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    )


def build_recovery_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    (
        rollout_path,
        plan_path,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    ) = recovery_epoch_files(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-1",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=stop_status,
        created_at="2026-09-22T04:50:00+00:00",
    )
    append_rollback_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-1",
        current_stage="canary-5",
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=rollback_status,
        rollback_completion=rollback_completion,
        created_at="2026-09-22T04:58:00+00:00",
    )
    append_recovery_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-1",
        current_stage="canary-5",
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=recovery_status,
        rollback_completion=rollback_completion,
        recovery_verification=recovery_verification,
        created_at="2026-09-22T05:00:00+00:00",
    )
    return ledger, recovery_verification


def test_post_recovery_epoch_excludes_historical_stop(monkeypatch, tmp_path):
    ledger, recovery_verification = build_recovery_ledger(tmp_path, monkeypatch)
    epoch = load_recovery_epoch(
        recovery_verification,
        ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
    )
    history = [
        row(datetime(2026, 9, 22, 4, 55, tzinfo=timezone.utc), decision="STOP_ROLLOUT"),
        row(datetime(2026, 9, 22, 5, 5, tzinfo=timezone.utc)),
        row(datetime(2026, 9, 22, 5, 10, tzinfo=timezone.utc)),
        row(datetime(2026, 9, 22, 5, 15, tzinfo=timezone.utc)),
    ]
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 5, 17, tzinfo=timezone.utc),
        epoch_start=epoch,
    )
    assert result["decision"] == "ELIGIBLE_FOR_EXPANSION"
    assert result["reasons"] == []


def test_recovery_epoch_requires_fresh_post_recovery_health(monkeypatch, tmp_path):
    ledger, recovery_verification = build_recovery_ledger(tmp_path, monkeypatch)
    epoch = load_recovery_epoch(
        recovery_verification,
        ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
    )
    result = evaluate_progression(
        [row(datetime(2026, 9, 22, 4, 55, tzinfo=timezone.utc), decision="STOP_ROLLOUT")],
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 5, 2, tzinfo=timezone.utc),
        epoch_start=epoch,
    )
    assert result["decision"] == "HOLD"
    assert result["reasons"] == ["no_post_recovery_health"]


def test_unledgered_recovery_cannot_create_progression_epoch(monkeypatch, tmp_path):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    *_files, recovery_verification = recovery_epoch_files(tmp_path)
    ledger = tmp_path / "empty-ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    with pytest.raises(Exception, match="ledger"):
        load_recovery_epoch(
            recovery_verification,
            ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
        )


def test_recovery_epoch_starts_after_ledger_entry_not_only_artifact(monkeypatch, tmp_path):
    ledger, recovery_verification = build_recovery_ledger(tmp_path, monkeypatch)
    entries = ledger.read_text(encoding="utf-8").splitlines()
    last = json.loads(entries[-1])
    last["created_at"] = "2026-09-22T05:02:00+00:00"
    from scripts.cohort_release_ledger import entry_core, sign_entry
    last["entry_hash"], last["hmac_sha256"] = sign_entry(entry_core(last), KEY)
    entries[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
    ledger.write_text("\n".join(entries) + "\n", encoding="utf-8")

    epoch = load_recovery_epoch(
        recovery_verification,
        ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
    )
    assert epoch == datetime(2026, 9, 22, 5, 2, tzinfo=timezone.utc)
