from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.cohort_release_ledger import (
    PERSONAL_TRANSACTIONS_SCHEMA_VERSION,
    RESTAURANT_RESERVATIONS_SCHEMA_VERSION,
    append_event,
    append_personal_transactions_event,
    append_transaction_capability_event,
    canonical,
    file_sha256,
    read_entries,
    verify_entries,
)
from scripts.release_contract import normalize_capabilities


KEY = b"k" * 32
RELEASE = "coworker-cohort-001"
CHANGE = "pa09-change-1"
STAGE = "canary-5"
REVISION = "a" * 40


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def reviewed_rollout(tmp_path: Path) -> Path:
    value = json.loads(Path("docs/cohort-rollout.template.json").read_text(encoding="utf-8"))
    value["release_id"] = RELEASE
    value["action_providers"] = ["google"]
    value["capabilities"]["actions"] = True
    value["capabilities"]["connector_trust_boundary"] = True
    value["capabilities"]["personal_transactions"] = True
    value["transaction_operations"] = ["google:negotiation_commitment_email"]
    value["monitoring"]["actions"] = "actions-dashboard"
    value["incident"]["change_reference"] = CHANGE
    return write_json(tmp_path / "rollout.json", value)


def seed_ledger(tmp_path: Path, ledger: Path, rollout: Path) -> None:
    plan = write_json(tmp_path / "plan.json", {
        "release_id": RELEASE,
        "stages": [{"name": STAGE}, {"name": "cohort-25"}],
    })
    progression = write_json(tmp_path / "progression.json", {
        "release_id": RELEASE,
        "decision": "HOLD",
        "current_stage": STAGE,
        "next_stage": "cohort-25",
    })
    status = write_json(tmp_path / "seed-status.json", {
        "release_id": RELEASE,
        "decision": "CONTINUE_COHORT",
    })
    append_event(
        ledger=ledger,
        key=KEY,
        release_id=RELEASE,
        event_type="hold",
        actor_reference="operator",
        change_reference=CHANGE,
        current_stage=STAGE,
        next_stage="cohort-25",
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=status,
        created_at="2026-09-28T10:00:00+00:00",
    )


def test_append_personal_transactions_event_binds_activation_and_verifies(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    rollout = reviewed_rollout(tmp_path)
    seed_ledger(tmp_path, ledger, rollout)

    staging = write_json(tmp_path / "staging.json", {
        "personal_transactions": {
            "status": "passed",
            "evidence": "qualified transaction operations: google:negotiation_commitment_email",
            "verified_at": "2026-09-28T10:10:00+00:00",
            "operation_evidence": {
                "google:negotiation_commitment_email": {
                    "evidence": "live exact-term synthetic negotiation commitment passed",
                    "verified_at": "2026-09-28T10:10:00+00:00",
                }
            },
        }
    })
    deployment = write_json(tmp_path / "deployment.json", {
        "release_id": RELEASE,
        "change_reference": CHANGE,
        "current_stage": STAGE,
        "deployed_at": "2026-09-28T10:20:00+00:00",
        "source_revision": REVISION,
        "staging_evidence_sha256": file_sha256(staging),
        "rollout_manifest_sha256": file_sha256(rollout),
    })
    operator = write_json(tmp_path / "operator.json", {
        "release_id": RELEASE,
        "decision": "CONTINUE_COHORT",
        "breaches": [],
        "generated_at": "2026-09-28T10:25:00+00:00",
    })
    rollout_value = json.loads(rollout.read_text(encoding="utf-8"))
    runtime = {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": "production",
        "capabilities": normalize_capabilities(rollout_value["capabilities"]),
        "action_providers": ["google"],
        "cohort": {"enforced": True, "configured_members": 5, "max_users": 25},
    }
    transaction_authority = {
        "schema_version": 1,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "operations": ["google:negotiation_commitment_email"],
    }
    activation = write_json(tmp_path / "activation.json", {
        "schema_version": 1,
        "status": "personal_transactions_verified",
        "release_id": RELEASE,
        "current_stage": STAGE,
        "verified_at": "2026-09-28T10:26:00+00:00",
        "change_reference": CHANGE,
        "deployed_at": "2026-09-28T10:20:00+00:00",
        "source_revision": REVISION,
        "operator_status_generated_at": "2026-09-28T10:25:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": hashlib.sha256(canonical(runtime)).hexdigest(),
        "transaction_authority": transaction_authority,
        "transaction_authority_manifest_sha256": hashlib.sha256(
            canonical(transaction_authority)
        ).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging),
            "rollout_manifest": file_sha256(rollout),
            "deployment_change": file_sha256(deployment),
            "operator_status": file_sha256(operator),
        },
    })

    entry = append_personal_transactions_event(
        ledger=ledger,
        key=KEY,
        release_id=RELEASE,
        actor_reference="security-reviewer",
        change_reference=CHANGE,
        current_stage=STAGE,
        staging_evidence=staging,
        rollout_manifest=rollout,
        deployment_change=deployment,
        operator_status=operator,
        personal_transactions_activation=activation,
        created_at="2026-09-28T10:30:00+00:00",
    )
    assert entry["schema_version"] == PERSONAL_TRANSACTIONS_SCHEMA_VERSION
    assert entry["event_type"] == "personal_transactions_verified"
    assert entry["artifact_sha256"]["personal_transactions_activation"] == file_sha256(activation)
    state = verify_entries(read_entries(ledger), KEY)
    assert state["entries"] == 2
    assert state["head_entry_hash"] == entry["entry_hash"]



