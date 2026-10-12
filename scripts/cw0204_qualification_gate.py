"""CW-02/03/04 release witness gate. Offline evidence binding; NOT live staging proof.

The trusted reviewer key and its fingerprint must be pinned OUTSIDE the
evidence bundle by release engineering. A valid signature proves approval of
these particular bytes, not that a provider actually performed the operation.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.transaction_chaos_matrix import SCENARIOS, qualify, verify_evidence_files

WORKFLOWS = frozenset(("read", "draft", "goal", "reminder", "worker_restart", "backup_restore", "flag_rollback"))
INFRASTRUCTURE = frozenset(("postgresql", "temporal", "private_storage", "model", "synthetic_identity"))
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
GIT_SHA = re.compile(r"[a-f0-9]{40}\Z")
MAX_BYTES = 2 * 1024 * 1024


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def _pairs(pairs):
    output = {}
    for name, value in pairs:
        if name in output:
            raise ValueError("duplicate JSON object key")
        output[name] = value
    return output


def read_json_file(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("unsafe/missing/oversized JSON file")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError("JSON file size limit")
    result = json.loads(data, object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))
    if not isinstance(result, dict):
        raise ValueError("JSON root must be an object")
    return result, data


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return time.astimezone(timezone.utc) if time.tzinfo and time.utcoffset() is not None else None


def validate_checkpoint(checkpoint, *, source_revision, rollout_id):
    errors = []
    if checkpoint.get("schema_version") != 1 or checkpoint.get("environment") != "staging":
        errors.append("checkpoint schema/environment mismatch")
    if (checkpoint.get("source_revision") != source_revision or
            not GIT_SHA.fullmatch(source_revision) or checkpoint.get("rollout_id") != rollout_id or not rollout_id):
        errors.append("checkpoint exact revision/rollout mismatch")
    deployments = checkpoint.get("deployments")
    deployments = deployments if isinstance(deployments, dict) else {}
    for role in ("api", "worker"):
        item = deployments.get(role)
        if not isinstance(item, dict) or item.get("status") != "passed" or item.get("source_revision") != source_revision:
            errors.append(f"{role}: not deployed/verified at frozen revision")
        elif not isinstance(item.get("deployment_id"), str) or not item["deployment_id"].strip():
            errors.append(f"{role}: missing deployment ID")
        elif not _time(item.get("observed_at")):
            errors.append(f"{role}: missing timezone-aware observation")
    # A workflow cannot qualify a release that was not yet observed deployed.
    # The later of the two API/worker readiness observations is the floor.
    deployment_times = [
        _time(item.get("observed_at"))
        for item in deployments.values()
        if isinstance(item, dict) and _time(item.get("observed_at")) is not None
    ]
    deployment_ready_at = max(deployment_times) if len(deployment_times) == 2 else None
    infrastructure = checkpoint.get("infrastructure")
    infrastructure = infrastructure if isinstance(infrastructure, dict) else {}
    for name in sorted(INFRASTRUCTURE):
        value = infrastructure.get(name)
        if not isinstance(value, dict) or value.get("status") != "passed":
            errors.append(f"{name}: staging prerequisite not passed")
        elif not isinstance(value.get("observation_ref"), str) or not value["observation_ref"].strip():
            errors.append(f"{name}: missing independent observation reference")
    rows = checkpoint.get("workflows")
    if not isinstance(rows, list):
        return errors + ["CW-04 workflows must be a list"]
    if len(rows) != len(WORKFLOWS):
        errors.append("CW-04 requires exactly seven workflow runs")
    seen, run_ids = set(), set()
    for item in rows:
        if not isinstance(item, dict):
            errors.append("CW-04 workflow record must be object")
            continue
        name = item.get("id")
        if not isinstance(name, str) or name not in WORKFLOWS or name in seen:
            errors.append(f"CW-04 duplicate/unknown workflow {name!r}")
            continue
        seen.add(name)
        run_id = item.get("test_run_id")
        if not isinstance(run_id, str) or not run_id or run_id in run_ids:
            errors.append(f"{name}: missing/reused workflow run ID")
        run_ids.add(run_id)
        for key, required in (
            ("source_revision", source_revision), ("rollout_id", rollout_id),
            ("api_deployment_id", deployments.get("api", {}).get("deployment_id") if isinstance(deployments.get("api"), dict) else None),
            ("worker_deployment_id", deployments.get("worker", {}).get("deployment_id") if isinstance(deployments.get("worker"), dict) else None),
        ):
            if not required or item.get(key) != required:
                errors.append(f"{name}: {key} binding mismatch")
        observed_at = _time(item.get("observed_at"))
        if item.get("result") != "passed" or not observed_at:
            errors.append(f"{name}: incomplete workflow observation")
        elif deployment_ready_at is not None and observed_at < deployment_ready_at:
            errors.append(f"{name}: workflow observed before frozen API/worker deployment was ready")
        if not isinstance(item.get("evidence_sha256"), str) or not SHA256.fullmatch(item["evidence_sha256"]):
            errors.append(f"{name}: invalid workflow evidence SHA-256")
        if not isinstance(item.get("observation_ref"), str) or not item["observation_ref"].strip():
            errors.append(f"{name}: missing observer reference")
    for missing in sorted(WORKFLOWS - seen):
        errors.append(f"CW-04 missing workflow {missing}")
    return errors


def fault_tree_sha256(folder):
    """Hash actual bytes of every scenario, not just manifest-provided strings."""
    entries = []
    for name in sorted(SCENARIOS):
        path = folder / (name + ".json")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError(f"{name}: missing/unsafe fault evidence")
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError(f"{name}: oversized fault evidence")
        entries.append({"file": name + ".json", "sha256": sha256(data)})
    return sha256(canonical_bytes(entries))


def verify_workflow_evidence_files(checkpoint, folder):
    """Bind actual CW-04 bytes, exact rollout/run IDs and observer to reviewer approval.

    This is an integrity/consistency check, NOT a claim that observations are
    independently true. Release engineering must inspect source systems.
    """
    errors = []
    if folder.is_symlink() or not folder.is_dir():
        return ["CW-04 workflow evidence directory missing or unsafe"], None
    expected_files = {name + ".json" for name in WORKFLOWS}
    try:
        actual_files = {entry.name for entry in folder.iterdir()}
    except OSError as exc:
        return [f"CW-04 workflow evidence directory unreadable: {exc}"], None
    if actual_files != expected_files:
        errors.append("CW-04 requires exactly seven named workflow evidence files")
    rows = checkpoint.get("workflows")
    if not isinstance(rows, list):
        return errors + ["CW-04 workflows must be a list"], None
    by_name = {
        row["id"]: row for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] in WORKFLOWS
    }
    tree = []
    for name in sorted(WORKFLOWS):
        row = by_name.get(name)
        if row is None:
            errors.append(f"CW-04 {name}: missing manifest row")
            continue
        filename = name + ".json"
        if row.get("evidence_file") != filename:
            errors.append(f"CW-04 {name}: expected evidence_file {filename}")
        try:
            document, raw = read_json_file(folder / filename)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"CW-04 {name}: unreadable/unsafe evidence file: {exc}")
            continue
        digest = sha256(raw)
        tree.append({"file": filename, "sha256": digest})
        if row.get("evidence_sha256") != digest:
            errors.append(f"CW-04 {name}: evidence hash mismatch")
        for field in (
            "id", "source_revision", "rollout_id", "api_deployment_id",
            "worker_deployment_id", "test_run_id", "observed_at", "result",
            "observation_ref",
        ):
            expected = name if field == "id" else row.get(field)
            if document.get(field) != expected:
                errors.append(f"CW-04 {name}: {field} evidence identity mismatch")
        if document.get("environment") != "staging":
            errors.append(f"CW-04 {name}: staging observation required")
        observer = document.get("observation_source")
        if not isinstance(observer, str) or not observer.strip():
            errors.append(f"CW-04 {name}: missing observation source")
    if errors or len(tree) != len(WORKFLOWS):
        return errors or ["CW-04 workflow evidence incomplete"], None
    return [], sha256(canonical_bytes(tree))


def verify_witness(witness, *, pem, trusted_key_sha256, manifest_sha256,
                   checkpoint_sha256, tree_sha256, workflow_tree_sha256, source_revision, rollout_id, latest_observation):
    errors = []
    try:
        key = serialization.load_pem_public_key(pem)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("reviewer key must be Ed25519")
        der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if not isinstance(trusted_key_sha256, str) or not SHA256.fullmatch(trusted_key_sha256) or sha256(der) != trusted_key_sha256:
            raise ValueError("trusted reviewer fingerprint mismatch")
    except (ValueError, TypeError) as exc:
        return [str(exc)]
    required = {
        "schema_version": 1, "role": "independent_release_reviewer",
        "source_revision": source_revision, "rollout_id": rollout_id,
        "manifest_sha256": manifest_sha256, "checkpoint_sha256": checkpoint_sha256,
        "evidence_tree_sha256": tree_sha256,
        "workflow_tree_sha256": workflow_tree_sha256,
    }
    for field, value in required.items():
        if witness.get(field) != value:
            errors.append(f"attestation {field} mismatch")
    signed_at = _time(witness.get("attested_at"))
    if not signed_at:
        errors.append("reviewer timestamp invalid")
    elif latest_observation and signed_at < latest_observation:
        errors.append("reviewer signed before evidence observations completed")
    if not isinstance(witness.get("reviewer_id"), str) or not witness["reviewer_id"].strip():
        errors.append("reviewer ID missing")
    try:
        signature = base64.b64decode(witness.get("signature_base64", ""), validate=True)
        if len(signature) != 64:
            raise ValueError("wrong signature size")
        key.verify(signature, canonical_bytes({k: v for k, v in witness.items() if k != "signature_base64"}))
    except (InvalidSignature, ValueError, TypeError, binascii.Error):
        errors.append("release reviewer signature invalid")
    return errors


def qualify_release(*, manifest_path, checkpoint_path, evidence_dir, workflow_evidence_dir,
                    attestation_path, trusted_public_key, trusted_key_sha256,
                    source_revision, rollout_id):
    try:
        manifest, manifest_raw = read_json_file(manifest_path)
        checkpoint, checkpoint_raw = read_json_file(checkpoint_path)
        witness, _ = read_json_file(attestation_path)
        if trusted_public_key.is_symlink() or not trusted_public_key.is_file() or trusted_public_key.stat().st_size > 8192:
            raise ValueError("unsafe/missing reviewer public key")
        pem = trusted_public_key.read_bytes()
        errors = qualify(manifest, expected_revision=source_revision, expected_rollout=rollout_id)
        errors += verify_evidence_files(manifest, evidence_dir)
        errors += validate_checkpoint(checkpoint, source_revision=source_revision, rollout_id=rollout_id)
        workflow_errors, workflow_tree = verify_workflow_evidence_files(checkpoint, workflow_evidence_dir)
        errors += workflow_errors
        if errors or workflow_tree is None:
            return errors or ["CW-04 workflow evidence incomplete"]
        timestamps = [_time(item.get("observed_at")) for item in manifest["scenarios"] + checkpoint["workflows"]]
        timestamps += [_time(row.get("observed_at")) for row in checkpoint["deployments"].values()]
        latest = max((t for t in timestamps if t is not None), default=None)
        return verify_witness(witness, pem=pem, trusted_key_sha256=trusted_key_sha256,
                              manifest_sha256=sha256(manifest_raw),
                              checkpoint_sha256=sha256(checkpoint_raw),
                              tree_sha256=fault_tree_sha256(evidence_dir),
                              workflow_tree_sha256=workflow_tree,
                              source_revision=source_revision, rollout_id=rollout_id,
                              latest_observation=latest)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"qualification evidence invalid: {exc}"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("manifest", "checkpoint", "evidence-dir", "workflow-evidence-dir", "attestation", "trusted-public-key"):
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--trusted-key-sha256", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--rollout-id", required=True)
    args = parser.parse_args()
    failures = qualify_release(
        manifest_path=args.manifest, checkpoint_path=args.checkpoint,
        evidence_dir=args.evidence_dir, workflow_evidence_dir=args.workflow_evidence_dir,
        attestation_path=args.attestation,
        trusted_public_key=args.trusted_public_key,
        trusted_key_sha256=args.trusted_key_sha256,
        source_revision=args.source_revision, rollout_id=args.rollout_id,
    )
    if failures:
        for error in failures:
            print("NOT QUALIFIED:", error)
        return 1
    print("CW-02–04 signed evidence structure passed; independent real-world staging/provider proof still requires human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
