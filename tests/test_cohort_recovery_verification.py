from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for recovery verification tests")

from scripts import cohort_recovery_verification as recovery


def rollout():
    return {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
        "capabilities": {
            "coworker": True,
            "work_services": True,
            "artifact_services": True,
            "agent_runtime": True,
            "intelligent_planner": True,
            "memory": False,
            "handoffs": True,
            "multi_handoffs": True,
            "dependency_graph": True,
            "parallel_execution": True,
            "outcome_replan": True,
            "research": False,
            "actions": False,
        },
    }


def plan():
    return {
        "release_id": "coworker-cohort-001",
        "stages": [
            {"name": "canary-5", "min_members": 5, "max_users": 5},
            {"name": "canary-10", "min_members": 10, "max_users": 10},
        ],
    }


def rollback_completion(tmp_path, rollout_path):
    value = {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "verified_at": "2026-09-22T07:00:00+00:00",
        "artifact_sha256": {
            "rollout_manifest": recovery.sha256_file(rollout_path),
            "operator_status": "a" * 64,
        },
    }
    path = tmp_path / "rollback.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return value, path


def settings(members, *, microsoft=False):
    return SimpleNamespace(
        cohort_enforced=True,
        cohort_account_ids=frozenset(members),
        work_services_enabled=True,
        artifact_services_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_memory_enabled=False,
        agent_handoffs_enabled=True,
        agent_multi_handoffs_enabled=True,
        agent_dependency_graph_enabled=True,
        agent_parallel_execution_enabled=True,
        agent_outcome_replan_enabled=True,
        research_services_enabled=False,
        actions_enabled=False,
        microsoft_actions_enabled=microsoft,
    )


