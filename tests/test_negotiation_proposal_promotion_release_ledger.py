from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.cohort_release_ledger import (
    ACTION_PROPOSALS_ARTIFACT_KEYS,
    ACTION_PROPOSALS_SCHEMA_VERSION,
    NEGOTIATION_PROPOSAL_PROMOTION_SCHEMA_VERSION,
    PERSONAL_TRANSACTIONS_ARTIFACT_KEYS,
    PERSONAL_TRANSACTIONS_SCHEMA_VERSION,
    ZERO_HASH,
    ReleaseLedgerError,
    append_negotiation_proposal_promotion_event,
    canonical,
    file_sha256,
    read_entries,
    sign_entry,
    verify_entries,
)
from scripts.release_contract import normalize_capabilities


KEY = b"k" * 32
RELEASE = "coworker-cohort-001"
CHANGE = "pa09-promotion-change-1"
STAGE = "canary-5"
REVISION = "a" * 40
HASH = "b" * 64


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def rollout_value() -> dict:
    value = json.loads(
        Path("docs/cohort-rollout.template.json").read_text(encoding="utf-8")
    )
    value["release_id"] = RELEASE
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
    value["incident"]["change_reference"] = CHANGE
    return value


def signed_dependency(
    *,
    sequence: int,
    previous: str,
    schema_version: int,
    event_type: str,
    artifact_keys: set[str],
) -> dict:
    core = {
        "schema_version": schema_version,
        "sequence": sequence,
        "created_at": f"2026-09-29T00:0{sequence}:00+00:00",
        "release_id": RELEASE,
        "event_type": event_type,
        "actor_reference": "security-reviewer",
        "change_reference": CHANGE,
        "current_stage": STAGE,
        "next_stage": None,
        "artifact_sha256": {
            key: HASH for key in sorted(artifact_keys)
        },
        "previous_entry_hash": previous,
    }
    entry_hash, tag = sign_entry(core, KEY)
    return {
        **core,
        "entry_hash": entry_hash,
        "hmac_sha256": tag,
    }


def seed_dependencies(ledger: Path, *, personal=True) -> None:
    action = signed_dependency(
        sequence=1,
        previous=ZERO_HASH,
        schema_version=ACTION_PROPOSALS_SCHEMA_VERSION,
        event_type="action_proposals_verified",
        artifact_keys=ACTION_PROPOSALS_ARTIFACT_KEYS,
    )
    rows = [action]
    if personal:
        rows.append(
            signed_dependency(
                sequence=2,
                previous=action["entry_hash"],
                schema_version=PERSONAL_TRANSACTIONS_SCHEMA_VERSION,
                event_type="personal_transactions_verified",
                artifact_keys=PERSONAL_TRANSACTIONS_ARTIFACT_KEYS,
            )
        )
    ledger.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    verify_entries(read_entries(ledger), KEY)


def release_files(tmp_path: Path):
    rollout = write_json(tmp_path / "rollout.json", rollout_value())
    staging = write_json(tmp_path / "staging.json", {
        "negotiation_proposal_promotion": {
            "status": "passed",
            "evidence": (
                "qualified negotiation proposal promotion operations: "
                "google:negotiation_commitment_email"
            ),
            "verified_at": "2026-09-29T00:10:00+00:00",
            "operation_evidence": {
                "google:negotiation_commitment_email": {
                    "evidence": "live exact-hash promotion passed",
                    "verified_at": "2026-09-29T00:10:00+00:00",
                }
            },
        }
    })
    deployment = write_json(tmp_path / "deployment.json", {
        "release_id": RELEASE,
        "change_reference": CHANGE,
        "current_stage": STAGE,
        "deployed_at": "2026-09-29T00:20:00+00:00",
        "source_revision": REVISION,
        "staging_evidence_sha256": file_sha256(staging),
        "rollout_manifest_sha256": file_sha256(rollout),
    })
    operator = write_json(tmp_path / "operator.json", {
        "release_id": RELEASE,
        "decision": "CONTINUE_COHORT",
        "breaches": [],
        "generated_at": "2026-09-29T00:25:00+00:00",
    })
    reviewed = rollout_value()
    runtime = {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": "production",
        "capabilities": normalize_capabilities(reviewed["capabilities"]),
        "action_providers": ["google"],
        "cohort": {
            "enforced": True,
            "configured_members": 5,
            "max_users": 25,
        },
    }
    authority = {
        "schema_version": 1,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "operations": ["google:negotiation_commitment_email"],
    }
    activation = write_json(tmp_path / "activation.json", {
        "schema_version": 1,
        "status": "negotiation_proposal_promotion_verified",
        "release_id": RELEASE,
        "current_stage": STAGE,
        "verified_at": "2026-09-29T00:26:00+00:00",
        "change_reference": CHANGE,
        "deployed_at": "2026-09-29T00:20:00+00:00",
        "source_revision": REVISION,
        "operator_status_generated_at": "2026-09-29T00:25:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": hashlib.sha256(canonical(runtime)).hexdigest(),
        "transaction_authority": authority,
        "transaction_authority_manifest_sha256": hashlib.sha256(
            canonical(authority)
        ).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging),
            "rollout_manifest": file_sha256(rollout),
            "deployment_change": file_sha256(deployment),
            "operator_status": file_sha256(operator),
        },
    })
    return staging, rollout, deployment, operator, activation


def append(ledger: Path, files):
    staging, rollout, deployment, operator, activation = files
    return append_negotiation_proposal_promotion_event(
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
        negotiation_proposal_promotion_activation=activation,
        created_at="2026-09-29T00:30:00+00:00",
    )


def test_schema_v27_append_requires_dependencies_and_binds_activation(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    seed_dependencies(ledger)
    files = release_files(tmp_path)

    entry = append(ledger, files)
    assert entry["schema_version"] == NEGOTIATION_PROPOSAL_PROMOTION_SCHEMA_VERSION
    assert entry["event_type"] == "negotiation_proposal_promotion_verified"
    assert entry["artifact_sha256"][
        "negotiation_proposal_promotion_activation"
    ] == file_sha256(files[-1])

    state = verify_entries(read_entries(ledger), KEY)
    assert state["entries"] == 3
    assert state["head_entry_hash"] == entry["entry_hash"]

    with pytest.raises(ReleaseLedgerError, match="already recorded"):
        append(ledger, files)


def test_schema_v27_refuses_missing_personal_transactions_attestation(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    seed_dependencies(ledger, personal=False)
    files = release_files(tmp_path)

    with pytest.raises(
        ReleaseLedgerError,
        match="personal_transactions_verified",
    ):
        append(ledger, files)
