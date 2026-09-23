from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from scripts.action_attachments_activation import (
    ActionAttachmentsActivationError,
    build_evidence,
    canonical_sha256,
    fetch_runtime_manifest,
    sha256_file,
    validate_deployment,
    validate_operator_status,
    validate_reviewed_rollout,
    validate_runtime_manifest,
    validate_staging,
)


NOW = datetime(2026, 9, 23, 6, 30, tzinfo=timezone.utc)
REVISION = "a" * 40


def staging(verified_at=None):
    return {
        "action_attachments": {
            "status": "passed",
            "evidence": (
                "live approved attachment email preserved the exact artifact manifest "
                "through explicit approval and provider acceptance"
            ),
            "verified_at": (
                verified_at
                or (NOW - timedelta(minutes=20)).isoformat()
            ),
        }
    }


def rollout():
    return {
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {
            "reference": "cohort-ticket",
            "max_users": 25,
        },
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
            "action_attachments": True,
            "action_selection": False,
            "action_proposals": False,
        },
        "rollback": {
            "runbook_reference": "rollback-runbook",
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": (
                "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false"
            ),
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
            "action_selection_kill_switch": (
                "SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false"
            ),
            "action_attachments_kill_switch": "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
        },
        "monitoring": {
            "queue_age": "queue-dashboard",
            "task_success": "task-dashboard",
            "provider_errors": "provider-alert",
            "latency": "latency-dashboard",
            "token_cost": "cost-dashboard",
            "storage_growth": "storage-dashboard",
            "agent_failures": "agent-alert",
            "actions": "actions-dashboard",
        },
        "incident": {
            "oncall_reference": "oncall-owner",
            "change_reference": "change-action-attachments-001",
        },
    }


def runtime(reviewed=None):
    reviewed = reviewed or validate_reviewed_rollout(
        rollout(),
        max_cohort_users=25,
    )
    return {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": "production",
        "capabilities": dict(reviewed["capabilities"]),
        "action_providers": list(reviewed["action_providers"]),
        "cohort": {
            "enforced": True,
            "configured_members": 5,
            "max_users": reviewed["cohort_max_users"],
        },
    }


def test_staging_evidence_must_be_passed_fresh_and_timestamped():
    verified = validate_staging(
        staging(),
        now=NOW,
        max_age_minutes=60,
    )
    assert verified == NOW - timedelta(minutes=20)

    stale = staging(
        (NOW - timedelta(hours=2)).isoformat()
    )
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="stale",
    ):
        validate_staging(
            stale,
            now=NOW,
            max_age_minutes=60,
        )


def test_reviewed_rollout_requires_action_attachments_and_exact_kill_switch():
    value = rollout()
    reviewed = validate_reviewed_rollout(
        value,
        max_cohort_users=25,
    )
    assert reviewed["capabilities"]["action_attachments"] is True
    assert reviewed["action_providers"] == ["google"]

    value["capabilities"]["action_attachments"] = False
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="does not enable action_attachments",
    ):
        validate_reviewed_rollout(
            value,
            max_cohort_users=25,
        )

    value = rollout()
    value["rollback"]["action_attachments_kill_switch"] = "wrong"
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="invalid",
    ):
        validate_reviewed_rollout(
            value,
            max_cohort_users=25,
        )


def test_deployment_binds_exact_staging_rollout_and_revision(tmp_path):
    staging_path = tmp_path / "staging.json"
    rollout_path = tmp_path / "rollout.json"
    staging_path.write_text(
        json.dumps(staging()),
        encoding="utf-8",
    )
    rollout_path.write_text(
        json.dumps(rollout()),
        encoding="utf-8",
    )
    reviewed = validate_reviewed_rollout(
        rollout(),
        max_cohort_users=25,
    )
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "change-action-attachments-001",
        "current_stage": "cohort-25",
        "deployed_at": (
            NOW - timedelta(minutes=10)
        ).isoformat(),
        "source_revision": REVISION,
        "staging_evidence_sha256": sha256_file(staging_path),
        "rollout_manifest_sha256": sha256_file(rollout_path),
    }
    result = validate_deployment(
        deployment,
        staging_path=staging_path,
        rollout_path=rollout_path,
        rollout=reviewed,
        not_before=NOW - timedelta(minutes=20),
    )
    assert result == NOW - timedelta(minutes=10)

    deployment["source_revision"] = "short"
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="source_revision",
    ):
        validate_deployment(
            deployment,
            staging_path=staging_path,
            rollout_path=rollout_path,
            rollout=reviewed,
            not_before=NOW - timedelta(minutes=20),
        )


