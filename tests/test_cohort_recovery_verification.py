from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for recovery verification tests")

from scripts import cohort_recovery_verification as recovery


def rollout(*, action_selection=False, action_proposals=False, action_attachments=False, action_reminders=False, action_recipients=False, action_document_sharing=False):
    value = {
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
            "actions": action_selection or action_proposals or action_attachments or action_reminders or action_recipients or action_document_sharing,
        },
    }
    if action_selection:
        value["capabilities"]["action_selection"] = True
    if action_proposals:
        value["capabilities"]["action_proposals"] = True
    if action_attachments:
        value["capabilities"]["action_attachments"] = True
    if action_reminders:
        value["capabilities"]["action_reminders"] = True
    if action_recipients:
        value["capabilities"]["action_recipients"] = True
    if action_document_sharing:
        value["capabilities"]["action_document_sharing"] = True
    return value


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


def settings(members, *, microsoft=False, action_selection=False, action_proposals=False, action_attachments=False, action_reminders=False, action_recipients=False, action_document_sharing=False):
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
        actions_enabled=action_selection or action_proposals or action_attachments or action_reminders or action_recipients or action_document_sharing,
        microsoft_actions_enabled=microsoft,
        agent_action_selection_enabled=action_selection,
        agent_action_proposals_enabled=action_proposals,
        action_attachments_enabled=action_attachments,
        action_reminders_enabled=action_reminders,
        action_recipients_enabled=action_recipients,
        action_document_sharing_enabled=action_document_sharing,
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


def seed_recovery_action_selection_chain(monkeypatch, tmp_path):
    from scripts.cohort_release_ledger import (
        append_action_selection_event,
        append_event,
        append_rollback_event,
        file_sha256,
    )

    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "action-selection-recovery-ledger.jsonl"

    rollout_path = tmp_path / "as-rollout.json"
    plan_path = tmp_path / "as-plan.json"
    progression_path = tmp_path / "as-progression.json"
    stop_status_path = tmp_path / "as-stop-status.json"
    post_status_path = tmp_path / "as-post-status.json"
    rollback_path = tmp_path / "as-rollback.json"

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
        change_reference="incident-action-selection",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=stop_status_path,
        created_at="2026-09-23T04:00:00+00:00",
    )

    rollback_path.write_text(json.dumps({
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "verified_at": "2026-09-23T04:05:00+00:00",
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
        change_reference="incident-action-selection",
        current_stage="canary-5",
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=post_status_path,
        rollback_completion=rollback_path,
        created_at="2026-09-23T04:06:00+00:00",
    )

    staging_path = tmp_path / "as-staging.json"
    deployment_path = tmp_path / "as-deployment.json"
    status_path = tmp_path / "as-status.json"
    activation_path = tmp_path / "as-activation.json"

    staging_path.write_text(json.dumps({
        "action_selection": {
            "status": "passed",
            "evidence": "fresh recovery action selection proof",
            "verified_at": "2026-09-23T04:08:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "action-selection-recovery-1",
        "current_stage": "canary-5",
        "deployed_at": "2026-09-23T04:10:00+00:00",
        "staging_evidence_sha256": file_sha256(staging_path),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-23T04:11:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    activation_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "action_selection_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "canary-5",
        "verified_at": "2026-09-23T04:12:00+00:00",
        "change_reference": "action-selection-recovery-1",
        "deployed_at": "2026-09-23T04:10:00+00:00",
        "operator_status_generated_at": "2026-09-23T04:11:00+00:00",
        "runtime": {
            "coworker_enabled": True,
            "agent_runtime_enabled": True,
            "intelligent_planner_enabled": True,
            "actions_enabled": True,
            "action_selection_enabled": True,
            "cohort_enforced": True,
            "cohort_members_configured": 5,
            "cohort_max_users": 5,
        },
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_path),
            "deployment_change": file_sha256(deployment_path),
            "operator_status": file_sha256(status_path),
        },
    }), encoding="utf-8")

    entry = append_action_selection_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="action-selection-recovery-1",
        current_stage="canary-5",
        staging_evidence=staging_path,
        deployment_change=deployment_path,
        operator_status=status_path,
        action_selection_activation=activation_path,
        created_at="2026-09-23T04:13:00+00:00",
    )
    return ledger, rollback_path, activation_path, entry


