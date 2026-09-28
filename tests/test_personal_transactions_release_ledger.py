from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.cohort_release_ledger import (
    PERSONAL_TRANSACTIONS_SCHEMA_VERSION,
    append_event,
    append_personal_transactions_event,
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
            "evidence": "live exact-term synthetic negotiation commitment passed",
            "verified_at": "2026-09-28T10:10:00+00:00",
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