def test_restaurant_transaction_capability_chains_after_personal_transactions(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    base_rollout = reviewed_rollout(tmp_path)
    seed_ledger(tmp_path, ledger, base_rollout)

    personal_staging = write_json(tmp_path / "personal-staging.json", {
        "personal_transactions": {
            "status": "passed",
            "evidence": "qualified transaction operations: google:negotiation_commitment_email",
            "verified_at": "2026-09-28T10:10:00+00:00",
            "operation_evidence": {
                "google:negotiation_commitment_email": {
                    "evidence": "live exact-term synthetic negotiation commitment passed",
                    "verified_at": "2026-09-28T10:10:00+00:00",
                }
            },
        }
    })
    personal_deployment = write_json(tmp_path / "personal-deployment.json", {
        "release_id": RELEASE,
        "change_reference": CHANGE,
        "current_stage": STAGE,
        "deployed_at": "2026-09-28T10:20:00+00:00",
        "source_revision": REVISION,
        "staging_evidence_sha256": file_sha256(personal_staging),
        "rollout_manifest_sha256": file_sha256(base_rollout),
    })
    personal_operator = write_json(tmp_path / "personal-operator.json", {
        "release_id": RELEASE,
        "decision": "CONTINUE_COHORT",
        "breaches": [],
        "generated_at": "2026-09-28T10:25:00+00:00",
    })
    base_value = json.loads(base_rollout.read_text(encoding="utf-8"))
    base_runtime = {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": "production",
        "capabilities": normalize_capabilities(base_value["capabilities"]),
        "action_providers": ["google"],
        "cohort": {"enforced": True, "configured_members": 5, "max_users": 25},
    }
    base_authority = {
        "schema_version": 1,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "operations": ["google:negotiation_commitment_email"],
    }
    personal_activation = write_json(tmp_path / "personal-activation.json", {
        "schema_version": 1,
        "status": "personal_transactions_verified",
        "release_id": RELEASE,
        "current_stage": STAGE,
        "verified_at": "2026-09-28T10:26:00+00:00",
        "change_reference": CHANGE,
        "deployed_at": "2026-09-28T10:20:00+00:00",
        "source_revision": REVISION,
        "operator_status_generated_at": "2026-09-28T10:25:00+00:00",
        "runtime": base_runtime,
        "runtime_manifest_sha256": hashlib.sha256(canonical(base_runtime)).hexdigest(),
        "transaction_authority": base_authority,
        "transaction_authority_manifest_sha256": hashlib.sha256(
            canonical(base_authority)
        ).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": file_sha256(personal_staging),
            "rollout_manifest": file_sha256(base_rollout),
            "deployment_change": file_sha256(personal_deployment),
            "operator_status": file_sha256(personal_operator),
        },
    })
    append_personal_transactions_event(
        ledger=ledger,
        key=KEY,
        release_id=RELEASE,
        actor_reference="security-reviewer",
        change_reference=CHANGE,
        current_stage=STAGE,
        staging_evidence=personal_staging,
        rollout_manifest=base_rollout,
        deployment_change=personal_deployment,
        operator_status=personal_operator,
        personal_transactions_activation=personal_activation,
        created_at="2026-09-28T10:30:00+00:00",
    )

    restaurant_rollout_value = json.loads(
        Path("docs/cohort-rollout.template.json").read_text(encoding="utf-8")
    )
    restaurant_rollout_value["release_id"] = RELEASE
    restaurant_rollout_value["action_providers"] = ["google", "opentable"]
    restaurant_rollout_value["transaction_operations"] = [
        "opentable:restaurant_reservation_create"
    ]
    restaurant_rollout_value["capabilities"]["actions"] = True
    restaurant_rollout_value["capabilities"]["connector_trust_boundary"] = True
    restaurant_rollout_value["capabilities"]["personal_transactions"] = True
    restaurant_rollout_value["capabilities"]["restaurant_reservations"] = True
    restaurant_rollout_value["monitoring"]["actions"] = "actions-dashboard"
    restaurant_rollout_value["incident"]["change_reference"] = "restaurant-change"
    restaurant_rollout = write_json(
        tmp_path / "restaurant-rollout.json",
        restaurant_rollout_value,
    )
    restaurant_staging = write_json(tmp_path / "restaurant-staging.json", {
        "restaurant_reservations": {
            "status": "passed",
            "evidence": "OpenTable controlled-staging reservation passed",
            "verified_at": "2026-09-28T10:35:00+00:00",
            "operation": "opentable:restaurant_reservation_create",
            "provider_evidence_sha256": "b" * 64,
        }
    })
    restaurant_deployment = write_json(tmp_path / "restaurant-deployment.json", {
        "release_id": RELEASE,
        "change_reference": "restaurant-change",
        "current_stage": STAGE,
        "deployed_at": "2026-09-28T10:40:00+00:00",
        "source_revision": REVISION,
        "staging_evidence_sha256": file_sha256(restaurant_staging),
        "rollout_manifest_sha256": file_sha256(restaurant_rollout),
    })
    restaurant_operator = write_json(tmp_path / "restaurant-operator.json", {
        "release_id": RELEASE,
        "decision": "CONTINUE_COHORT",
        "breaches": [],
        "generated_at": "2026-09-28T10:45:00+00:00",
    })
    runtime = {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": "production",
        "capabilities": normalize_capabilities(
            restaurant_rollout_value["capabilities"]
        ),
        "action_providers": ["google", "opentable"],
        "cohort": {"enforced": True, "configured_members": 5, "max_users": 25},
    }
    authority = {
        "schema_version": 2,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "restaurant_reservations_enabled": True,
        "shopping_checkout_enabled": False,
        "travel_booking_enabled": False,
        "operations": ["opentable:restaurant_reservation_create"],
    }
    activation_value = {
        "schema_version": 1,
        "status": "restaurant_reservations_verified",
        "capability": "restaurant_reservations",
        "operation": "opentable:restaurant_reservation_create",
        "provider_evidence_sha256": "b" * 64,
        "release_id": RELEASE,
        "current_stage": STAGE,
        "verified_at": "2026-09-28T10:46:00+00:00",
        "change_reference": "restaurant-change",
        "deployed_at": "2026-09-28T10:40:00+00:00",
        "source_revision": REVISION,
        "operator_status_generated_at": "2026-09-28T10:45:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": hashlib.sha256(canonical(runtime)).hexdigest(),
        "transaction_authority": authority,
        "transaction_authority_manifest_sha256": hashlib.sha256(
            canonical(authority)
        ).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": file_sha256(restaurant_staging),
            "rollout_manifest": file_sha256(restaurant_rollout),
            "deployment_change": file_sha256(restaurant_deployment),
            "operator_status": file_sha256(restaurant_operator),
        },
    }
    activation_value["activation_sha256"] = hashlib.sha256(
        canonical(activation_value)
    ).hexdigest()
    restaurant_activation = write_json(
        tmp_path / "restaurant-activation.json",
        activation_value,
    )

    entry = append_transaction_capability_event(
        ledger=ledger,
        key=KEY,
        capability="restaurant_reservations",
        release_id=RELEASE,
        actor_reference="release-engineer",
        change_reference="restaurant-change",
        current_stage=STAGE,
        staging_evidence=restaurant_staging,
        rollout_manifest=restaurant_rollout,
        deployment_change=restaurant_deployment,
        operator_status=restaurant_operator,
        activation_evidence=restaurant_activation,
        created_at="2026-09-28T10:50:00+00:00",
    )
    assert entry["schema_version"] == RESTAURANT_RESERVATIONS_SCHEMA_VERSION
    assert entry["event_type"] == "restaurant_reservations_verified"
    assert verify_entries(read_entries(ledger), KEY)["entries"] == 3
