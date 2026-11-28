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

from scripts.staging_day2_authorization import (
    AuthorizationEvidenceFailure, read_private_authorization,
    reconcile_authorization,
)
from services.coworker.reviewed_skill_registry import WORKER_HEARTBEAT_TTL_SECONDS
from services.coworker.runtime_identity import WORKER_IDENTITY_KEYS
from scripts.staging_release_freeze import EXPECTED_SCHEMA_REVISION


class Day2AcceptanceFailure(RuntimeError):
    pass


_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_REVISION = re.compile(r"[a-f0-9]{40}\Z")
_BASE_FIELDS = (
    "status", "release_id", "source_revision", "runtime_manifest_sha256",
    "build_digest", "schema_revision", "model_provider", "model_id", "task_queue", "runtime_identity_sha256",
    "document_id", "document_version_id", "document_sha256",
    "task_id", "workflow_id", "artifact_id", "artifact_sha256",
    "artifact_bytes", "model_attempts", "accounted_tokens",
    "owner_isolation", "artifact_retrieval", "content_anchor_verification",
    "worker", "document_outbox", "model_evidence",
)
_RECOVERY = ("temporal", "parallel_restart", "fan_in")
_CHECKS = [
    "model", "owner_isolation", "artifact_retrieval", "temporal", "document_outbox",
    "worker_heartbeat", "parallel_restart", "fan_in", "outbox_once",
    "worker_replaced", "backup_restore", "pdf_content_fidelity",
    "founder_c_authorization",
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
    identity_claims = _object(proof.get("identity_claims"), "execution.owner_isolation.identity_claims")
    if identity_claims.get("subjects_distinct") is not True:
        raise Day2AcceptanceFailure("Managed owner JWT subjects are not proven distinct.")
    for owner_key in ("owner_a", "owner_b"):
        identity = _object(identity_claims.get(owner_key), f"identity_claims.{owner_key}")
        for field in (
            "issuer_verified", "audience_verified", "expiry_verified",
            "subject_verified", "api_subject_binding_verified",
        ):
            if identity.get(field) is not True:
                raise Day2AcceptanceFailure(f"Managed {owner_key} {field} evidence is missing.")
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
    *, expected_revision: str, authorization: object = None,
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
    for key in ("build_digest", "runtime_identity_sha256"):
        _digest(release.get(key), "freeze.release." + key)
    if release.get("schema_revision") != EXPECTED_SCHEMA_REVISION or release.get("model_provider") != "deepseek":
        raise Day2AcceptanceFailure("Frozen runtime identity has an unreviewed schema or provider.")
    for key in ("model_id", "task_queue"):
        _nonempty(release.get(key), "freeze.release." + key)

    run = _object(execution, "execution")
    rec = _object(recovery, "recovery")
    restore = _object(restored, "restored")
    if run.get("status") != "passed" or run.get("source_revision") != expected_revision or run.get("release_id") != release_id:
        raise Day2AcceptanceFailure("Document execution is not passed for the frozen release.")
    if run.get("runtime_manifest_sha256") != runtime_digest:
        raise Day2AcceptanceFailure("Document execution does not match the frozen runtime manifest.")
    if any(run.get(key) != release[key] for key in WORKER_IDENTITY_KEYS):
        raise Day2AcceptanceFailure("Document execution build identity differs from the frozen candidate.")
    for key in ("document_id", "document_version_id", "task_id", "artifact_id"):
        _nonempty(run.get(key), "execution." + key)
    for key in ("document_sha256", "artifact_sha256"):
        _digest(run.get(key), "execution." + key)
    for key in ("artifact_bytes", "model_attempts", "accounted_tokens"):
        _positive(run.get(key), "execution." + key)
    # The provider's identity and positive billed usage must be corroborated
    # by the persisted task, settled cw_model_attempts and draft Step metadata.
    # A positive API usage aggregate alone could be a charged reservation.
    model = _object(run.get("model_evidence"), "execution.model_evidence")
    if (model.get("status") != "verified"
            or model.get("task_id") != run["task_id"]
            or model.get("provider") != "deepseek"
            or model.get("generation_validator") != "passed"):
        raise Day2AcceptanceFailure(
            "Private report has no verified persisted DeepSeek model provenance."
        )
    model_name = _nonempty(model.get("model"), "model_evidence.model")
    if model_name != release["model_id"] or model["provider"] != release["model_provider"]:
        raise Day2AcceptanceFailure("Persisted model identity differs from the frozen candidate.")
    if len(model_name) > 120:
        raise Day2AcceptanceFailure("Model identity exceeds the persisted model ledger bound.")
    _digest(model.get("prompt_sha256"), "model_evidence.prompt_sha256")
    if (type(model.get("ledger_attempt_count")) is not int
            or type(model.get("ledger_accounted_tokens")) is not int
            or model["ledger_attempt_count"] != run["model_attempts"]
            or model["ledger_accounted_tokens"] != run["accounted_tokens"]):
        raise Day2AcceptanceFailure(
            "Model SQL attempt or token totals do not match the private report."
        )
    completed_attempt = _positive(model.get("completed_attempt"), "model_evidence.completed_attempt")
    input_tokens = _positive(model.get("completed_input_tokens"), "model_evidence.completed_input_tokens")
    output_tokens = _positive(model.get("completed_output_tokens"), "model_evidence.completed_output_tokens")
    total_tokens = _positive(model.get("completed_total_tokens"), "model_evidence.completed_total_tokens")
    if (completed_attempt > run["model_attempts"]
            or total_tokens < input_tokens + output_tokens
            or total_tokens > run["accounted_tokens"]):
        raise Day2AcceptanceFailure(
            "Completed provider attempt does not have consistent positive usage."
        )
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
    if run.get("content_anchor_verification") != "passed":
        raise Day2AcceptanceFailure("Document execution did not prove synthetic source-to-summary-to-PDF content fidelity.")
    worker = _object(run.get("worker"), "execution.worker")
    _nonempty(worker.get("id"), "execution.worker.id")
    _nonempty(worker.get("task_queue"), "execution.worker.task_queue")
    if any(worker.get(key) != release[key] for key in WORKER_IDENTITY_KEYS):
        raise Day2AcceptanceFailure("Worker build identity does not match the frozen candidate.")
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
    before_heartbeat = _time(effect.get("worker_before_heartbeat_at"), "recovery_outbox.worker_before_heartbeat_at")
    after_heartbeat = _time(effect.get("worker_after_heartbeat_at"), "recovery_outbox.worker_after_heartbeat_at")
    if (before_heartbeat > restarted
            or (restarted - before_heartbeat).total_seconds() > WORKER_HEARTBEAT_TTL_SECONDS
            or after_heartbeat <= replacement_started):
        raise Day2AcceptanceFailure(
            "Worker heartbeat chronology or pre-restart freshness does not corroborate replacement."
        )
    if effect.get("agent_outbox_delivered") is not True:
        raise Day2AcceptanceFailure("The parent AgentRun outbox delivery was not attested.")
    children = effect.get("completed_children")
    if not isinstance(children, list) or len(children) != 3:
        raise Day2AcceptanceFailure("Recovery needs three structured completed child task receipts.")
    child_ids: set[str] = set()
    child_windows: list[tuple[datetime, datetime]] = []
    for ordinal, raw_child in enumerate(children, start=1):
        child = _object(raw_child, f"recovery_outbox.completed_children[{ordinal}]")
        child_id = _nonempty(child.get("task_id"), f"completed_child_{ordinal}.task_id")
        if (child_id in child_ids or type(child.get("ordinal")) is not int
                or child["ordinal"] != ordinal or child.get("state") != "completed"
                or child.get("idempotency_key") != f"agent:{agent_run_id}:{ordinal}"):
            raise Day2AcceptanceFailure("Recovery child task identity, state or idempotency is inconsistent.")
        child_ids.add(child_id)
        child_start = _time(child.get("started_at"), f"completed_child_{ordinal}.started_at")
        child_finish = _time(child.get("finished_at"), f"completed_child_{ordinal}.finished_at")
        if not started <= child_start <= child_finish <= finished:
            raise Day2AcceptanceFailure("Recovery child task occurred outside the recorded AgentRun.")
        child_windows.append((child_start, child_finish))
    if child_windows[2][0] < max(child_windows[0][1], child_windows[1][1]):
        raise Day2AcceptanceFailure("Recovery fan-in started before both completed branches.")
    if not any(begin <= restarted <= end for begin, end in child_windows):
        raise Day2AcceptanceFailure("Recovery restart did not interrupt an active child task.")
    integrity = _object(restore.get("archive_integrity"), "restored.archive_integrity")
    if integrity.get("status") != "verified" or integrity.get("probe_object_verified") is not True:
        raise Day2AcceptanceFailure("Restored source archive and synthetic probe must have verified receipts.")
    for field in (
        "postgres_archive_sha256", "postgres_schema_sha256", "object_manifest_sha256",
        "source_database_fingerprint", "target_database_fingerprint",
        "source_storage_fingerprint", "target_storage_fingerprint",
    ):
        _digest(integrity.get(field), "archive_integrity." + field)
    for field in ("postgres_table_count", "postgres_row_count", "object_count", "object_total_bytes"):
        _positive(integrity.get(field), "archive_integrity." + field)
    if integrity["postgres_table_count"] < 84:
        raise Day2AcceptanceFailure("Restored database has an incomplete 84-table source inventory.")
    if (integrity["source_database_fingerprint"] == integrity["target_database_fingerprint"]
            or integrity["source_storage_fingerprint"] == integrity["target_storage_fingerprint"]):
        raise Day2AcceptanceFailure("Source and restored database/object targets are not independent.")
    if not isinstance(integrity.get("source_schema_revision"), str) or not re.fullmatch(
        r"[A-Za-z0-9_]{1,128}", integrity["source_schema_revision"]
    ):
        raise Day2AcceptanceFailure("Restored archive schema revision is missing.")
    # Privileged SQL/S3 restore reads are not user-facing authorization.
    # Fail closed unless the restored API itself authenticated A and B,
    # returned the same archived probe bytes, and denied B document/task reads.
    restored_api = _object(
        integrity.get("restored_api_access"),
        "archive_integrity.restored_api_access",
    )
    if (restored_api.get("status") != "verified"
            or restored_api.get("runtime_source_revision") != expected_revision):
        raise Day2AcceptanceFailure(
            "archive_integrity.restored_api_access is missing verified release identity."
        )
    for field in (
        "source_api_origin_sha256", "restored_api_origin_sha256",
        "owner_a_document_sha256",
    ):
        _digest(restored_api.get(field), "archive_integrity.restored_api_access." + field)
    _digest(integrity.get("probe_object_sha256"), "archive_integrity.probe_object_sha256")
    probe_bytes = _positive(integrity.get("probe_object_bytes"), "archive_integrity.probe_object_bytes")
    readback_bytes = _positive(
        restored_api.get("owner_a_document_bytes"),
        "archive_integrity.restored_api_access.owner_a_document_bytes",
    )
    if (restored_api["source_api_origin_sha256"] == restored_api["restored_api_origin_sha256"]
            or restored_api["owner_a_document_sha256"] != integrity["probe_object_sha256"]
            or probe_bytes != readback_bytes):
        raise Day2AcceptanceFailure(
            "archive_integrity.restored_api_access differs from source API or archived probe bytes."
        )
    for field in (
        "owner_a_identity_verified", "owner_b_identity_verified",
        "owner_a_document_retrievable", "owner_b_document_denied",
        "owner_b_document_unlisted", "owner_a_cancelled_task_verified",
        "owner_b_task_denied",
    ):
        if restored_api.get(field) is not True:
            raise Day2AcceptanceFailure(
                "archive_integrity.restored_api_access is missing authenticated owner isolation: " + field
            )
    preseed = _object(integrity.get("preseed_baseline"), "archive_integrity.preseed_baseline")
    if (preseed.get("status") != "preseed_verified"
            or preseed.get("source_schema_revision") != "0070"
            or preseed.get("object_count") != 0
            or preseed.get("object_total_bytes") != 0):
        raise Day2AcceptanceFailure(
            "archive_integrity.preseed_baseline must prove the original 0070 zero-object state."
        )
    observed_preseed = _time(
        preseed.get("attested_at"), "archive_integrity.preseed_baseline.attested_at",
    )
    if observed_preseed > started:
        raise Day2AcceptanceFailure(
            "archive_integrity.preseed_baseline was recorded after worker recovery began."
        )
    for field in (
        "postgres_archive_sha256", "postgres_schema_sha256",
        "object_manifest_sha256", "source_database_fingerprint",
        "source_storage_fingerprint",
    ):
        _digest(preseed.get(field), "archive_integrity.preseed_baseline." + field)
    if (_positive(preseed.get("postgres_table_count"),
                  "archive_integrity.preseed_baseline.postgres_table_count") < 84
            or _positive(preseed.get("postgres_row_count"),
                         "archive_integrity.preseed_baseline.postgres_row_count") < 1
            or preseed["source_database_fingerprint"] != integrity["source_database_fingerprint"]
            or preseed["source_storage_fingerprint"] != integrity["source_storage_fingerprint"]):
        raise Day2AcceptanceFailure(
            "archive_integrity.preseed_baseline differs from the verified source resources."
        )
    digest, restored_at = _stage(restore.get("backup_restore"), "restored.backup_restore",
                                 release_id=release_id, revision=expected_revision)
    if digest != rollout_digest:
        raise Day2AcceptanceFailure("Backup/restore does not match the frozen rollout manifest.")
    if restored_at < max(recovery_times):
        raise Day2AcceptanceFailure("Isolated backup/restore verification predates worker recovery.")
    # Part 02 D02.T05 / G05 is separate from a green code test or a
    # technically consistent restore. A private, dated Founder + C decision
    # must cover the exact release, host, limit, duration and restore targets.
    # This checks only the *shape and consistency* of operator-supplied data.
    try:
        authorization_evidence = reconcile_authorization(
            authorization,
            release=release,
            freeze_prepared_at=frozen.get("prepared_at"),
            preseed_attested_at=preseed.get("attested_at"),
            integrity=integrity,
            model_attempts=run.get("model_attempts"),
            restore_verified_at=restored_at,
        )
    except AuthorizationEvidenceFailure as error:
        raise Day2AcceptanceFailure(str(error)) from None
    return {
        "status": "evidence_consistent",
        "release_id": release_id,
        "source_revision": expected_revision,
        "runtime_manifest_sha256": runtime_digest,
        **{key: release[key] for key in WORKER_IDENTITY_KEYS if key != "source_revision"},
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
        "parent_agent_outbox_delivered": True,
        "completed_child_task_count": len(child_ids),
        "logical_document_outbox_effect_count": 1,
        "document_outbox_dispatch_attempts": document_outbox["dispatch_attempts"],
        "archive_integrity": integrity,
        "authorization_evidence": authorization_evidence,
        "required_live_checks": list(_CHECKS),
        "caveat": "Only operator-supplied evidence consistency; independent live/platform verification remains mandatory.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile existing Day 2 private staging evidence without executing live work.")
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--restored", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True,
                        help="Private mode-0600 dated Founder/C decision receipt, never pasted into CI")
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
        authorization = read_private_authorization(args.authorization)
        value = validate_evidence(
            *proofs, expected_revision=args.expected_revision,
            authorization=authorization,
        )
        # Avoid importing the runtime/SQLAlchemy modules for a read-only evidence gate.
        from scripts.staging_release_evidence import write_private_json
        write_private_json(args.output, value)
        print(json.dumps({"status": "evidence_consistent", "written": str(args.output)}, indent=2))
    except (Day2AcceptanceFailure, AuthorizationEvidenceFailure, OSError, ValueError, TypeError) as error:
        message = str(error) if isinstance(error, (Day2AcceptanceFailure, AuthorizationEvidenceFailure)) else type(error).__name__
        print(json.dumps({"status": "failed", "error": message}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