def test_runtime_manifest_must_exactly_match_reviewed_deployment():
    reviewed = validate_reviewed_rollout(
        rollout(),
        max_cohort_users=25,
    )
    deployment = {
        "source_revision": REVISION,
    }
    current = runtime(reviewed)
    result = validate_runtime_manifest(
        current,
        deployment=deployment,
        rollout=reviewed,
    )
    assert result["source_revision"] == REVISION
    assert result["capabilities"]["action_attachments"] is True

    drifted = json.loads(json.dumps(current))
    drifted["capabilities"]["memory"] = True
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="capability flags",
    ):
        validate_runtime_manifest(
            drifted,
            deployment=deployment,
            rollout=reviewed,
        )

    wrong_revision = json.loads(json.dumps(current))
    wrong_revision["source_revision"] = "b" * 40
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="revision",
    ):
        validate_runtime_manifest(
            wrong_revision,
            deployment=deployment,
            rollout=reviewed,
        )

    overflow = json.loads(json.dumps(current))
    overflow["cohort"]["configured_members"] = 26
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="membership count",
    ):
        validate_runtime_manifest(
            overflow,
            deployment=deployment,
            rollout=reviewed,
        )


def test_runtime_manifest_fetch_is_https_authenticated_and_no_redirect():
    expected = runtime()

    def respond(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer verification-token"
        assert request.url.path == "/api/v1/runtime-manifest"
        return httpx.Response(200, json=expected)

    value = fetch_runtime_manifest(
        base_url="https://prod.example.test",
        token="verification-token",
        timeout_seconds=5,
        transport=httpx.MockTransport(respond),
    )
    assert value == expected

    with pytest.raises(
        ActionAttachmentsActivationError,
        match="clean HTTPS origin",
    ):
        fetch_runtime_manifest(
            base_url="http://prod.example.test",
            token="verification-token",
            timeout_seconds=5,
            transport=httpx.MockTransport(respond),
        )


def test_post_deploy_operator_status_is_required():
    deployment_time = NOW - timedelta(minutes=10)
    status = {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": (
            NOW - timedelta(minutes=5)
        ).isoformat(),
        "breaches": [],
    }
    validate_operator_status(
        status,
        "coworker-cohort-001",
        not_before=deployment_time,
        now=NOW,
        freshness_minutes=30,
    )

    status["breaches"] = ["provider_failure_ratio"]
    with pytest.raises(
        ActionAttachmentsActivationError,
        match="CONTINUE_COHORT",
    ):
        validate_operator_status(
            status,
            "coworker-cohort-001",
            not_before=deployment_time,
            now=NOW,
            freshness_minutes=30,
        )


def test_activation_evidence_binds_all_inputs_and_remote_runtime(tmp_path):
    staging_path = tmp_path / "staging.json"
    rollout_path = tmp_path / "rollout.json"
    deployment_path = tmp_path / "deployment.json"
    status_path = tmp_path / "status.json"

    staging_path.write_text(
        json.dumps(staging()),
        encoding="utf-8",
    )
    rollout_path.write_text(
        json.dumps(rollout()),
        encoding="utf-8",
    )
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "change-action-attachments-001",
        "current_stage": "cohort-25",
        "deployed_at": (
            NOW - timedelta(minutes=10)
        ).isoformat(),
        "source_revision": REVISION,
        "staging_evidence_sha256": sha256_file(staging_path),
        "rollout_manifest_sha256": sha256_file(rollout_path),
    }
    deployment_path.write_text(
        json.dumps(deployment),
        encoding="utf-8",
    )
    operator_status = {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": (
            NOW - timedelta(minutes=5)
        ).isoformat(),
        "breaches": [],
    }
    status_path.write_text(
        json.dumps(operator_status),
        encoding="utf-8",
    )
    remote = runtime()

    evidence = build_evidence(
        deployment=deployment,
        staging_path=staging_path,
        rollout_path=rollout_path,
        deployment_path=deployment_path,
        operator_status_path=status_path,
        runtime=remote,
        operator_status=operator_status,
        now=NOW,
    )

    assert evidence["status"] == "action_attachments_verified"
    assert evidence["source_revision"] == REVISION
    assert evidence["runtime_manifest_sha256"] == canonical_sha256(remote)
    assert (
        evidence["artifact_sha256"]["staging_evidence"]
        == sha256_file(staging_path)
    )
    assert (
        evidence["artifact_sha256"]["rollout_manifest"]
        == sha256_file(rollout_path)
    )
    assert (
        evidence["artifact_sha256"]["deployment_change"]
        == sha256_file(deployment_path)
    )
    assert (
        evidence["artifact_sha256"]["operator_status"]
        == sha256_file(status_path)
    )