def test_recovery_configuration_matches_manifest_and_stage(monkeypatch, tmp_path):
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    rollback_value, _ = rollback_completion(tmp_path, rollout_path)
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    members = {"a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64}
    result = recovery.validate_recovery_configuration(
        settings(members),
        rollout(),
        plan(),
        rollback_value,
        rollout_path=rollout_path,
        current_stage="canary-5",
        deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    )
    assert result["members"] == 5
    assert result["capabilities"]["parallel_execution"] is True


def test_recovery_configuration_rejects_flag_drift(monkeypatch, tmp_path):
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    rollback_value, _ = rollback_completion(tmp_path, rollout_path)
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    value = settings({"a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64})
    value.actions_enabled = True
    with pytest.raises(recovery.RecoveryVerificationError, match="do not match"):
        recovery.validate_recovery_configuration(
            value,
            rollout(),
            plan(),
            rollback_value,
            rollout_path=rollout_path,
            current_stage="canary-5",
            deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
        )


def test_recovery_configuration_rejects_cohort_stage_overflow(monkeypatch, tmp_path):
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    rollback_value, _ = rollback_completion(tmp_path, rollout_path)
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    members = {f"{index:064x}" for index in range(6)}
    with pytest.raises(recovery.RecoveryVerificationError, match="outside canary-5 bounds"):
        recovery.validate_recovery_configuration(
            settings(members),
            rollout(),
            plan(),
            rollback_value,
            rollout_path=rollout_path,
            current_stage="canary-5",
            deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
        )


def test_build_recovery_evidence_requires_health_after_smoke(monkeypatch, tmp_path):
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan()), encoding="utf-8")
    rollback_value, rollback_path = rollback_completion(tmp_path, rollout_path)
    status_output = tmp_path / "status.json"
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    members = {"a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64}

    monkeypatch.setattr(
        recovery,
        "run_live_recovery_probe",
        lambda **kwargs: {
            "task_state": "completed",
            "task_updated_at": "2026-09-22T07:10:00+00:00",
            "artifact_count": 1,
            "model_attempts": 1,
            "accounted_tokens": 100,
            "admission": {"allowed": 200, "denied": 403},
        },
    )
    monkeypatch.setattr(
        recovery,
        "collect_snapshot",
        lambda _settings, window_minutes: {
            "generated_at": "2026-09-22T07:09:00+00:00",
            "window_minutes": window_minutes,
            "cohort_members_configured": 5,
            "active": {"tasks": 0, "agent_runs": 0, "provider_actions": 0, "oldest_work_age_seconds": 0},
            "tasks": {"samples": 1, "completed": 1, "failed": 0, "needs_input": 0, "success_rate": 1.0, "failure_rate": 0.0},
            "provider": {"samples": 1, "failed_or_unknown": 0, "failure_rate": 0.0, "p95_latency_ms": 1000, "window_tokens": 100, "reserved_attempts": 0},
            "agents": {"samples": 0, "failed": 0, "failure_rate": None},
            "research": {"samples": 0, "failed": 0, "failure_rate": None},
            "actions": {"samples": 0, "failed_or_unknown": 0, "outcome_unknown": 0, "failure_rate": None},
            "storage": {"total_bytes": 1000},
        },
    )
    monkeypatch.setattr(
        recovery,
        "evaluate",
        lambda snapshot, _rollout, _thresholds: {
            "decision": "CONTINUE_COHORT",
            "release_id": "coworker-cohort-001",
            "snapshot": snapshot,
            "breaches": [],
            "rollback": None,
        },
    )
    with pytest.raises(recovery.RecoveryVerificationError, match="predates completion"):
        recovery.build_recovery_evidence(
            settings=settings(members),
            rollout=rollout(),
            rollout_path=rollout_path,
            plan=plan(),
            plan_path=plan_path,
            rollback_completion=rollback_value,
            rollback_path=rollback_path,
            thresholds={"window_minutes": 15},
            current_stage="canary-5",
            deployment_reference="deploy-recovery-1",
            deployed_at="2026-09-22T07:05:00+00:00",
            base_url="https://staging.example.test",
            allowed_token="allowed",
            denied_token="denied",
            task_timeout=60,
            status_output=status_output,
        )


def test_google_only_recovery_does_not_require_microsoft_proof(tmp_path):
    assert recovery.validate_microsoft_recovery_activation(
        settings=settings({"a" * 64}, microsoft=False),
        activation_path=None,
        ledger_path=None,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion={
            "verified_at": "2026-09-22T07:00:00+00:00",
        },
        rollback_path=tmp_path / "unused.json",
        recovery_deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    ) is None


def seed_recovery_microsoft_chain(monkeypatch, tmp_path):
    from scripts.cohort_release_ledger import (
        append_event,
        append_rollback_event,
        append_microsoft_rollout_event,
        file_sha256,
    )

    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "release-ledger.jsonl"

    rollout_path = tmp_path / "rollout-ledger.json"
    plan_path = tmp_path / "plan-ledger.json"
    progression_path = tmp_path / "progression-ledger.json"
    stop_status_path = tmp_path / "stop-status-ledger.json"
    post_status_path = tmp_path / "post-status-ledger.json"
    rollback_path = tmp_path / "rollback-ledger.json"

    rollout_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 5},
    }), encoding="utf-8")
    plan_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "canary-5"}],
    }), encoding="utf-8")
    progression_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
        "current_stage": "canary-5",
        "next_stage": None,
    }), encoding="utf-8")
    stop_status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
    }), encoding="utf-8")
    post_status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    }), encoding="utf-8")

    append_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall",
        change_reference="incident-1",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=stop_status_path,
        created_at="2026-09-22T06:50:00+00:00",
    )

    rollback_path.write_text(json.dumps({
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "verified_at": "2026-09-22T07:00:00+00:00",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout_path),
            "operator_status": file_sha256(post_status_path),
        },
    }), encoding="utf-8")

    append_rollback_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="incident-1",
        current_stage="canary-5",
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=post_status_path,
        rollback_completion=rollback_path,
        created_at="2026-09-22T07:01:00+00:00",
    )

    staging_path = tmp_path / "microsoft-staging-recovery.json"
    deployment_path = tmp_path / "microsoft-deployment-recovery.json"
    microsoft_status_path = tmp_path / "microsoft-status-recovery.json"
    activation_path = tmp_path / "microsoft-activation-recovery.json"

    staging_path.write_text(json.dumps({
        "microsoft_actions": {
            "status": "passed",
            "evidence": "fresh post-rollback Microsoft validation",
            "verified_at": "2026-09-22T07:06:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "microsoft-recovery-1",
        "deployed_at": "2026-09-22T07:07:00+00:00",
        "frontend_base_url": "https://staging.example.com",
        "frontend_source_revision": "abcdef1234567",
        "staging_evidence_sha256": file_sha256(staging_path),
    }), encoding="utf-8")
    microsoft_status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T07:08:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    activation_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "microsoft_rollout_verified",
        "release_id": "coworker-cohort-001",
        "verified_at": "2026-09-22T07:09:00+00:00",
        "change_reference": "microsoft-recovery-1",
        "deployed_at": "2026-09-22T07:07:00+00:00",
        "frontend_base_url": "https://staging.example.com",
        "frontend_source_revision": "abcdef1234567",
        "backend": {
            "actions_enabled": True,
            "microsoft_actions_enabled": True,
        },
        "frontend": {
            "coworker_enabled": True,
            "microsoft_actions_enabled": True,
        },
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_path),
            "operator_status": file_sha256(microsoft_status_path),
        },
    }), encoding="utf-8")

    append_microsoft_rollout_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="microsoft-recovery-1",
        current_stage="canary-5",
        staging_evidence=staging_path,
        deployment_change=deployment_path,
        operator_status=microsoft_status_path,
        rollout_activation=activation_path,
        created_at="2026-09-22T07:10:00+00:00",
    )
    return ledger, rollback_path, activation_path


