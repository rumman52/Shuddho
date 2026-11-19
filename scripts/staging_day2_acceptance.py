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
    "owner_isolation", "artifact_retrieval", "worker", "document_outbox",
)
_RECOVERY = ("temporal", "parallel_restart", "fan_in")
_CHECKS = [
    "model", "owner_isolation", "artifact_retrieval", "temporal", "document_outbox",
    "worker_heartbeat", "parallel_restart", "fan_in", "outbox_once",
    "worker_replaced", "backup_restore",
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


def validate_owner_isolation(
    value: object,
    *,
    document_id: str,
    document_sha256: str,
    artifact_id: str,
    artifact_sha256: str,
    artifact_bytes: int,
) -> dict:
    """Require positive and negative document/artifact proofs for both owners."""
    proof = _object(value, "execution.owner_isolation")
    if proof.get("schema_version") != 1 or proof.get("status") != "passed":
        raise Day2AcceptanceFailure("Bidirectional owner isolation has not passed schema version 1.")
    if proof.get("identities_distinct") is not True:
        raise Day2AcceptanceFailure("Bidirectional owner isolation does not prove distinct identities.")
    owners = _object(proof.get("owners"), "execution.owner_isolation.owners")
    if set(owners) != {"a", "b"}:
        raise Day2AcceptanceFailure("Bidirectional owner isolation must contain exactly owners a and b.")

    required_statuses = {
        "document_read": "passed",
        "own_document_list": "included",
        "foreign_document_read": "denied_404",
        "foreign_document_write": "denied_404",
        "foreign_document_list": "excluded",
        "artifact_content_read": "passed",
        "artifact_download": "passed",
        "own_artifact_list": "included",
        "foreign_artifact_content": "denied_404",
        "foreign_artifact_download": "denied_404",
        "foreign_artifact_list": "excluded",
    }
    normalized = {}
    for owner in ("a", "b"):
        row = _object(owners.get(owner), f"execution.owner_isolation.owners.{owner}")
        for key in ("document_id", "artifact_id"):
            _nonempty(row.get(key), f"owner_{owner}.{key}")
        _digest(row.get("document_sha256"), f"owner_{owner}.document_sha256")
        _digest(row.get("artifact_sha256"), f"owner_{owner}.artifact_sha256")
        _positive(row.get("document_bytes"), f"owner_{owner}.document_bytes")
        _positive(row.get("artifact_bytes"), f"owner_{owner}.artifact_bytes")
        for key, expected in required_statuses.items():
            if row.get(key) != expected:
                raise Day2AcceptanceFailure(
                    f"Bidirectional owner isolation owner_{owner}.{key} must be {expected}."
                )
        normalized[owner] = row

    owner_a, owner_b = normalized["a"], normalized["b"]
    if owner_a["document_id"] == owner_b["document_id"] or owner_a["artifact_id"] == owner_b["artifact_id"]:
        raise Day2AcceptanceFailure("Bidirectional owner isolation resource IDs must be distinct.")
    if owner_a["document_id"] != document_id or owner_a["artifact_id"] != artifact_id:
        raise Day2AcceptanceFailure("Owner A isolation resource IDs do not match the primary PDF task.")
    if owner_a["document_sha256"] != document_sha256:
        raise Day2AcceptanceFailure("Owner A document digest does not match the primary PDF task.")
    if owner_a["artifact_sha256"] != artifact_sha256 or owner_a["artifact_bytes"] != artifact_bytes:
        raise Day2AcceptanceFailure("Owner A artifact digest/size does not match the primary PDF task.")
    return proof


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
    rollout_digest = _digest(release.get("rollout_manifest_sha256"), "freeze.release.rollout_manifest_sha256")

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
    document_outbox = _object(run.get("document_outbox"), "execution.document_outbox")
    if (document_outbox.get("task_id") != run["task_id"]
            or type(document_outbox.get("effect_count")) is not int
            or document_outbox["effect_count"] != 1
            or document_outbox.get("delivered") is not True):
        raise Day2AcceptanceFailure("Private PDF task does not have exactly one delivered outbox effect.")
    _positive(document_outbox.get("dispatch_attempts"), "document_outbox.dispatch_attempts")
    if run.get("workflow_id") != "shuddho-task-" + run["task_id"]:
        raise Day2AcceptanceFailure("Document execution has an unrelated Temporal workflow id.")
    owner_isolation = validate_owner_isolation(
        run.get("owner_isolation"),
        document_id=run["document_id"],
        document_sha256=run["document_sha256"],
        artifact_id=run["artifact_id"],
        artifact_sha256=run["artifact_sha256"],
        artifact_bytes=run["artifact_bytes"],
    )
    if run.get("artifact_retrieval") != "passed":
        raise Day2AcceptanceFailure("Document execution did not prove private artifact retrieval.")
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

    recovery_times = []
    for stage in _RECOVERY:
        digest, verified = _stage(rec.get(stage), "recovery." + stage,
                                  release_id=release_id, revision=expected_revision)
        if restore.get(stage) != rec[stage]:
            raise Day2AcceptanceFailure(f"Restore did not carry forward the same {stage} evidence.")
        if digest != rollout_digest:
            raise Day2AcceptanceFailure(f"Recovery {stage} does not match the frozen rollout manifest.")
        recovery_times.append(verified)
    effect = _object(rec.get("recovery_outbox"), "recovery.recovery_outbox")
    if restore.get("recovery_outbox") != effect:
        raise Day2AcceptanceFailure("Restore did not carry forward the same recovery outbox evidence.")
    agent_run_id = _nonempty(effect.get("agent_run_id"), "recovery_outbox.agent_run_id")
    if (effect.get("workflow_id") != "shuddho-agent-" + agent_run_id
            or effect.get("source_revision") != expected_revision):
        raise Day2AcceptanceFailure("Outbox proof belongs to a different Agent run or source revision.")
    if (type(effect.get("agent_outbox_effect_count")) is not int
            or effect["agent_outbox_effect_count"] != 1
            or type(effect.get("child_task_outbox_count")) is not int
            or effect["child_task_outbox_count"] != 0
            or effect.get("child_task_outbox_expected_absent") is not True):
        raise Day2AcceptanceFailure("Recovery has not proved one AgentRun outbox effect and zero direct-child outbox effects.")
    worker_before_id = _nonempty(effect.get("worker_before_id"), "recovery_outbox.worker_before_id")
    worker_after_id = _nonempty(effect.get("worker_after_id"), "recovery_outbox.worker_after_id")
    if worker_before_id == worker_after_id:
        raise Day2AcceptanceFailure("Recovery has no distinct replacement worker identity.")
    started = _time(effect.get("run_started_at"), "recovery_outbox.run_started_at")
    finished = _time(effect.get("run_finished_at"), "recovery_outbox.run_finished_at")
    restarted = _time(effect.get("restart_at"), "recovery_outbox.restart_at")
    replacement_started = _time(effect.get("worker_after_started_at"), "recovery_outbox.worker_after_started_at")
    _nonempty(effect.get("restart_reference"), "recovery_outbox.restart_reference")
    if not (started <= restarted <= finished
            and started <= replacement_started <= finished
            and 0 <= (replacement_started - restarted).total_seconds() <= 300):
        raise Day2AcceptanceFailure("Recovery did not replace a worker during the same active Agent run.")
    digest, restored_at = _stage(restore.get("backup_restore"), "restored.backup_restore",
                                 release_id=release_id, revision=expected_revision)
    if digest != rollout_digest:
        raise Day2AcceptanceFailure("Backup/restore does not match the frozen rollout manifest.")
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
        "owner_isolation": owner_isolation,
        "worker_id": worker["id"],
        "recovered_agent_run_id": agent_run_id,
        "recovered_agent_workflow_id": effect["workflow_id"],
        "logical_agent_outbox_effect_count": 1,
        "logical_document_outbox_effect_count": 1,
        "document_outbox_dispatch_attempts": document_outbox["dispatch_attempts"],
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
