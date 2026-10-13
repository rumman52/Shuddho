"""Offline contract regressions only: synthetic attestations are NOT live CW-09 evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.cohort_release_ledger import (
    AGENT_BROWSER_READ_SCHEMA_VERSION,
    ReleaseLedgerError,
    append_agent_browser_read_event,
    canonical,
    read_entries,
    sign_entry,
    verify_entries,
)
from scripts.release_contract import normalize_capabilities

KEY = b"w" * 32
RELEASE_ID = "cw09-review-001"
STAGE = "canary-5"
REV = "a" * 40


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path):
    # A fully signed synthetic genesis; never use fixture values as release proof.
    seed = {
        "schema_version": 1,
        "sequence": 1,
        "created_at": "2026-10-14T00:00:00+00:00",
        "release_id": RELEASE_ID,
        "event_type": "hold",
        "actor_reference": "synthetic-test-operator",
        "change_reference": "synthetic-first-stage",
        "current_stage": STAGE,
        "next_stage": None,
        "artifact_sha256": {
            "rollout_manifest": "a" * 64,
            "canary_plan": "b" * 64,
            "progression_decision": "c" * 64,
            "operator_status": "d" * 64,
        },
        "previous_entry_hash": "0" * 64,
    }
    head, tag = sign_entry(seed, KEY)
    ledger = write(tmp_path / "ledger.jsonl", {})  # overwritten with one JSONL row
    ledger.write_text(json.dumps({
        **seed, "entry_hash": head, "hmac_sha256": tag,
    }) + "\n", encoding="utf-8")

    flags = {
        "coworker": True, "agent_browser_read": True, "browser": True,
        "runtime_v3": True, "connector_trust_boundary": True,
    }
    rollout = write(tmp_path / "rollout.json", {
        "release_id": RELEASE_ID, "environment": "production",
        "capabilities": flags, "cohort": {"max_users": 5},
        "action_providers": [],
        "rollback": {"agent_browser_read_kill_switch": "SHUDDHO_AGENT_BROWSER_READ_ENABLED=false"},
    })
    staged = write(tmp_path / "staging.json", {
        "agent_browser_read": {
            "status": "passed", "evidence": "synthetic-only: no real worker used",
            "verified_at": "2026-10-14T00:05:00+00:00",
        }
    })
    deployment = write(tmp_path / "deployment.json", {
        "release_id": RELEASE_ID, "source_revision": REV,
        "current_stage": STAGE, "change_reference": "synthetic-change",
        "deployed_at": "2026-10-14T00:06:00+00:00",
        "staging_evidence_sha256": digest(staged),
        "rollout_manifest_sha256": digest(rollout),
    })
    status = write(tmp_path / "status.json", {
        "release_id": RELEASE_ID, "decision": "CONTINUE_COHORT",
        "breaches": [], "generated_at": "2026-10-14T00:07:00+00:00",
    })
    runtime = {
        "schema_version": 1, "source_revision": REV,
        "environment": "production", "capabilities": flags,
        "action_providers": [], "cohort": {
            "enforced": True, "configured_members": 5, "max_users": 5,
        },
    }
    activation = {
        "release_id": RELEASE_ID, "status": "agent_browser_read_verified",
        "current_stage": STAGE, "change_reference": "synthetic-change",
        "source_revision": REV, "deployed_at": "2026-10-14T00:06:00+00:00",
        "operator_status_generated_at": "2026-10-14T00:07:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": hashlib.sha256(canonical(runtime)).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": digest(staged),
            "rollout_manifest": digest(rollout),
            "deployment_change": digest(deployment),
            "operator_status": digest(status),
        },
    }
    activation["activation_sha256"] = hashlib.sha256(canonical(activation)).hexdigest()
    approved = write(tmp_path / "activation.json", activation)
    return {
        "ledger": ledger, "key": KEY, "release_id": RELEASE_ID,
        "actor_reference": "synthetic-operator",
        "change_reference": "synthetic-change", "current_stage": STAGE,
        "staging_evidence": staged, "rollout_manifest": rollout,
        "deployment_change": deployment, "operator_status": status,
        "activation_evidence": approved,
    }


def test_schema34_agent_browser_read_attestation_round_trips_through_hmac_ledger(tmp_path):
    args = fixture(tmp_path)
    entry = append_agent_browser_read_event(**args)
    assert entry["schema_version"] == AGENT_BROWSER_READ_SCHEMA_VERSION == 34
    assert entry["event_type"] == "agent_browser_read_verified"
    assert set(entry["artifact_sha256"]) == {
        "staging_evidence", "rollout_manifest", "deployment_change",
        "operator_status", "agent_browser_read_activation",
    }
    assert verify_entries(read_entries(args["ledger"]), KEY)["entries"] == 2
    with pytest.raises(ReleaseLedgerError, match="already been recorded"):
        append_agent_browser_read_event(**args)


def test_schema34_denies_unverified_or_modified_authority_without_ledger_append(tmp_path):
    for case in ("staging_pending", "missing_browser_dependency", "runtime_switched_off", "invalid_activation_hash"):
        root = tmp_path / case
        root.mkdir()
        args = fixture(root)
        if case == "staging_pending":
            stage = json.loads(args["staging_evidence"].read_text())
            stage["agent_browser_read"]["status"] = "pending"
            write(args["staging_evidence"], stage)
        elif case == "missing_browser_dependency":
            rollout = json.loads(args["rollout_manifest"].read_text())
            rollout["capabilities"]["browser"] = False
            write(args["rollout_manifest"], rollout)
        else:
            activation = json.loads(args["activation_evidence"].read_text())
            if case == "runtime_switched_off":
                activation["runtime"]["capabilities"]["agent_browser_read"] = False
                activation["runtime_manifest_sha256"] = hashlib.sha256(canonical(activation["runtime"])).hexdigest()
                activation.pop("activation_sha256")
                activation["activation_sha256"] = hashlib.sha256(canonical(activation)).hexdigest()
            else:
                activation["activation_sha256"] = "0" * 64
            write(args["activation_evidence"], activation)
        with pytest.raises(ReleaseLedgerError):
            append_agent_browser_read_event(**args)
        assert verify_entries(read_entries(args["ledger"]), KEY)["entries"] == 1


def test_schema34_rejects_wrong_event_or_artifact_shape_even_if_signed(tmp_path):
    args = fixture(tmp_path)
    entry = append_agent_browser_read_event(**args)
    original = read_entries(args["ledger"])
    for tamper in ("event", "artifacts"):
        altered = dict(entry)
        if tamper == "event":
            altered["event_type"] = "browser_verified"
        else:
            altered["artifact_sha256"] = {
                **entry["artifact_sha256"], "unexpected_grant": "f" * 64,
            }
        head, tag = sign_entry({
            key: value for key, value in altered.items()
            if key not in {"entry_hash", "hmac_sha256"}
        }, KEY)
        altered.update(entry_hash=head, hmac_sha256=tag)
        with pytest.raises(ReleaseLedgerError):
            verify_entries([original[0], altered], KEY)


@pytest.mark.parametrize("invalid", [
    "missing_rollout_binding",
    "wrong_rollout_binding",
    "operator_before_deployment",
    "invalid_status_time",
    "rollback_missing",
    "rollback_wrong",
])
def test_agent_browser_read_denies_mismatched_operated_release_evidence(tmp_path, invalid):
    args = fixture(tmp_path)
    if invalid in {"missing_rollout_binding", "wrong_rollout_binding"}:
        deployment = json.loads(args["deployment_change"].read_text())
        if invalid == "missing_rollout_binding":
            deployment.pop("rollout_manifest_sha256")
        else:
            deployment["rollout_manifest_sha256"] = "f" * 64
        write(args["deployment_change"], deployment)
    elif invalid in {"operator_before_deployment", "invalid_status_time"}:
        status = json.loads(args["operator_status"].read_text())
        status["generated_at"] = (
            "2026-10-14T00:04:00+00:00"
            if invalid == "operator_before_deployment" else "2026-10-14T00:07:00"
        )
        write(args["operator_status"], status)
        activation = json.loads(args["activation_evidence"].read_text())
        activation["operator_status_generated_at"] = status["generated_at"]
        activation["artifact_sha256"]["operator_status"] = digest(args["operator_status"])
        activation.pop("activation_sha256")
        activation["activation_sha256"] = hashlib.sha256(canonical(activation)).hexdigest()
        write(args["activation_evidence"], activation)
    else:
        rollout = json.loads(args["rollout_manifest"].read_text())
        if invalid == "rollback_missing":
            rollout.pop("rollback")
        else:
            rollout["rollback"]["agent_browser_read_kill_switch"] = "SHUDDHO_BROWSER_ENABLED=false"
        write(args["rollout_manifest"], rollout)
    with pytest.raises(ReleaseLedgerError):
        append_agent_browser_read_event(**args)
    assert verify_entries(read_entries(args["ledger"]), KEY)["entries"] == 1
