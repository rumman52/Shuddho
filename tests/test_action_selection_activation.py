from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts.action_selection_activation import (
    ActionSelectionActivationError,
    build_evidence,
    require_runtime_flags,
    sha256_file,
    validate_deployment,
    validate_operator_status,
    validate_staging,
)


NOW = datetime(2026, 9, 23, 3, 30, tzinfo=timezone.utc)


def staging(verified_at=None):
    return {
        "action_selection": {
            "status": "passed",
            "evidence": "live action selection paused at approval",
            "verified_at": (
                verified_at
                or (NOW - timedelta(minutes=20)).isoformat()
            ),
        }
    }


def settings(**overrides):
    value = {
        "agent_runtime_enabled": True,
        "intelligent_planner_enabled": True,
        "actions_enabled": True,
        "agent_action_selection_enabled": True,
        "cohort_enforced": True,
        "cohort_account_ids": frozenset({"a" * 64}),
        "cohort_max_users": 25,
    }
    value.update(overrides)
    return SimpleNamespace(**value)


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
        ActionSelectionActivationError,
        match="stale",
    ):
        validate_staging(
            stale,
            now=NOW,
            max_age_minutes=60,
        )

    missing = staging()
    del missing["action_selection"]["verified_at"]
    with pytest.raises(
        ActionSelectionActivationError,
        match="verified_at",
    ):
        validate_staging(
            missing,
            now=NOW,
            max_age_minutes=60,
        )


def test_deployment_binds_exact_action_selection_evidence(tmp_path):
    evidence_path = tmp_path / "staging.json"
    evidence_path.write_text(
        json.dumps(staging()),
        encoding="utf-8",
    )
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "change-action-selection-1",
        "current_stage": "cohort-25",
        "deployed_at": (
            NOW - timedelta(minutes=10)
        ).isoformat(),
        "staging_evidence_sha256": sha256_file(evidence_path),
    }
    result = validate_deployment(
        deployment,
        evidence_path,
        not_before=NOW - timedelta(minutes=20),
    )
    assert result == NOW - timedelta(minutes=10)

    deployment["staging_evidence_sha256"] = "0" * 64
    with pytest.raises(
        ActionSelectionActivationError,
        match="exact action-selection staging evidence",
    ):
        validate_deployment(
            deployment,
            evidence_path,
            not_before=NOW - timedelta(minutes=20),
        )


def test_runtime_requires_every_action_selection_prerequisite():
    result = require_runtime_flags(
        settings(),
        coworker_is_enabled=True,
    )
    assert result["action_selection_enabled"] is True
    assert result["cohort_members_configured"] == 1

    cases = [
        ("coworker_enabled", settings(), False),
        (
            "agent_runtime_enabled",
            settings(agent_runtime_enabled=False),
            True,
        ),
        (
            "intelligent_planner_enabled",
            settings(intelligent_planner_enabled=False),
            True,
        ),
        (
            "actions_enabled",
            settings(actions_enabled=False),
            True,
        ),
        (
            "action_selection_enabled",
            settings(agent_action_selection_enabled=False),
            True,
        ),
        (
            "cohort_enforced",
            settings(cohort_enforced=False),
            True,
        ),
    ]
    for expected, current, coworker_flag in cases:
        with pytest.raises(
            ActionSelectionActivationError,
            match=expected,
        ):
            require_runtime_flags(
                current,
                coworker_is_enabled=coworker_flag,
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

    status["decision"] = "STOP_ROLLOUT"
    with pytest.raises(
        ActionSelectionActivationError,
        match="CONTINUE_COHORT",
    ):
        validate_operator_status(
            status,
            "coworker-cohort-001",
            not_before=deployment_time,
            now=NOW,
            freshness_minutes=30,
        )


def test_activation_evidence_hash_binds_exact_inputs(tmp_path):
    staging_path = tmp_path / "staging.json"
    deployment_path = tmp_path / "deployment.json"
    status_path = tmp_path / "status.json"

    staging_path.write_text(
        json.dumps(staging()),
        encoding="utf-8",
    )
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "change-action-selection-1",
        "current_stage": "cohort-25",
        "deployed_at": (
            NOW - timedelta(minutes=10)
        ).isoformat(),
        "staging_evidence_sha256": sha256_file(staging_path),
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

    evidence = build_evidence(
        deployment=deployment,
        staging_path=staging_path,
        deployment_path=deployment_path,
        operator_status_path=status_path,
        runtime=require_runtime_flags(
            settings(),
            coworker_is_enabled=True,
        ),
        operator_status=operator_status,
        now=NOW,
    )

    assert evidence["status"] == "action_selection_verified"
    assert evidence["release_id"] == "coworker-cohort-001"
    assert evidence["current_stage"] == "cohort-25"
    assert (
        evidence["artifact_sha256"]["staging_evidence"]
        == sha256_file(staging_path)
    )
    assert (
        evidence["artifact_sha256"]["deployment_change"]
        == sha256_file(deployment_path)
    )
    assert (
        evidence["artifact_sha256"]["operator_status"]
        == sha256_file(status_path)
    )
