"""Fail-closed identity reconciliation for Day 2 staging evidence.

This proves only that independently generated private evidence files are
mutually consistent. It does not perform or replace a live worker restart,
model call, storage retrieval, PostgreSQL backup, or isolated restore.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


class Day2AcceptanceFailure(RuntimeError):
    pass


_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_REVISION = re.compile(r"[a-f0-9]{40}\Z")
_BASE_FIELDS = (
    "status", "release_id", "source_revision", "runtime_manifest_sha256",
    "document_id", "document_version_id", "document_sha256",
    "task_id", "workflow_id", "artifact_id", "artifact_sha256",
    "artifact_bytes", "model_attempts", "accounted_tokens",
    "owner_isolation", "artifact_retrieval", "worker",
)
_RECOVERY = ("temporal", "parallel_restart", "fan_in")
_CHECKS = [
    "model", "owner_isolation", "artifact_retrieval", "temporal",
    "worker_heartbeat", "parallel_restart", "fan_in", "backup_restore",
]


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise Day2AcceptanceFailure(f"{label} must be a JSON object.")
    return value


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Day2AcceptanceFailure(f"{label} must be a nonempty string.")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise Day2AcceptanceFailure(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise Day2AcceptanceFailure(f"{label} must include a timezone.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Day2AcceptanceFailure(f"{label} must be a valid ISO-8601 timestamp.") from None
    if parsed.tzinfo is None:
        raise Day2AcceptanceFailure(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise Day2AcceptanceFailure(f"{label} must be a positive integer.")
    return value


def _stage(value: object, label: str, *, release_id: str, revision: str) -> tuple[str, datetime]:
    obj = _object(value, label)
    if obj.get("status") != "passed":
        raise Day2AcceptanceFailure(f"{label} has not passed.")
    if obj.get("source_revision") != revision or obj.get("release_id") != release_id:
        raise Day2AcceptanceFailure(f"{label} does not belong to the frozen source/release.")
    _nonempty(obj.get("evidence"), label + ".evidence")
    digest = _digest(obj.get("rollout_manifest_sha256"), label + ".rollout_manifest_sha256")
    started = _time(obj.get("exercise_started_at"), label + ".exercise_started_at")
    verified = _time(obj.get("verified_at"), label + ".verified_at")
    if verified < started:
        raise Day2AcceptanceFailure(f"{label} verification predates its preparation.")
    return digest, verified


def validate_evidence(
    freeze: object, execution: object, recovery: object, restored: object,
    *, expected_revision: str,
) -> dict:
    """Reject mixed release/worker/task/artifact evidence; never claim live execution."""
    if not isinstance(expected_revision, str) or not _REVISION.fullmatch(expected_revision):
        raise Day2AcceptanceFailure("An exact reviewed 40-character source SHA is required.")
    frozen = _object(freeze, "freeze")
    release = _object(frozen.get("release"), "freeze.release")
    if (frozen.get("status") != "frozen" or release.get("environment") != "staging"
            or release.get("source_revision") != expected_revision):
        raise Day2AcceptanceFailure("The expected source SHA must have a frozen staging release.")
    release_id = _nonempty(release.get("release_id"), "freeze.release.release_id")
    runtime_digest = _digest(frozen.get("runtime_manifest_sha256"), "freeze.runtime_manifest_sha256")

    run = _object(execution, "execution")
    rec = _object(recovery, "recovery")
    restore = _object(restored, "restored")
    if run.get("status") != "passed" or run.get("source_revision") != expected_revision or run.get("release_id") != release_id:
        raise Day2AcceptanceFailure("Document execution is not passed for the frozen release.")
    if run.get("runtime_manifest_sha256") != runtime_digest:
        raise Day2AcceptanceFailure("Document execution does not match the frozen runtime manifest.")
    for key in ("document_id", "document_version_id", "task_id", "artifact_id"):
        _nonempty(run.get(key), "execution." + key)
    for key in ("document_sha256", "artifact_sha256"):
        _digest(run.get(key), "execution." + key)
    for key in ("artifact_bytes", "model_attempts", "accounted_tokens"):
        _positive(run.get(key), "execution." + key)
    if run.get("workflow_id") != "shuddho-task-" + run["task_id"]:
        raise Day2AcceptanceFailure("Document execution has an unrelated Temporal workflow id.")
    if run.get("owner_isolation") != "passed" or run.get("artifact_retrieval") != "passed":
        raise Day2AcceptanceFailure("Document execution did not prove isolation and private artifact retrieval.")
    worker = _object(run.get("worker"), "execution.worker")
    _nonempty(worker.get("id"), "execution.worker.id")
    _nonempty(worker.get("task_queue"), "execution.worker.task_queue")
    if worker.get("source_revision") != expected_revision:
        raise Day2AcceptanceFailure("Worker source revision does not match the frozen candidate.")
    if _time(worker.get("heartbeat_after"), "worker.heartbeat_after") <= _time(
            worker.get("heartbeat_before"), "worker.heartbeat_before"):
        raise Day2AcceptanceFailure("Real worker heartbeat did not advance.")

    for label, proof in (("recovery", rec), ("restored", restore)):
        for key in _BASE_FIELDS:
            if proof.get(key) != run.get(key):
                raise Day2AcceptanceFailure(f"{label} changed document execution identity: {key}.")

    rollout_digest = None
    recovery_times = []
    for stage in _RECOVERY:
        digest, verified = _stage(rec.get(stage), "recovery." + stage,
                                  release_id=release_id, revision=expected_revision)
        if restore.get(stage) != rec[stage]:
            raise Day2AcceptanceFailure(f"Restore did not carry forward the same {stage} evidence.")
        if rollout_digest is not None and digest != rollout_digest:
            raise Day2AcceptanceFailure("Recovery checks refer to different rollout manifests.")
        rollout_digest = digest
        recovery_times.append(verified)
    digest, restored_at = _stage(restore.get("backup_restore"), "restored.backup_restore",
                                 release_id=release_id, revision=expected_revision)
    if digest != rollout_digest:
        raise Day2AcceptanceFailure("Restore and recovery are for different rollout manifests.")
    if restored_at < max(recovery_times):
        raise Day2AcceptanceFailure("Isolated backup/restore verification predates worker recovery.")
    return {
        "status": "evidence_consistent",
        "release_id": release_id,
        "source_revision": expected_revision,
        "runtime_manifest_sha256": runtime_digest,
        "rollout_manifest_sha256": rollout_digest,
        "document_id": run["document_id"],
        "document_version_id": run["document_version_id"],
        "task_id": run["task_id"],
        "workflow_id": run["workflow_id"],
        "artifact_id": run["artifact_id"],
        "artifact_sha256": run["artifact_sha256"],
        "worker_id": worker["id"],
        "required_live_checks": list(_CHECKS),
        "caveat": "Only operator-supplied evidence consistency; independent live/platform verification remains mandatory.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile existing Day 2 private staging evidence without executing live work.")
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--restored", type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if (os.getenv("SHUDDHO_STAGING_ALLOW_DAY2_EXECUTION", "").lower() != "true"
                or os.getenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true"):
            raise Day2AcceptanceFailure("Both staging and synthetic-account guards are required.")
        if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
            raise Day2AcceptanceFailure("A fresh private output destination in an existing directory is required.")
        proofs = []
        for path in (args.freeze, args.execution, args.recovery, args.restored):
            proofs.append(json.loads(path.read_text(encoding="utf-8")))
        value = validate_evidence(*proofs, expected_revision=args.expected_revision)
        # Avoid importing the runtime/SQLAlchemy modules for a read-only evidence gate.
        from scripts.staging_release_evidence import write_private_json
        write_private_json(args.output, value)
        print(json.dumps({"status": "evidence_consistent", "written": str(args.output)}, indent=2))
    except (Day2AcceptanceFailure, OSError, ValueError, TypeError) as error:
        message = str(error) if isinstance(error, Day2AcceptanceFailure) else type(error).__name__
        print(json.dumps({"status": "failed", "error": message}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
