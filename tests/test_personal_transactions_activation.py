from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.personal_transactions_activation import (
    PersonalTransactionsActivationError,
    build_evidence,
    canonical_sha256,
    sha256_file,
    validate_reviewed_rollout,
    validate_runtime_manifest,
    validate_staging,
    validate_transaction_authority_manifest,
)


NOW = datetime(2026, 9, 28, 11, 30, tzinfo=timezone.utc)
REVISION = "a" * 40


def rollout():
    value = json.loads(Path("docs/cohort-rollout.template.json").read_text(encoding="utf-8"))
    value["action_providers"] = ["google"]
    value["capabilities"]["actions"] = True
    value["capabilities"]["connector_trust_boundary"] = True
    value["capabilities"]["personal_transactions"] = True
    value["transaction_operations"] = ["google:negotiation_commitment_email"]
    value["monitoring"]["actions"] = "actions-dashboard"
    value["incident"]["change_reference"] = "pa09-change-1"
    return value


def staging():
    return {
        "personal_transactions": {
            "status": "passed",
            "evidence": "live exact-term Google negotiation commitment passed",
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
        "cohort": {
            "enforced": True,
            "configured_members": 5,
            "max_users": reviewed["cohort_max_users"],
        },
    }


def transaction_authority(reviewed):
    return {
        "schema_version": 1,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "operations": list(reviewed["transaction_operations"]),
    }


def test_reviewed_rollout_requires_pa09_prerequisites_and_exact_kill_switch():
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    assert reviewed["capabilities"]["personal_transactions"] is True
    assert reviewed["capabilities"]["connector_trust_boundary"] is True
    assert reviewed["action_providers"] == ["google"]
    assert reviewed["transaction_operations"] == ["google:negotiation_commitment_email"]

    broken = rollout()
    broken["capabilities"]["connector_trust_boundary"] = False
    with pytest.raises(PersonalTransactionsActivationError):
        validate_reviewed_rollout(broken, max_cohort_users=25)

    broken = rollout()
    broken["rollback"]["personal_transactions_kill_switch"] = "wrong"
    with pytest.raises(PersonalTransactionsActivationError, match="personal_transactions_kill_switch"):
        validate_reviewed_rollout(broken, max_cohort_users=25)


def test_staging_must_be_passed_timestamped_and_fresh():
    verified = validate_staging(staging(), now=NOW, max_age_minutes=60)
    assert verified == NOW - timedelta(minutes=20)

    stale = staging()
    stale["personal_transactions"]["verified_at"] = (NOW - timedelta(hours=2)).isoformat()
    with pytest.raises(PersonalTransactionsActivationError, match="stale"):
        validate_staging(stale, now=NOW, max_age_minutes=60)


def test_runtime_manifest_must_exactly_match_reviewed_pa09_rollout():
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    deployment = {"source_revision": REVISION}
    value = runtime(reviewed)
    normalized = validate_runtime_manifest(value, deployment=deployment, rollout=reviewed)
    assert normalized["capabilities"]["personal_transactions"] is True

    changed = copy.deepcopy(value)
    changed["capabilities"]["personal_transactions"] = False
    with pytest.raises(PersonalTransactionsActivationError, match="capability flags"):
        validate_runtime_manifest(changed, deployment=deployment, rollout=reviewed)


def test_transaction_authority_manifest_must_exactly_match_reviewed_operation_allowlist():
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    deployment = {"source_revision": REVISION}
    value = transaction_authority(reviewed)
    normalized = validate_transaction_authority_manifest(
        value,
        deployment=deployment,
        rollout=reviewed,
    )
    assert normalized["operations"] == ["google:negotiation_commitment_email"]

    changed = copy.deepcopy(value)
    changed["operations"] = []
    with pytest.raises(PersonalTransactionsActivationError, match="operations"):
        validate_transaction_authority_manifest(
            changed,
            deployment=deployment,
            rollout=reviewed,
        )


def test_activation_evidence_binds_exact_artifacts(tmp_path):
    staging_path = tmp_path / "staging.json"
    rollout_path = tmp_path / "rollout.json"
    deployment_path = tmp_path / "deployment.json"
    status_path = tmp_path / "status.json"
    for path, value in (
        (staging_path, staging()),
        (rollout_path, rollout()),
        (deployment_path, {"release_id": "coworker-cohort-001"}),
        (status_path, {"release_id": "coworker-cohort-001", "generated_at": NOW.isoformat()}),
    ):
        path.write_text(json.dumps(value), encoding="utf-8")

    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    deployed = {
        "release_id": "coworker-cohort-001",
        "change_reference": "pa09-change-1",
        "current_stage": "canary-5",
        "deployed_at": NOW.isoformat(),
        "source_revision": REVISION,
    }
    evidence = build_evidence(
        deployment=deployed,
        staging_path=staging_path,
        rollout_path=rollout_path,
        deployment_path=deployment_path,
        operator_status_path=status_path,
        runtime=runtime(reviewed),
        transaction_authority=transaction_authority(reviewed),
        operator_status={"generated_at": NOW.isoformat()},
        now=NOW,
    )
    assert evidence["status"] == "personal_transactions_verified"
    assert evidence["runtime_manifest_sha256"] == canonical_sha256(evidence["runtime"])
    assert evidence["transaction_authority_manifest_sha256"] == canonical_sha256(
        evidence["transaction_authority"]
    )
    assert evidence["artifact_sha256"] == {
        "staging_evidence": sha256_file(staging_path),
        "rollout_manifest": sha256_file(rollout_path),
        "deployment_change": sha256_file(deployment_path),
        "operator_status": sha256_file(status_path),
    }
