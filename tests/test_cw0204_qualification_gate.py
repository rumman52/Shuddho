"""Synthetic CW-02–04 signed-evidence tests. Passing does NOT certify staging."""
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.cw0204_qualification_gate import (
    INFRASTRUCTURE, WORKFLOWS, canonical_bytes, fault_tree_sha256,
    qualify_release, read_json_file, sha256, validate_checkpoint,
)
from scripts.transaction_chaos_matrix import SCENARIOS

REV = "a" * 40
ROLLOUT = "synthetic-release-42"
OBSERVED = "2026-10-12T09:00:00Z"
ATTESTED = "2026-10-12T10:00:00Z"


def _save(path, value):
    path.write_bytes(canonical_bytes(value))


def _checkpoint():
    api = {"status": "passed", "source_revision": REV, "deployment_id": "synthetic-api-01", "observed_at": OBSERVED}
    worker = {"status": "passed", "source_revision": REV, "deployment_id": "synthetic-worker-01", "observed_at": OBSERVED}
    return {
        "schema_version": 1, "environment": "staging", "source_revision": REV, "rollout_id": ROLLOUT,
        "deployments": {"api": api, "worker": worker},
        "infrastructure": {name: {"status": "passed", "observation_ref": "synthetic-" + name}
                           for name in INFRASTRUCTURE},
        "workflows": [{
            "id": name, "test_run_id": "synthetic-workflow-" + name, "observed_at": OBSERVED,
            "result": "passed", "source_revision": REV, "rollout_id": ROLLOUT,
            "api_deployment_id": api["deployment_id"], "worker_deployment_id": worker["deployment_id"],
            "evidence_sha256": "b" * 64, "observation_ref": "synthetic-" + name,
        } for name in sorted(WORKFLOWS)],
    }


