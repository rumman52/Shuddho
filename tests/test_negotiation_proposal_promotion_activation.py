from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.negotiation_proposal_promotion_activation import (
    NegotiationProposalPromotionActivationError,
    build_evidence,
    canonical_sha256,
    sha256_file,
    validate_reviewed_rollout,
    validate_runtime_manifest,
    validate_staging,
    validate_transaction_authority_manifest,
)


NOW = datetime(2026, 9, 29, 0, 30, tzinfo=timezone.utc)
REVISION = "a" * 40


def rollout():
    value = json.loads(
        Path("docs/cohort-rollout.template.json").read_text(encoding="utf-8")
    )
    value["action_providers"] = ["google"]
    for key in (
        "actions",
        "connector_trust_boundary",
        "personal_transactions",
        "agent_runtime",
        "intelligent_planner",
        "action_proposals",
        "negotiation_proposal_promotion",
    ):
        value["capabilities"][key] = True
    value["transaction_operations"] = [
        "google:negotiation_commitment_email"
    ]
    value["monitoring"]["actions"] = "actions-dashboard"
    value["incident"]["change_reference"] = "pa09-promotion-change-1"
    return value


def staging():
    verified_at = (NOW - timedelta(minutes=20)).isoformat()
    return {
        "negotiation_proposal_promotion": {
            "status": "passed",
            "evidence": (
                "qualified negotiation proposal promotion operations: "
                "google:negotiation_commitment_email"
            ),
            "verified_at": verified_at,
            "operation_evidence": {
                "google:negotiation_commitment_email": {
                    "evidence": (
                        "live exact-hash history-bound promotion remained "
                        "unapproved and failed closed after source change"
                    ),
                    "verified_at": verified_at,
                }
            },
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


def test_reviewed_rollout_requires_all_promotion_prerequisites_and_kill_switch():
    reviewed = validate_reviewed_rollout(
        rollout(),
        max_cohort_users=25,
    )
    assert reviewed["capabilities"]["negotiation_proposal_promotion"] is True
    assert reviewed["capabilities"]["action_proposals"] is True
    assert reviewed["capabilities"]["personal_transactions"] is True

    broken = rollout()
    broken["capabilities"]["action_proposals"] = False
    with pytest.raises(NegotiationProposalPromotionActivationError):
        validate_reviewed_rollout(broken, max_cohort_users=25)

    broken = rollout()
    broken["rollback"]["negotiation_proposal_promotion_kill_switch"] = "wrong"
    with pytest.raises(
        NegotiationProposalPromotionActivationError,
        match="kill[_ ]switch",
    ):
        validate_reviewed_rollout(broken, max_cohort_users=25)


def test_staging_requires_exact_operation_evidence_and_freshness():
    verified = validate_staging(
        staging(),
        expected_operations=["google:negotiation_commitment_email"],
        now=NOW,
        max_age_minutes=60,
    )
    assert verified == NOW - timedelta(minutes=20)

    stale = staging()
    old = (NOW - timedelta(hours=2)).isoformat()
    stale["negotiation_proposal_promotion"]["operation_evidence"][
        "google:negotiation_commitment_email"
    ]["verified_at"] = old
    with pytest.raises(
        NegotiationProposalPromotionActivationError,
        match="stale",
    ):
        validate_staging(
            stale,
            expected_operations=["google:negotiation_commitment_email"],
            now=NOW,
            max_age_minutes=60,
        )

    with pytest.raises(
        NegotiationProposalPromotionActivationError,
        match="allowlist",
    ):
        validate_staging(
            staging(),
            expected_operations=[
                "google:negotiation_commitment_email",
                "microsoft:negotiation_commitment_email",
            ],
            now=NOW,
            max_age_minutes=60,
        )


def test_runtime_and_transaction_authority_must_exactly_match_reviewed_rollout():
    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    deployment = {"source_revision": REVISION}

    normalized = validate_runtime_manifest(
        runtime(reviewed),
        deployment=deployment,
        rollout=reviewed,
    )
    assert normalized["capabilities"]["negotiation_proposal_promotion"] is True

    changed = runtime(reviewed)
    changed["capabilities"] = dict(changed["capabilities"])
    changed["capabilities"]["negotiation_proposal_promotion"] = False
    with pytest.raises(
        NegotiationProposalPromotionActivationError,
        match="capability",
    ):
        validate_runtime_manifest(
            changed,
            deployment=deployment,
            rollout=reviewed,
        )

    authority = validate_transaction_authority_manifest(
        transaction_authority(reviewed),
        deployment=deployment,
        rollout=reviewed,
    )
    assert authority["operations"] == [
        "google:negotiation_commitment_email"
    ]

    changed_authority = copy.deepcopy(transaction_authority(reviewed))
    changed_authority["operations"] = []
    with pytest.raises(
        NegotiationProposalPromotionActivationError,
        match="operations",
    ):
        validate_transaction_authority_manifest(
            changed_authority,
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
        (
            status_path,
            {
                "release_id": "coworker-cohort-001",
                "generated_at": NOW.isoformat(),
            },
        ),
    ):
        path.write_text(json.dumps(value), encoding="utf-8")

    reviewed = validate_reviewed_rollout(rollout(), max_cohort_users=25)
    deployed = {
        "release_id": "coworker-cohort-001",
        "change_reference": "pa09-promotion-change-1",
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
    assert evidence["status"] == "negotiation_proposal_promotion_verified"
    assert evidence["runtime_manifest_sha256"] == canonical_sha256(
        evidence["runtime"]
    )
    assert evidence["transaction_authority_manifest_sha256"] == canonical_sha256(
        evidence["transaction_authority"]
    )
    assert evidence["artifact_sha256"] == {
        "staging_evidence": sha256_file(staging_path),
        "rollout_manifest": sha256_file(rollout_path),
        "deployment_change": sha256_file(deployment_path),
        "operator_status": sha256_file(status_path),
    }