def test_action_selection_recovery_requires_fresh_schema_v7_after_rollback(monkeypatch, tmp_path):
    ledger, rollback_path, activation_path, entry = (
        seed_recovery_action_selection_chain(monkeypatch, tmp_path)
    )
    result = recovery.validate_action_selection_recovery_activation(
        settings=settings({"a" * 64}, action_selection=True),
        activation_path=activation_path,
        ledger_path=ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion=json.loads(
            rollback_path.read_text(encoding="utf-8")
        ),
        rollback_path=rollback_path,
        recovery_deployed_at=datetime(
            2026, 9, 23, 4, 9, tzinfo=timezone.utc
        ),
    )
    assert result["ledger_sequence"] == entry["sequence"]
    assert result["ledger_entry_hash"] == entry["entry_hash"]


def test_action_selection_recovery_rejects_tampered_activation(monkeypatch, tmp_path):
    ledger, rollback_path, activation_path, _ = (
        seed_recovery_action_selection_chain(monkeypatch, tmp_path)
    )
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["verified_at"] = "2026-09-23T04:14:00+00:00"
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        recovery.RecoveryVerificationError,
        match="Release ledger verification failed",
    ):
        recovery.validate_action_selection_recovery_activation(
            settings=settings({"a" * 64}, action_selection=True),
            activation_path=activation_path,
            ledger_path=ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion=json.loads(
                rollback_path.read_text(encoding="utf-8")
            ),
            rollback_path=rollback_path,
            recovery_deployed_at=datetime(
                2026, 9, 23, 4, 9, tzinfo=timezone.utc
            ),
        )


def test_legacy_recovery_manifest_defaults_action_selection_off(monkeypatch, tmp_path):
    rollout_path = tmp_path / "legacy-rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    rollback_value, _ = rollback_completion(tmp_path, rollout_path)
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    members = {
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
    }
    result = recovery.validate_recovery_configuration(
        settings(members),
        rollout(),
        plan(),
        rollback_value,
        rollout_path=rollout_path,
        current_stage="canary-5",
        deployed_at=datetime(
            2026, 9, 22, 7, 5, tzinfo=timezone.utc
        ),
    )
    assert result["capabilities"]["action_selection"] is False


