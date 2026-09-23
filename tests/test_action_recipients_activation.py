from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.action_recipients_activation import (
    ActionRecipientsActivationError,
    build_evidence,
    canonical_sha256,
    sha256_file,
    validate_reviewed_rollout,
    validate_runtime_manifest,
    validate_staging,
)


NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
REVISION = "a" * 40


def rollout():
    return {
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "cohort-ticket", "max_users": 25},
        "action_providers": ["google"],
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
            "actions": True,
            "action_attachments": False,
            "action_reminders": False,
            "action_recipients": True,
            "action_selection": False,
            "action_proposals": False,
        },
        "rollback": {
            "runbook_reference": "rollback-runbook",
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
            "action_recipients_kill_switch": "SHUDDHO_ACTION_RECIPIENTS_ENABLED=false",
        },
        "monitoring": {
            "queue_age": "q",
            "task_success": "s",
            "provider_errors": "p",
            "latency": "l",
            "token_cost": "t",
            "storage_growth": "g",
            "agent_failures": "a",
            "actions": "actions",
        },
        "incident": {"oncall_reference": "oncall", "change_reference": "recipient-change-1"},
    }


def staging():
    return {
        "action_recipients": {
            "status": "passed",
            "evidence": "owner isolation and CRUD passed",
            "verified_at": (NOW - timedelta(minutes=20)).isoformat(),
        }
    }


def runtime(reviewed):
    return {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": "production",
        "capabilities": dict(reviewed["capabilities"]),
        "action_providers": list(reviewed["action_providers"]),
        "cohort": {"enforced": True, "configured_members": 5, "max_users": 25},
    }


def test_reviewed_rollout_requires_exact_recipient_kill_switch():
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    assert reviewed["capabilities"]["action_recipients"] is True
    broken = rollout()
    broken["rollback"]["action_recipients_kill_switch"] = "wrong"
    with pytest.raises(ActionRecipientsActivationError):
        validate_reviewed_rollout(broken, max_cohort_users=25)


def test_staging_is_timestamped_fresh_and_passed():
    assert validate_staging(
        staging(),
        now=NOW,
        max_age_minutes=60,
    ) == NOW - timedelta(minutes=20)
    stale = staging()
    stale["action_recipients"]["verified_at"] = (NOW - timedelta(minutes=61)).isoformat()
    with pytest.raises(ActionRecipientsActivationError, match="stale"):
        validate_staging(stale, now=NOW, max_age_minutes=60)


def test_runtime_manifest_exactly_matches_reviewed_recipient_rollout():
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    value = runtime(reviewed)
    result = validate_runtime_manifest(
        value,
        deployment={"source_revision": REVISION},
        rollout=reviewed,
    )
    assert result["capabilities"]["action_recipients"] is True

    drifted = json.loads(json.dumps(value))
    drifted["capabilities"]["action_recipients"] = False
    with pytest.raises(ActionRecipientsActivationError, match="capability flags"):
        validate_runtime_manifest(
            drifted,
            deployment={"source_revision": REVISION},
            rollout=reviewed,
        )


def test_activation_evidence_binds_inputs(tmp_path):
    staging_path = tmp_path / "staging.json"
    rollout_path = tmp_path / "rollout.json"
    deployment_path = tmp_path / "deployment.json"
    status_path = tmp_path / "status.json"
    staging_path.write_text(json.dumps(staging()), encoding="utf-8")
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "recipient-change-1",
        "current_stage": "cohort-25",
        "deployed_at": (NOW - timedelta(minutes=10)).isoformat(),
        "source_revision": REVISION,
        "staging_evidence_sha256": sha256_file(staging_path),
        "rollout_manifest_sha256": sha256_file(rollout_path),
    }
    deployment_path.write_text(json.dumps(deployment), encoding="utf-8")
    status = {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": (NOW - timedelta(minutes=5)).isoformat(),
        "breaches": [],
    }
    status_path.write_text(json.dumps(status), encoding="utf-8")
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    evidence = build_evidence(
        deployment=deployment,
        staging_path=staging_path,
        rollout_path=rollout_path,
        deployment_path=deployment_path,
        operator_status_path=status_path,
        runtime=runtime(reviewed),
        operator_status=status,
        now=NOW,
    )
    assert evidence["status"] == "action_recipients_verified"
    assert evidence["runtime_manifest_sha256"] == canonical_sha256(runtime(reviewed))
    assert evidence["artifact_sha256"]["staging_evidence"] == sha256_file(staging_path)