def _bundle(folder):
    directory = folder / "evidence"
    directory.mkdir()
    no_dispatch = {"model_429", "model_500", "model_timeout", "approval_after_expiration"}
    no_applied = no_dispatch | {"provider_401", "provider_403"}
    entries = []
    for i, name in enumerate(SCENARIOS):
        attempted = 0 if name in no_dispatch else 1
        applied = 0 if name in no_applied else 1
        outcome = "blocked" if name in no_applied else "recovered"
        body = {
            "scenario_id": name, "source_revision": REV, "rollout_id": ROLLOUT,
            "test_run_id": f"synthetic-{i}", "observed_at": OBSERVED,
            "attempted_mutations": attempted, "applied_mutations": applied, "outcome": outcome,
            "provider_observation_source": "provider_sandbox",
            "provider_observation_reference": "synthetic-" + str(i),
        }
        raw = canonical_bytes(body)
        (directory / (name + ".json")).write_bytes(raw)
        entries.append({
            "id": name, "result": "passed", "environment": "staging",
            "test_run_id": body["test_run_id"], "evidence_sha256": sha256(raw),
            "operator": "synthetic-ci", "observed_at": OBSERVED,
            "attempted_mutations": attempted, "applied_mutations": applied,
            "outcome": outcome, "evidence_file": name + ".json",
        })
    _save(folder / "manifest.json", {
        "schema_version": 1, "source_revision": REV, "rollout_id": ROLLOUT, "scenarios": entries,
    })
    _save(folder / "checkpoint.json", _checkpoint())
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    (folder / "pub.pem").write_bytes(pub.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    witness = {
        "schema_version": 1, "role": "independent_release_reviewer",
        "reviewer_id": "synthetic-reviewer", "attested_at": ATTESTED,
        "source_revision": REV, "rollout_id": ROLLOUT,
        "manifest_sha256": sha256((folder / "manifest.json").read_bytes()),
        "checkpoint_sha256": sha256((folder / "checkpoint.json").read_bytes()),
        "evidence_tree_sha256": fault_tree_sha256(directory),
    }
    witness["signature_base64"] = base64.b64encode(key.sign(canonical_bytes(witness))).decode()
    _save(folder / "witness.json", witness)
    return {
        "manifest_path": folder / "manifest.json",
        "checkpoint_path": folder / "checkpoint.json",
        "evidence_dir": directory,
        "attestation_path": folder / "witness.json",
        "trusted_public_key": folder / "pub.pem",
        "trusted_key_sha256": sha256(der),
        "source_revision": REV, "rollout_id": ROLLOUT,
    }


def test_synthetic_bundle_consistency_not_live_evidence(tmp_path):
    assert qualify_release(**_bundle(tmp_path)) == []


def test_witness_required(tmp_path):
    args = _bundle(tmp_path)
    args["attestation_path"].unlink()
    assert qualify_release(**args)


def test_foreign_reviewer_key_fails_pinned_fingerprint(tmp_path):
    args = _bundle(tmp_path)
    fake = Ed25519PrivateKey.generate().public_key()
    args["trusted_public_key"].write_bytes(fake.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    assert any("fingerprint" in value for value in qualify_release(**args))


def test_tampered_witness_rejected(tmp_path):
    args = _bundle(tmp_path)
    obj = json.loads(args["attestation_path"].read_bytes())
    obj["reviewer_id"] = "substituted-operator"
    _save(args["attestation_path"], obj)
    assert any("signature invalid" in value for value in qualify_release(**args))


def test_tampered_checkpoint_fails_frozen_hash(tmp_path):
    args = _bundle(tmp_path)
    obj = json.loads(args["checkpoint_path"].read_bytes())
    obj["workflows"][0]["observation_ref"] = "replaced"
    _save(args["checkpoint_path"], obj)
    assert any("checkpoint_sha256 mismatch" in value for value in qualify_release(**args))


def test_changed_fault_file_fails_evidence_hash(tmp_path):
    args = _bundle(tmp_path)
    target = args["evidence_dir"] / "provider_500.json"
    target.write_bytes(target.read_bytes() + b" ")
    assert any("hash mismatch" in value for value in qualify_release(**args))


def test_wrong_deployment_revision_rejected(tmp_path):
    args = _bundle(tmp_path)
    obj = json.loads(args["checkpoint_path"].read_bytes())
    obj["deployments"]["worker"]["source_revision"] = "c" * 40
    _save(args["checkpoint_path"], obj)
    assert any("worker:" in value for value in qualify_release(**args))


def test_missing_workflow_denied(tmp_path):
    args = _bundle(tmp_path)
    obj = json.loads(args["checkpoint_path"].read_bytes())
    obj["workflows"].pop()
    _save(args["checkpoint_path"], obj)
    assert any("CW-04" in value for value in qualify_release(**args))


def test_duplicate_workflow_run_id_denied():
    obj = _checkpoint()
    obj["workflows"][1]["test_run_id"] = obj["workflows"][0]["test_run_id"]
    assert any("reused" in e for e in validate_checkpoint(obj, source_revision=REV, rollout_id=ROLLOUT))


def test_missing_storage_prerequisite_denied():
    obj = _checkpoint()
    obj["infrastructure"]["private_storage"]["status"] = "pending"
    assert any("private_storage" in e for e in validate_checkpoint(obj, source_revision=REV, rollout_id=ROLLOUT))


def test_duplicate_json_key_denied(tmp_path):
    file = tmp_path / "duplicate.json"
    file.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        read_json_file(file)


def test_witness_before_observations_denied(tmp_path):
    args = _bundle(tmp_path)
    obj = json.loads(args["attestation_path"].read_bytes())
    obj["attested_at"] = "2026-10-12T08:00:00Z"
    _save(args["attestation_path"], obj)
    assert any("reviewer signed before" in e for e in qualify_release(**args))


def test_invalid_git_sha_denied():
    assert any("revision" in e for e in validate_checkpoint(
        _checkpoint(), source_revision="invalid", rollout_id=ROLLOUT,
    ))


def test_bogus_manifest_rollout_denied(tmp_path):
    args = _bundle(tmp_path)
    args["rollout_id"] = "wrong-release"
    assert qualify_release(**args)