def test_legacy_recovery_manifest_defaults_action_proposals_off(monkeypatch, tmp_path):
    rollout_path = tmp_path / "legacy-proposal-rollout.json"
    value = rollout()
    value["capabilities"].pop("action_proposals", None)
    rollout_path.write_text(json.dumps(value), encoding="utf-8")
    rollback_value, _ = rollback_completion(tmp_path, rollout_path)
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    members = {"a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64}
    result = recovery.validate_recovery_configuration(
        settings(members, action_proposals=False),
        value,
        plan(),
        rollback_value,
        rollout_path=rollout_path,
        current_stage="canary-5",
        deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    )
    assert result["capabilities"]["action_proposals"] is False

def seed_recovery_action_proposals_chain(monkeypatch, tmp_path):
    from scripts.cohort_release_ledger import (
        append_action_proposals_event,
        file_sha256,
    )

    ledger, rollback_path, _action_selection_activation, _ = (
        seed_recovery_action_selection_chain(monkeypatch, tmp_path)
    )

    capabilities = {
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
        "actions": True,
        "action_selection": False,
        "action_proposals": True,
    }
    rollout_path = tmp_path / "proposal-recovery-rollout.json"
    staging_path = tmp_path / "proposal-recovery-staging.json"
    deployment_path = tmp_path / "proposal-recovery-deployment.json"
    status_path = tmp_path / "proposal-recovery-status.json"
    activation_path = tmp_path / "proposal-recovery-activation.json"

    rollout_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "approved-cohort", "max_users": 5},
        "capabilities": capabilities,
        "action_providers": ["google"],
        "rollback": {
            "action_proposals_kill_switch":
                "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false",
        },
        "incident": {"change_reference": "proposal-recovery-1"},
    }), encoding="utf-8")
    staging_path.write_text(json.dumps({
        "action_proposals": {
            "status": "passed",
            "evidence": "fresh post-rollback inert proposal validation",
            "verified_at": "2026-09-23T04:14:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "proposal-recovery-1",
        "current_stage": "canary-5",
        "deployed_at": "2026-09-23T04:15:00+00:00",
        "source_revision": "b" * 40,
        "staging_evidence_sha256": file_sha256(staging_path),
        "rollout_manifest_sha256": file_sha256(rollout_path),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-23T04:16:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    runtime = {
        "schema_version": 1,
        "source_revision": "b" * 40,
        "environment": "production",
        "capabilities": capabilities,
        "action_providers": ["google"],
        "cohort": {
            "enforced": True,
            "configured_members": 5,
            "max_users": 5,
        },
    }
    runtime_hash = hashlib.sha256(json.dumps(
        runtime,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    activation_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "action_proposals_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "canary-5",
        "verified_at": "2026-09-23T04:17:00+00:00",
        "change_reference": "proposal-recovery-1",
        "deployed_at": "2026-09-23T04:15:00+00:00",
        "source_revision": "b" * 40,
        "operator_status_generated_at": "2026-09-23T04:16:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": runtime_hash,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_path),
            "rollout_manifest": file_sha256(rollout_path),
            "deployment_change": file_sha256(deployment_path),
            "operator_status": file_sha256(status_path),
        },
    }), encoding="utf-8")

    entry = append_action_proposals_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="proposal-recovery-1",
        current_stage="canary-5",
        staging_evidence=staging_path,
        rollout_manifest=rollout_path,
        deployment_change=deployment_path,
        operator_status=status_path,
        action_proposals_activation=activation_path,
        created_at="2026-09-23T04:18:00+00:00",
    )
    return ledger, rollback_path, activation_path, entry


def test_action_proposals_recovery_requires_fresh_schema_v8_after_rollback(
    monkeypatch,
    tmp_path,
):
    ledger, rollback_path, activation_path, entry = (
        seed_recovery_action_proposals_chain(monkeypatch, tmp_path)
    )
    result = recovery.validate_action_proposals_recovery_activation(
        settings=settings({"a" * 64}, action_proposals=True),
        activation_path=activation_path,
        ledger_path=ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion=json.loads(
            rollback_path.read_text(encoding="utf-8")
        ),
        rollback_path=rollback_path,
        recovery_deployed_at=datetime(
            2026, 9, 23, 4, 9, tzinfo=timezone.utc
        ),
    )
    assert result["ledger_sequence"] == entry["sequence"]
    assert result["ledger_entry_hash"] == entry["entry_hash"]


def test_action_proposals_recovery_rejects_tampered_activation(
    monkeypatch,
    tmp_path,
):
    ledger, rollback_path, activation_path, _ = (
        seed_recovery_action_proposals_chain(monkeypatch, tmp_path)
    )
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["verified_at"] = "2026-09-23T04:19:00+00:00"
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        recovery.RecoveryVerificationError,
        match="Release ledger verification failed",
    ):
        recovery.validate_action_proposals_recovery_activation(
            settings=settings({"a" * 64}, action_proposals=True),
            activation_path=activation_path,
            ledger_path=ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion=json.loads(
                rollback_path.read_text(encoding="utf-8")
            ),
            rollback_path=rollback_path,
            recovery_deployed_at=datetime(
                2026, 9, 23, 4, 9, tzinfo=timezone.utc
            ),
        )


