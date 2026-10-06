from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.transaction_capability_activation import (
    TransactionCapabilityActivationError,
    build_evidence,
    canonical_sha256,
    validate_reviewed_rollout,
    validate_runtime_manifest,
    validate_staging,
    validate_transaction_authority,
)


NOW = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
REVISION = "a" * 40
OPERATION = "opentable:restaurant_reservation_create"


def rollout():
    value = json.loads(Path("docs/cohort-rollout.template.json").read_text(encoding="utf-8"))
    value["action_providers"] = ["google", "opentable"]
    value["transaction_operations"] = [OPERATION]
    value["capabilities"]["actions"] = True
    value["capabilities"]["connector_trust_boundary"] = True
    value["capabilities"]["personal_transactions"] = True
    value["capabilities"]["restaurant_reservations"] = True
    value["monitoring"]["actions"] = "actions-dashboard"
    value["incident"]["change_reference"] = "tx28-restaurant"
    return value


def staging():
    return {
        "restaurant_reservations": {
            "status": "passed",
            "evidence": "controlled staging reservation passed",
            "verified_at": (NOW - timedelta(minutes=5)).isoformat(),
            "operation": OPERATION,
            "provider_evidence_sha256": "b" * 64,
        }
    }


def runtime(reviewed):
    return {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": reviewed["environment"],
        "capabilities": reviewed["capabilities"],
        "action_providers": reviewed["action_providers"],
        "cohort": {
            "enforced": True,
            "configured_members": 1,
            "max_users": reviewed["cohort_max_users"],
        },
    }


def authority(reviewed):
    return {
        "schema_version": 2,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "restaurant_reservations_enabled": True,
        "shopping_checkout_enabled": False,
        "travel_booking_enabled": False,
        "operations": reviewed["transaction_operations"],
    }


def test_restaurant_activation_contract_binds_exact_operation_and_runtime(tmp_path):
    reviewed = validate_reviewed_rollout(
        rollout(),
        capability="restaurant_reservations",
        operation=OPERATION,
        max_cohort_users=25,
    )
    verified = validate_staging(
        staging(),
        capability="restaurant_reservations",
        operation=OPERATION,
        now=NOW,
        max_age_minutes=60,
    )
    assert verified == NOW - timedelta(minutes=5)
    assert validate_runtime_manifest(
        runtime(reviewed),
        deployment={"source_revision": REVISION},
        rollout=reviewed,
    )["capabilities"]["restaurant_reservations"] is True
    normalized = validate_transaction_authority(
        authority(reviewed),
        deployment={"source_revision": REVISION},
        rollout=reviewed,
        capability="restaurant_reservations",
    )
    assert normalized["restaurant_reservations_enabled"] is True


def test_nested_transaction_capability_must_be_enabled_in_authority_manifest():
    reviewed = validate_reviewed_rollout(
        rollout(),
        capability="restaurant_reservations",
        operation=OPERATION,
        max_cohort_users=25,
    )
    value = authority(reviewed)
    value["restaurant_reservations_enabled"] = False
    with pytest.raises(TransactionCapabilityActivationError):
        validate_transaction_authority(
            value,
            deployment={"source_revision": REVISION},
            rollout=reviewed,
            capability="restaurant_reservations",
        )


def test_staging_must_bind_provider_evidence_hash():
    value = staging()
    value["restaurant_reservations"]["provider_evidence_sha256"] = "not-a-hash"
    with pytest.raises(TransactionCapabilityActivationError):
        validate_staging(
            value,
            capability="restaurant_reservations",
            operation=OPERATION,
            now=NOW,
            max_age_minutes=60,
        )


def test_shopping_and_travel_rollout_cannot_pass_without_registered_provider_operation():
    for capability, operation in (
        ("shopping_checkout", "merchantx:shopping_checkout_create"),
        ("travel_booking", "travelco:travel_booking_create"),
    ):
        value = rollout()
        value["capabilities"]["restaurant_reservations"] = False
        value["capabilities"][capability] = True
        value["transaction_operations"] = [operation]
        value["action_providers"] = ["google"]
        with pytest.raises(TransactionCapabilityActivationError):
            validate_reviewed_rollout(
                value,
                capability=capability,
                operation=operation,
                max_cohort_users=25,
            )


def test_activation_evidence_hashes_runtime_authority_and_artifacts(tmp_path):
    reviewed = validate_reviewed_rollout(
        rollout(),
        capability="restaurant_reservations",
        operation=OPERATION,
        max_cohort_users=25,
    )
    staging_path = tmp_path / "staging.json"
    rollout_path = tmp_path / "rollout.json"
    deployment_path = tmp_path / "deployment.json"
    operator_path = tmp_path / "operator.json"
    for path, value in (
        (staging_path, staging()),
        (rollout_path, rollout()),
        (deployment_path, {"release_id": "coworker-cohort-001"}),
        (operator_path, {"generated_at": NOW.isoformat()}),
    ):
        path.write_text(json.dumps(value), encoding="utf-8")
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "tx28-restaurant",
        "current_stage": "canary-5",
        "deployed_at": NOW.isoformat(),
        "source_revision": REVISION,
    }
    operator = {"generated_at": NOW.isoformat()}
    evidence = build_evidence(
        capability="restaurant_reservations",
        deployment=deployment,
        staging=staging(),
        staging_path=staging_path,
        rollout_path=rollout_path,
        deployment_path=deployment_path,
        operator_status_path=operator_path,
        runtime=runtime(reviewed),
        transaction_authority=authority(reviewed),
        operator_status=operator,
        now=NOW,
    )
    assert evidence["status"] == "restaurant_reservations_verified"
    assert evidence["provider_evidence_sha256"] == "b" * 64
    assert evidence["runtime_manifest_sha256"] == canonical_sha256(evidence["runtime"])
    assert evidence["transaction_authority_manifest_sha256"] == canonical_sha256(
        evidence["transaction_authority"]
    )
    unsigned = copy.deepcopy(evidence)
    stored = unsigned.pop("activation_sha256")
    assert stored == canonical_sha256(unsigned)