def test_microsoft_recovery_requires_fresh_schema_v6_after_rollback(monkeypatch, tmp_path):
    ledger, rollback_path, activation_path = seed_recovery_microsoft_chain(
        monkeypatch, tmp_path
    )
    result = recovery.validate_microsoft_recovery_activation(
        settings=settings({"a" * 64}, microsoft=True),
        activation_path=activation_path,
        ledger_path=ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion=json.loads(rollback_path.read_text(encoding="utf-8")),
        rollback_path=rollback_path,
        recovery_deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    )
    assert result["ledger_sequence"] == 3
    assert len(result["ledger_entry_hash"]) == 64


def test_microsoft_recovery_rejects_tampered_activation(monkeypatch, tmp_path):
    ledger, rollback_path, activation_path = seed_recovery_microsoft_chain(
        monkeypatch, tmp_path
    )
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["verified_at"] = "2026-09-22T07:11:00+00:00"
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        recovery.RecoveryVerificationError,
        match="schema-v6",
    ):
        recovery.validate_microsoft_recovery_activation(
            settings=settings({"a" * 64}, microsoft=True),
            activation_path=activation_path,
            ledger_path=ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion=json.loads(
                rollback_path.read_text(encoding="utf-8")
            ),
            rollback_path=rollback_path,
            recovery_deployed_at=datetime(
                2026, 9, 22, 7, 5, tzinfo=timezone.utc
            ),
        )


def test_microsoft_recovery_rejects_activation_before_recovery_deployment(monkeypatch, tmp_path):
    ledger, rollback_path, activation_path = seed_recovery_microsoft_chain(
        monkeypatch, tmp_path
    )
    with pytest.raises(
        recovery.RecoveryVerificationError,
        match="predates the recovery deployment",
    ):
        recovery.validate_microsoft_recovery_activation(
            settings=settings({"a" * 64}, microsoft=True),
            activation_path=activation_path,
            ledger_path=ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion=json.loads(
                rollback_path.read_text(encoding="utf-8")
            ),
            rollback_path=rollback_path,
            recovery_deployed_at=datetime(
                2026, 9, 22, 7, 8, tzinfo=timezone.utc
            ),
        )