def test_action_proposals_recovery_rejects_activation_before_recovery_deployment(
    monkeypatch,
    tmp_path,
):
    ledger, rollback_path, activation_path, _ = (
        seed_recovery_action_proposals_chain(monkeypatch, tmp_path)
    )
    with pytest.raises(
        recovery.RecoveryVerificationError,
        match="predates the recovery deployment",
    ):
        recovery.validate_action_proposals_recovery_activation(
            settings=settings({"a" * 64}, action_proposals=True),
            activation_path=activation_path,
            ledger_path=ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion=json.loads(
                rollback_path.read_text(encoding="utf-8")
            ),
            rollback_path=rollback_path,
            recovery_deployed_at=datetime(
                2026, 9, 23, 4, 16, tzinfo=timezone.utc
            ),
        )



def seed_recovery_action_attachments_chain(monkeypatch, tmp_path):
    from scripts.cohort_release_ledger import (
        append_action_attachments_event,
        file_sha256,
    )

    ledger, rollback_path, _selection_activation, _ = (
        seed_recovery_action_selection_chain(monkeypatch, tmp_path)
    )

    capabilities = {
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
        "actions": True,
        "action_attachments": True,
        "action_selection": False,
        "action_proposals": False,
    }
    rollout_path = tmp_path / "attachment-recovery-rollout.json"
    staging_path = tmp_path / "attachment-recovery-staging.json"
    deployment_path = tmp_path / "attachment-recovery-deployment.json"
    status_path = tmp_path / "attachment-recovery-status.json"
    activation_path = tmp_path / "attachment-recovery-activation.json"

    rollout_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "approved-cohort", "max_users": 5},
        "capabilities": capabilities,
        "action_providers": ["google"],
        "rollback": {
            "action_attachments_kill_switch":
                "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
        },
        "incident": {"change_reference": "attachment-recovery-1"},
    }), encoding="utf-8")
    staging_path.write_text(json.dumps({
        "action_attachments": {
            "status": "passed",
            "evidence": "fresh post-rollback synthetic attachment validation",
            "verified_at": "2026-09-23T04:14:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "attachment-recovery-1",
        "current_stage": "canary-5",
        "deployed_at": "2026-09-23T04:15:00+00:00",
        "source_revision": "c" * 40,
        "staging_evidence_sha256": file_sha256(staging_path),
        "rollout_manifest_sha256": file_sha256(rollout_path),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-23T04:16:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    runtime = {
        "schema_version": 1,
        "source_revision": "c" * 40,
        "environment": "production",
        "capabilities": capabilities,
        "action_providers": ["google"],
        "cohort": {
            "enforced": True,
            "configured_members": 5,
            "max_users": 5,
        },
    }
    activation_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "action_attachments_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "canary-5",
        "verified_at": "2026-09-23T04:17:00+00:00",
        "change_reference": "attachment-recovery-1",
        "deployed_at": "2026-09-23T04:15:00+00:00",
        "source_revision": "c" * 40,
        "operator_status_generated_at": "2026-09-23T04:16:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": hashlib.sha256(json.dumps(
            runtime,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_path),
            "rollout_manifest": file_sha256(rollout_path),
            "deployment_change": file_sha256(deployment_path),
            "operator_status": file_sha256(status_path),
        },
    }), encoding="utf-8")

    entry = append_action_attachments_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="attachment-recovery-1",
        current_stage="canary-5",
        staging_evidence=staging_path,
        rollout_manifest=rollout_path,
        deployment_change=deployment_path,
        operator_status=status_path,
        action_attachments_activation=activation_path,
        created_at="2026-09-23T04:18:00+00:00",
    )
    return ledger, rollback_path, activation_path, entry


def test_action_attachments_recovery_requires_fresh_schema_v9_after_rollback(
    monkeypatch,
    tmp_path,
):
    ledger, rollback_path, activation_path, entry = (
        seed_recovery_action_attachments_chain(monkeypatch, tmp_path)
    )
    result = recovery.validate_action_attachments_recovery_activation(
        settings=settings({"a" * 64}, action_attachments=True),
        activation_path=activation_path,
        ledger_path=ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion=json.loads(
            rollback_path.read_text(encoding="utf-8")
        ),
        rollback_path=rollback_path,
        recovery_deployed_at=datetime(
            2026, 9, 23, 4, 9, tzinfo=timezone.utc
        ),
    )
    assert result["ledger_sequence"] == entry["sequence"]
    assert result["ledger_entry_hash"] == entry["entry_hash"]


def test_action_attachments_recovery_rejects_tampered_activation(
    monkeypatch,
    tmp_path,
):
    ledger, rollback_path, activation_path, _ = (
        seed_recovery_action_attachments_chain(monkeypatch, tmp_path)
    )
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["verified_at"] = "2026-09-23T04:19:00+00:00"
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        recovery.RecoveryVerificationError,
        match="Release ledger verification failed",
    ):
        recovery.validate_action_attachments_recovery_activation(
            settings=settings({"a" * 64}, action_attachments=True),
            activation_path=activation_path,
            ledger_path=ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion=json.loads(
                rollback_path.read_text(encoding="utf-8")
            ),
            rollback_path=rollback_path,
            recovery_deployed_at=datetime(
                2026, 9, 23, 4, 9, tzinfo=timezone.utc
            ),
        )


def test_recovery_configuration_tracks_attachment_flag(monkeypatch, tmp_path):
    value = rollout(action_attachments=True)
    rollout_path = tmp_path / "attachment-rollout.json"
    rollout_path.write_text(json.dumps(value), encoding="utf-8")
    rollback_value, _ = rollback_completion(tmp_path, rollout_path)
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    members = {"a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64}
    result = recovery.validate_recovery_configuration(
        settings(members, action_attachments=True),
        value,
        plan(),
        rollback_value,
        rollout_path=rollout_path,
        current_stage="canary-5",
        deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    )
    assert result["capabilities"]["action_attachments"] is True


def test_action_recipients_recovery_activation_is_optional_when_disabled(tmp_path):
    assert recovery.validate_action_recipients_recovery_activation(
        settings=settings({"a" * 64}, action_recipients=False),
        activation_path=None,
        ledger_path=None,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion={"verified_at": "2026-09-22T07:00:00+00:00"},
        rollback_path=tmp_path / "unused.json",
        recovery_deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    ) is None


def test_action_recipients_recovery_requires_fresh_activation_and_ledger(tmp_path):
    with pytest.raises(recovery.RecoveryVerificationError, match="fresh recipient activation"):
        recovery.validate_action_recipients_recovery_activation(
            settings=settings({"a" * 64}, action_recipients=True),
            activation_path=None,
            ledger_path=None,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion={"verified_at": "2026-09-22T07:00:00+00:00"},
            rollback_path=tmp_path / "rollback.json",
            recovery_deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
        )


def test_document_sharing_recovery_activation_is_optional_when_disabled(tmp_path):
    assert recovery.validate_action_document_sharing_recovery_activation(
        settings=settings({"a" * 64}, action_document_sharing=False),
        activation_path=None,
        ledger_path=None,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
        rollback_completion={"verified_at": "2026-09-22T07:00:00+00:00"},
        rollback_path=tmp_path / "unused.json",
        recovery_deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
    ) is None


def test_document_sharing_recovery_requires_fresh_activation_and_ledger(tmp_path):
    with pytest.raises(recovery.RecoveryVerificationError, match="fresh"):
        recovery.validate_action_document_sharing_recovery_activation(
            settings=settings({"a" * 64}, action_document_sharing=True),
            activation_path=None,
            ledger_path=None,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollback_completion={"verified_at": "2026-09-22T07:00:00+00:00"},
            rollback_path=tmp_path / "rollback.json",
            recovery_deployed_at=datetime(2026, 9, 22, 7, 5, tzinfo=timezone.utc),
        )
