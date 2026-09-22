from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
ROLLBACK_SCHEMA_VERSION = 2
RECOVERY_SCHEMA_VERSION = 3
SCALE_SCHEMA_VERSION = 4
PROVIDER_POLICY_SCHEMA_VERSION = 5
MICROSOFT_ROLLOUT_SCHEMA_VERSION = 6
ZERO_HASH = "0" * 64
EVENT_DECISIONS = {
    "hold": "HOLD",
    "eligible_for_expansion": "ELIGIBLE_FOR_EXPANSION",
    "stage_approved": "ELIGIBLE_FOR_EXPANSION",
    "stop_rollout": "STOP_ROLLOUT",
}
ARTIFACT_KEYS = {
    "rollout_manifest",
    "canary_plan",
    "progression_decision",
    "operator_status",
}
ROLLBACK_ARTIFACT_KEYS = ARTIFACT_KEYS | {"rollback_completion"}
RECOVERY_ARTIFACT_KEYS = ROLLBACK_ARTIFACT_KEYS | {"recovery_verification"}
SCALE_ARTIFACT_KEYS = {
    "scale_decision",
    "deployment_change",
    "operator_status",
    "scale_activation",
}
PROVIDER_POLICY_ARTIFACT_KEYS = {
    "provider_policy",
    "deployment_change",
    "operator_status",
    "policy_activation",
}
MICROSOFT_ROLLOUT_ARTIFACT_KEYS = {
    "staging_evidence",
    "deployment_change",
    "operator_status",
    "rollout_activation",
}


class ReleaseLedgerError(RuntimeError):
    pass


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def valid_hash(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReleaseLedgerError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ReleaseLedgerError(f"{label} must contain a JSON object.")
    return value


def ledger_key() -> bytes:
    value = os.environ.get("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "")
    key = value.encode("utf-8")
    if len(key) < 32:
        raise ReleaseLedgerError(
            "SHUDDHO_RELEASE_LEDGER_HMAC_KEY must contain at least 32 UTF-8 bytes."
        )
    return key


def artifact_hashes(
    rollout: Path,
    canary_plan: Path,
    progression_decision: Path,
    operator_status: Path,
) -> dict[str, str]:
    return {
        "rollout_manifest": file_sha256(rollout),
        "canary_plan": file_sha256(canary_plan),
        "progression_decision": file_sha256(progression_decision),
        "operator_status": file_sha256(operator_status),
    }


def validate_bound_inputs(
    *,
    release_id: str,
    event_type: str,
    current_stage: str,
    next_stage: str | None,
    rollout: Path,
    canary_plan: Path,
    progression_decision: Path,
    operator_status: Path,
) -> None:
    if event_type not in EVENT_DECISIONS:
        raise ReleaseLedgerError(f"Unsupported release ledger event type: {event_type!r}.")
    if not release_id.strip() or len(release_id) > 200:
        raise ReleaseLedgerError("release_id must be a non-empty string of at most 200 characters.")
    if not current_stage.strip() or len(current_stage) > 100:
        raise ReleaseLedgerError("current_stage must be a non-empty string of at most 100 characters.")
    if next_stage is not None and (not next_stage.strip() or len(next_stage) > 100):
        raise ReleaseLedgerError("next_stage must be null or a non-empty string of at most 100 characters.")

    rollout_value = load_json_object(rollout, "rollout manifest")
    plan_value = load_json_object(canary_plan, "canary plan")
    decision_value = load_json_object(progression_decision, "progression decision")
    status_value = load_json_object(operator_status, "operator status")

    for label, value in (
        ("rollout manifest", rollout_value),
        ("canary plan", plan_value),
        ("progression decision", decision_value),
        ("operator status", status_value),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(f"{label} release_id does not match {release_id!r}.")

    expected_decision = EVENT_DECISIONS[event_type]
    if decision_value.get("decision") != expected_decision:
        raise ReleaseLedgerError(
            f"{event_type} requires progression decision {expected_decision!r}."
        )
    if decision_value.get("current_stage") != current_stage:
        raise ReleaseLedgerError("Progression current_stage does not match the ledger event.")

    decision_next = decision_value.get("next_stage")
    if decision_next != next_stage:
        raise ReleaseLedgerError("Progression next_stage does not match the ledger event.")

    stages = plan_value.get("stages")
    if not isinstance(stages, list):
        raise ReleaseLedgerError("Canary plan has no valid stages list.")
    names = [
        item.get("name")
        for item in stages
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    if current_stage not in names:
        raise ReleaseLedgerError("current_stage is not present in the canary plan.")
    if next_stage is not None and next_stage not in names:
        raise ReleaseLedgerError("next_stage is not present in the canary plan.")

    if event_type in {"eligible_for_expansion", "stage_approved"}:
        current_index = names.index(current_stage)
        if current_index + 1 >= len(names) or names[current_index + 1] != next_stage:
            raise ReleaseLedgerError("Expansion must target the immediately following canary stage.")
    if event_type == "stage_approved" and next_stage is None:
        raise ReleaseLedgerError("stage_approved requires a next_stage.")


def entry_core(entry: dict) -> dict:
    return {
        key: entry[key]
        for key in (
            "schema_version",
            "sequence",
            "created_at",
            "release_id",
            "event_type",
            "actor_reference",
            "change_reference",
            "current_stage",
            "next_stage",
            "artifact_sha256",
            "previous_entry_hash",
        )
    }


def sign_entry(core: dict, key: bytes) -> tuple[str, str]:
    entry_hash = hashlib.sha256(canonical(core)).hexdigest()
    tag = hmac.new(key, entry_hash.encode("ascii"), hashlib.sha256).hexdigest()
    return entry_hash, tag


def read_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ReleaseLedgerError(f"Ledger line {line_number} is not a JSON object.")
            rows.append(value)
    except json.JSONDecodeError as error:
        raise ReleaseLedgerError(
            f"Ledger contains invalid JSON at line {error.lineno}."
        ) from None
    return rows


def verify_entries(entries: list[dict], key: bytes) -> dict:
    previous = ZERO_HASH
    release_id: str | None = None
    for index, entry in enumerate(entries, start=1):
        required = {
            "schema_version",
            "sequence",
            "created_at",
            "release_id",
            "event_type",
            "actor_reference",
            "change_reference",
            "current_stage",
            "next_stage",
            "artifact_sha256",
            "previous_entry_hash",
            "entry_hash",
            "hmac_sha256",
        }
        if set(entry) != required:
            raise ReleaseLedgerError(f"Ledger entry {index} has an unexpected schema.")
        version = entry["schema_version"]
        if version not in {
            SCHEMA_VERSION,
            ROLLBACK_SCHEMA_VERSION,
            RECOVERY_SCHEMA_VERSION,
            SCALE_SCHEMA_VERSION,
            PROVIDER_POLICY_SCHEMA_VERSION,
            MICROSOFT_ROLLOUT_SCHEMA_VERSION,
        }:
            raise ReleaseLedgerError(f"Ledger entry {index} has an unsupported schema version.")
        if entry["sequence"] != index:
            raise ReleaseLedgerError(f"Ledger entry {index} has an invalid sequence.")
        try:
            datetime.fromisoformat(str(entry["created_at"]).replace("Z", "+00:00"))
        except ValueError:
            raise ReleaseLedgerError(f"Ledger entry {index} has an invalid timestamp.") from None
        event_type = entry["event_type"]
        if version == SCHEMA_VERSION and event_type not in EVENT_DECISIONS:
            raise ReleaseLedgerError(f"Ledger entry {index} has an unsupported event type.")
        if version == ROLLBACK_SCHEMA_VERSION and event_type != "rollback_completed":
            raise ReleaseLedgerError(f"Ledger entry {index} has an unsupported schema-v2 event type.")
        if version == RECOVERY_SCHEMA_VERSION and event_type != "recovery_verified":
            raise ReleaseLedgerError(f"Ledger entry {index} has an unsupported schema-v3 event type.")
        if version == SCALE_SCHEMA_VERSION and event_type != "bounded_expansion_verified":
            raise ReleaseLedgerError(f"Ledger entry {index} has an unsupported schema-v4 event type.")
        if (
            version == PROVIDER_POLICY_SCHEMA_VERSION
            and event_type != "provider_policy_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v5 event type."
            )
        if (
            version == MICROSOFT_ROLLOUT_SCHEMA_VERSION
            and event_type != "microsoft_rollout_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v6 event type."
            )
        if not isinstance(entry["actor_reference"], str) or not entry["actor_reference"].strip():
            raise ReleaseLedgerError(f"Ledger entry {index} has no actor reference.")
        if not isinstance(entry["change_reference"], str) or not entry["change_reference"].strip():
            raise ReleaseLedgerError(f"Ledger entry {index} has no change reference.")
        if not isinstance(entry["current_stage"], str) or not entry["current_stage"].strip():
            raise ReleaseLedgerError(f"Ledger entry {index} has no current stage.")
        if entry["next_stage"] is not None and not isinstance(entry["next_stage"], str):
            raise ReleaseLedgerError(f"Ledger entry {index} has an invalid next stage.")
        artifacts = entry["artifact_sha256"]
        expected_artifacts = (
            ARTIFACT_KEYS if version == SCHEMA_VERSION
            else ROLLBACK_ARTIFACT_KEYS if version == ROLLBACK_SCHEMA_VERSION
            else RECOVERY_ARTIFACT_KEYS if version == RECOVERY_SCHEMA_VERSION
            else SCALE_ARTIFACT_KEYS if version == SCALE_SCHEMA_VERSION
            else PROVIDER_POLICY_ARTIFACT_KEYS
            if version == PROVIDER_POLICY_SCHEMA_VERSION
            else MICROSOFT_ROLLOUT_ARTIFACT_KEYS
        )
        if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
            raise ReleaseLedgerError(f"Ledger entry {index} has invalid artifact hashes.")
        if any(not valid_hash(value) for value in artifacts.values()):
            raise ReleaseLedgerError(f"Ledger entry {index} contains an invalid artifact SHA-256.")
        if entry["previous_entry_hash"] != previous:
            raise ReleaseLedgerError(f"Ledger entry {index} breaks the hash chain.")

        core = entry_core(entry)
        expected_hash, expected_tag = sign_entry(core, key)
        if not hmac.compare_digest(entry["entry_hash"], expected_hash):
            raise ReleaseLedgerError(f"Ledger entry {index} hash does not match its content.")
        if not hmac.compare_digest(entry["hmac_sha256"], expected_tag):
            raise ReleaseLedgerError(f"Ledger entry {index} HMAC verification failed.")

        if release_id is None:
            release_id = entry["release_id"]
        elif entry["release_id"] != release_id:
            raise ReleaseLedgerError("One ledger file may contain only one release_id.")
        previous = entry["entry_hash"]

    return {
        "entries": len(entries),
        "release_id": release_id,
        "head_entry_hash": previous if entries else None,
        "verified": True,
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def append_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    event_type: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    next_stage: str | None,
    rollout: Path,
    canary_plan: Path,
    progression_decision: Path,
    operator_status: Path,
    created_at: str | None = None,
) -> dict:
    if not actor_reference.strip() or len(actor_reference) > 500:
        raise ReleaseLedgerError("actor_reference must be non-empty and at most 500 characters.")
    if not change_reference.strip() or len(change_reference) > 500:
        raise ReleaseLedgerError("change_reference must be non-empty and at most 500 characters.")

    validate_bound_inputs(
        release_id=release_id,
        event_type=event_type,
        current_stage=current_stage,
        next_stage=next_stage,
        rollout=rollout,
        canary_plan=canary_plan,
        progression_decision=progression_decision,
        operator_status=operator_status,
    )
    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if state["release_id"] is not None and state["release_id"] != release_id:
        raise ReleaseLedgerError("Ledger release_id does not match the event release_id.")

    core = {
        "schema_version": SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": event_type,
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "artifact_sha256": artifact_hashes(
            rollout,
            canary_plan,
            progression_decision,
            operator_status,
        ),
        "previous_entry_hash": state["head_entry_hash"] or ZERO_HASH,
    }
    entry_hash, tag = sign_entry(core, key)
    entry = {**core, "entry_hash": entry_hash, "hmac_sha256": tag}
    serialized = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for item in [*entries, entry]
    )
    atomic_write(ledger, serialized)
    return entry



def append_rollback_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    rollout: Path,
    canary_plan: Path,
    progression_decision: Path,
    operator_status: Path,
    rollback_completion: Path,
    created_at: str | None = None,
) -> dict:
    if not actor_reference.strip() or len(actor_reference) > 500:
        raise ReleaseLedgerError("actor_reference must be non-empty and at most 500 characters.")
    if not change_reference.strip() or len(change_reference) > 500:
        raise ReleaseLedgerError("change_reference must be non-empty and at most 500 characters.")

    rollout_value = load_json_object(rollout, "rollout manifest")
    plan_value = load_json_object(canary_plan, "canary plan")
    decision_value = load_json_object(progression_decision, "progression decision")
    status_value = load_json_object(operator_status, "post-rollback operator status")
    rollback_value = load_json_object(rollback_completion, "rollback completion evidence")

    for label, value in (
        ("rollout manifest", rollout_value),
        ("canary plan", plan_value),
        ("progression decision", decision_value),
        ("operator status", status_value),
        ("rollback completion evidence", rollback_value),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(f"{label} release_id does not match {release_id!r}.")

    if decision_value.get("decision") != "STOP_ROLLOUT":
        raise ReleaseLedgerError("rollback_completed requires a STOP_ROLLOUT progression decision.")
    if decision_value.get("current_stage") != current_stage or decision_value.get("next_stage") is not None:
        raise ReleaseLedgerError("Rollback completion stage does not match the STOP decision.")
    if status_value.get("decision") != "CONTINUE_COHORT" or status_value.get("breaches") != []:
        raise ReleaseLedgerError("rollback_completed requires a healthy post-rollback operator status.")
    if rollback_value.get("status") != "rollback_completed":
        raise ReleaseLedgerError("Rollback completion evidence has not passed.")

    rollback_hashes = rollback_value.get("artifact_sha256")
    if not isinstance(rollback_hashes, dict):
        raise ReleaseLedgerError("Rollback completion evidence has no artifact hashes.")
    if rollback_hashes.get("rollout_manifest") != file_sha256(rollout):
        raise ReleaseLedgerError("Rollback completion evidence does not bind this rollout manifest.")
    if rollback_hashes.get("operator_status") != file_sha256(operator_status):
        raise ReleaseLedgerError("Rollback completion evidence does not bind this operator status.")

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if state["release_id"] is not None and state["release_id"] != release_id:
        raise ReleaseLedgerError("Ledger release_id does not match the rollback event.")
    stop_entries = [item for item in entries if item.get("event_type") == "stop_rollout"]
    if not stop_entries:
        raise ReleaseLedgerError("rollback_completed requires an earlier stop_rollout ledger entry.")
    stop = stop_entries[-1]
    expected_common = {
        "rollout_manifest": file_sha256(rollout),
        "canary_plan": file_sha256(canary_plan),
        "progression_decision": file_sha256(progression_decision),
    }
    for name, value in expected_common.items():
        if stop["artifact_sha256"].get(name) != value:
            raise ReleaseLedgerError(
                f"rollback_completed does not bind the same {name} as the latest STOP event."
            )
    if stop.get("current_stage") != current_stage:
        raise ReleaseLedgerError("rollback_completed current stage differs from the latest STOP event.")

    core = {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "rollback_completed",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            **artifact_hashes(rollout, canary_plan, progression_decision, operator_status),
            "rollback_completion": file_sha256(rollback_completion),
        },
        "previous_entry_hash": state["head_entry_hash"] or ZERO_HASH,
    }
    entry_hash, tag = sign_entry(core, key)
    entry = {**core, "entry_hash": entry_hash, "hmac_sha256": tag}
    serialized = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for item in [*entries, entry]
    )
    atomic_write(ledger, serialized)
    return entry



def append_recovery_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    rollout: Path,
    canary_plan: Path,
    progression_decision: Path,
    operator_status: Path,
    rollback_completion: Path,
    recovery_verification: Path,
    created_at: str | None = None,
) -> dict:
    if not actor_reference.strip() or len(actor_reference) > 500:
        raise ReleaseLedgerError("actor_reference must be non-empty and at most 500 characters.")
    if not change_reference.strip() or len(change_reference) > 500:
        raise ReleaseLedgerError("change_reference must be non-empty and at most 500 characters.")

    rollout_value = load_json_object(rollout, "rollout manifest")
    plan_value = load_json_object(canary_plan, "canary plan")
    decision_value = load_json_object(progression_decision, "STOP progression decision")
    status_value = load_json_object(operator_status, "post-recovery operator status")
    rollback_value = load_json_object(rollback_completion, "rollback completion evidence")
    recovery_value = load_json_object(recovery_verification, "recovery verification evidence")

    for label, value in (
        ("rollout manifest", rollout_value),
        ("canary plan", plan_value),
        ("progression decision", decision_value),
        ("operator status", status_value),
        ("rollback completion evidence", rollback_value),
        ("recovery verification evidence", recovery_value),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(f"{label} release_id does not match {release_id!r}.")

    if decision_value.get("decision") != "STOP_ROLLOUT":
        raise ReleaseLedgerError("recovery_verified requires the original STOP_ROLLOUT progression decision.")
    if decision_value.get("current_stage") != current_stage or decision_value.get("next_stage") is not None:
        raise ReleaseLedgerError("Recovery stage does not match the original STOP decision.")
    if rollback_value.get("status") != "rollback_completed":
        raise ReleaseLedgerError("Recovery requires passed rollback-completion evidence.")
    if recovery_value.get("status") != "recovery_verified":
        raise ReleaseLedgerError("Recovery verification evidence has not passed.")
    if recovery_value.get("current_stage") != current_stage:
        raise ReleaseLedgerError("Recovery verification current stage does not match the ledger event.")
    if status_value.get("decision") != "CONTINUE_COHORT" or status_value.get("breaches") != []:
        raise ReleaseLedgerError("recovery_verified requires a clean post-recovery operator status.")

    rollback_hashes = rollback_value.get("artifact_sha256")
    recovery_hashes = recovery_value.get("artifact_sha256")
    if not isinstance(rollback_hashes, dict) or not isinstance(recovery_hashes, dict):
        raise ReleaseLedgerError("Recovery evidence is missing artifact hashes.")
    if rollback_hashes.get("rollout_manifest") != file_sha256(rollout):
        raise ReleaseLedgerError("Rollback completion does not bind this rollout manifest.")
    expected_recovery_hashes = {
        "rollout_manifest": file_sha256(rollout),
        "canary_plan": file_sha256(canary_plan),
        "rollback_completion": file_sha256(rollback_completion),
        "operator_status": file_sha256(operator_status),
    }
    for name, value in expected_recovery_hashes.items():
        if recovery_hashes.get(name) != value:
            raise ReleaseLedgerError(f"Recovery verification does not bind this {name}.")

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if state["release_id"] is not None and state["release_id"] != release_id:
        raise ReleaseLedgerError("Ledger release_id does not match the recovery event.")
    rollback_entries = [item for item in entries if item.get("event_type") == "rollback_completed"]
    if not rollback_entries:
        raise ReleaseLedgerError("recovery_verified requires an earlier rollback_completed ledger entry.")
    rollback_entry = rollback_entries[-1]
    if rollback_entry.get("current_stage") != current_stage:
        raise ReleaseLedgerError("Recovery current stage differs from the latest rollback_completed event.")

    stop_entries = [item for item in entries if item.get("event_type") == "stop_rollout"]
    if not stop_entries:
        raise ReleaseLedgerError("recovery_verified requires the original stop_rollout ledger entry.")
    stop = stop_entries[-1]
    expected_common = {
        "rollout_manifest": file_sha256(rollout),
        "canary_plan": file_sha256(canary_plan),
        "progression_decision": file_sha256(progression_decision),
    }
    for name, value in expected_common.items():
        if stop["artifact_sha256"].get(name) != value:
            raise ReleaseLedgerError(
                f"recovery_verified does not bind the same {name} as the latest STOP event."
            )
    if rollback_entry["artifact_sha256"].get("rollback_completion") != file_sha256(rollback_completion):
        raise ReleaseLedgerError(
            "Recovery does not bind the rollback-completion artifact recorded in the ledger."
        )

    core = {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "recovery_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            **artifact_hashes(rollout, canary_plan, progression_decision, operator_status),
            "rollback_completion": file_sha256(rollback_completion),
            "recovery_verification": file_sha256(recovery_verification),
        },
        "previous_entry_hash": state["head_entry_hash"] or ZERO_HASH,
    }
    entry_hash, tag = sign_entry(core, key)
    entry = {**core, "entry_hash": entry_hash, "hmac_sha256": tag}
    serialized = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for item in [*entries, entry]
    )
    atomic_write(ledger, serialized)
    return entry



def append_scale_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    next_stage: str,
    scale_decision: Path,
    deployment_change: Path,
    operator_status: Path,
    scale_activation: Path,
    created_at: str | None = None,
) -> dict:
    if not actor_reference.strip() or len(actor_reference) > 500:
        raise ReleaseLedgerError("actor_reference must be non-empty and at most 500 characters.")
    if not change_reference.strip() or len(change_reference) > 500:
        raise ReleaseLedgerError("change_reference must be non-empty and at most 500 characters.")
    if not current_stage.strip() or not next_stage.strip():
        raise ReleaseLedgerError("Scale ledger event requires current_stage and next_stage.")

    decision = load_json_object(scale_decision, "scale decision")
    deployment = load_json_object(deployment_change, "deployment change")
    status = load_json_object(operator_status, "post-scale operator status")
    activation = load_json_object(scale_activation, "scale activation evidence")

    for label, value in (
        ("scale decision", decision),
        ("deployment change", deployment),
        ("operator status", status),
        ("scale activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(f"{label} release_id does not match {release_id!r}.")

    if decision.get("decision") != "ELIGIBLE_FOR_BOUNDED_EXPANSION":
        raise ReleaseLedgerError("bounded_expansion_verified requires an eligible scale decision.")
    if decision.get("current_stage") != current_stage or decision.get("proposed_stage") != next_stage:
        raise ReleaseLedgerError("Scale decision stages do not match the ledger event.")
    if deployment.get("stage") != next_stage:
        raise ReleaseLedgerError("Deployment stage does not match the ledger event.")
    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError("Deployment change reference does not match the ledger event.")
    if status.get("decision") != "CONTINUE_COHORT" or status.get("breaches") != []:
        raise ReleaseLedgerError("bounded_expansion_verified requires a clean post-scale operator status.")
    if activation.get("status") != "bounded_expansion_verified":
        raise ReleaseLedgerError("Scale activation evidence has not passed.")
    if activation.get("current_stage") != current_stage or activation.get("proposed_stage") != next_stage:
        raise ReleaseLedgerError("Scale activation stages do not match the ledger event.")
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError("Scale activation change reference does not match the ledger event.")

    hashes = activation.get("artifact_sha256")
    if not isinstance(hashes, dict):
        raise ReleaseLedgerError("Scale activation evidence has no artifact hashes.")
    expected_bound = {
        "scale_decision": file_sha256(scale_decision),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(f"Scale activation evidence does not bind this {name}.")

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if state["release_id"] is not None and state["release_id"] != release_id:
        raise ReleaseLedgerError("Ledger release_id does not match the scale event.")
    if not entries or not any(
        item.get("current_stage") == current_stage or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "bounded_expansion_verified requires an existing ledger chain that reached current_stage."
        )

    policy_activation_hash = hashes.get("provider_policy_activation")
    if not valid_hash(policy_activation_hash):
        raise ReleaseLedgerError(
            "Scale activation evidence does not bind a provider policy activation."
        )
    matching_policy_entries = [
        item
        for item in entries
        if item.get("schema_version") == PROVIDER_POLICY_SCHEMA_VERSION
        and item.get("event_type") == "provider_policy_verified"
        and item.get("current_stage") == current_stage
        and item.get("next_stage") == next_stage
        and item.get("artifact_sha256", {}).get("policy_activation")
        == policy_activation_hash
    ]
    if len(matching_policy_entries) != 1:
        raise ReleaseLedgerError(
            "bounded_expansion_verified requires the matching provider_policy_verified ledger event."
        )
    prior_scale = [
        item for item in entries
        if item.get("event_type") == "bounded_expansion_verified"
        and item.get("next_stage") == next_stage
    ]
    if prior_scale:
        raise ReleaseLedgerError("This bounded expansion stage is already recorded in the release ledger.")

    core = {
        "schema_version": SCALE_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "bounded_expansion_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "artifact_sha256": {
            "scale_decision": file_sha256(scale_decision),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "scale_activation": file_sha256(scale_activation),
        },
        "previous_entry_hash": state["head_entry_hash"] or ZERO_HASH,
    }
    entry_hash, tag = sign_entry(core, key)
    entry = {**core, "entry_hash": entry_hash, "hmac_sha256": tag}
    serialized = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for item in [*entries, entry]
    )
    atomic_write(ledger, serialized)
    return entry



def append_provider_policy_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    next_stage: str,
    provider_policy: Path,
    deployment_change: Path,
    operator_status: Path,
    policy_activation: Path,
    created_at: str | None = None,
) -> dict:
    if not actor_reference.strip() or len(actor_reference) > 500:
        raise ReleaseLedgerError(
            "actor_reference must be non-empty and at most 500 characters."
        )
    if not change_reference.strip() or len(change_reference) > 500:
        raise ReleaseLedgerError(
            "change_reference must be non-empty and at most 500 characters."
        )
    if not current_stage.strip() or not next_stage.strip():
        raise ReleaseLedgerError(
            "Provider policy ledger event requires current_stage and next_stage."
        )

    policy = load_json_object(provider_policy, "provider policy")
    deployment = load_json_object(
        deployment_change,
        "provider policy deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-policy operator status",
    )
    activation = load_json_object(
        policy_activation,
        "provider policy activation evidence",
    )

    for label, value in (
        ("provider policy", policy),
        ("deployment change", deployment),
        ("operator status", status),
        ("provider policy activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    if policy.get("decision") != "ELIGIBLE_FOR_POLICY_REVIEW":
        raise ReleaseLedgerError(
            "provider_policy_verified requires an eligible provider policy."
        )
    if policy.get("failures") != []:
        raise ReleaseLedgerError(
            "provider_policy_verified requires a failure-free provider policy."
        )
    if (
        policy.get("current_stage") != current_stage
        or policy.get("proposed_stage") != next_stage
    ):
        raise ReleaseLedgerError(
            "Provider policy stages do not match the ledger event."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Provider policy deployment current_stage does not match."
        )
    if deployment.get("proposed_stage") != next_stage:
        raise ReleaseLedgerError(
            "Provider policy deployment proposed_stage does not match."
        )
    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Provider policy deployment change reference does not match."
        )
    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "provider_policy_verified requires a clean post-policy operator status."
        )
    if activation.get("status") != "provider_policy_verified":
        raise ReleaseLedgerError(
            "Provider policy activation evidence has not passed."
        )
    if (
        activation.get("current_stage") != current_stage
        or activation.get("proposed_stage") != next_stage
    ):
        raise ReleaseLedgerError(
            "Provider policy activation stages do not match."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Provider policy activation change reference does not match."
        )

    hashes = activation.get("artifact_sha256")
    if not isinstance(hashes, dict):
        raise ReleaseLedgerError(
            "Provider policy activation evidence has no artifact hashes."
        )
    expected_bound = {
        "provider_policy": file_sha256(provider_policy),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Provider policy activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the provider-policy event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "provider_policy_verified requires an existing ledger chain that reached current_stage."
        )
    duplicates = [
        item
        for item in entries
        if item.get("event_type") == "provider_policy_verified"
        and item.get("current_stage") == current_stage
        and item.get("next_stage") == next_stage
        and item.get("artifact_sha256", {}).get("provider_policy")
        == file_sha256(provider_policy)
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This provider policy activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": PROVIDER_POLICY_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "provider_policy_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "artifact_sha256": {
            "provider_policy": file_sha256(provider_policy),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "policy_activation": file_sha256(policy_activation),
        },
        "previous_entry_hash": state["head_entry_hash"] or ZERO_HASH,
    }
    entry_hash, tag = sign_entry(core, key)
    entry = {
        **core,
        "entry_hash": entry_hash,
        "hmac_sha256": tag,
    }
    serialized = "".join(
        json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ) + "\n"
        for item in [*entries, entry]
    )
    atomic_write(ledger, serialized)
    return entry



def append_microsoft_rollout_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    staging_evidence: Path,
    deployment_change: Path,
    operator_status: Path,
    rollout_activation: Path,
    created_at: str | None = None,
) -> dict:
    if not actor_reference.strip() or len(actor_reference) > 500:
        raise ReleaseLedgerError(
            "actor_reference must be non-empty and at most 500 characters."
        )
    if not change_reference.strip() or len(change_reference) > 500:
        raise ReleaseLedgerError(
            "change_reference must be non-empty and at most 500 characters."
        )
    if not current_stage.strip() or len(current_stage) > 100:
        raise ReleaseLedgerError(
            "Microsoft rollout ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "Microsoft live staging evidence",
    )
    deployment = load_json_object(
        deployment_change,
        "Microsoft rollout deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-Microsoft-rollout operator status",
    )
    activation = load_json_object(
        rollout_activation,
        "Microsoft rollout activation evidence",
    )

    for label, value in (
        ("deployment change", deployment),
        ("operator status", status),
        ("Microsoft rollout activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    staged = staging.get("microsoft_actions")
    if (
        not isinstance(staged, dict)
        or staged.get("status") != "passed"
        or not isinstance(staged.get("evidence"), str)
        or not staged["evidence"].strip()
        or not isinstance(staged.get("verified_at"), str)
    ):
        raise ReleaseLedgerError(
            "microsoft_rollout_verified requires passed timestamped Microsoft live staging evidence."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Microsoft rollout deployment change reference does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Microsoft rollout deployment does not bind this staging evidence."
        )
    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "microsoft_rollout_verified requires a clean post-deploy operator status."
        )
    if activation.get("status") != "microsoft_rollout_verified":
        raise ReleaseLedgerError(
            "Microsoft rollout activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Microsoft rollout activation change reference does not match."
        )

    expected_deployment = {
        "deployed_at": deployment.get("deployed_at"),
        "frontend_base_url": deployment.get("frontend_base_url"),
        "frontend_source_revision": deployment.get(
            "frontend_source_revision"
        ),
    }
    for name, value in expected_deployment.items():
        if activation.get(name) != value:
            raise ReleaseLedgerError(
                f"Microsoft rollout activation does not bind deployment field {name}."
            )

    backend = activation.get("backend")
    frontend = activation.get("frontend")
    if (
        not isinstance(backend, dict)
        or backend.get("actions_enabled") is not True
        or backend.get("microsoft_actions_enabled") is not True
        or not isinstance(frontend, dict)
        or frontend.get("coworker_enabled") is not True
        or frontend.get("microsoft_actions_enabled") is not True
    ):
        raise ReleaseLedgerError(
            "Microsoft rollout activation does not prove enabled backend/frontend rollout controls."
        )

    hashes = activation.get("artifact_sha256")
    if not isinstance(hashes, dict):
        raise ReleaseLedgerError(
            "Microsoft rollout activation evidence has no artifact hashes."
        )
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "operator_status": file_sha256(operator_status),
    }
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Microsoft rollout activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the Microsoft rollout event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "microsoft_rollout_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(rollout_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == MICROSOFT_ROLLOUT_SCHEMA_VERSION
        and item.get("event_type") == "microsoft_rollout_verified"
        and item.get("artifact_sha256", {}).get("rollout_activation")
        == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This Microsoft rollout activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": MICROSOFT_ROLLOUT_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "microsoft_rollout_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "rollout_activation": activation_hash,
        },
        "previous_entry_hash": state["head_entry_hash"] or ZERO_HASH,
    }
    entry_hash, tag = sign_entry(core, key)
    entry = {
        **core,
        "entry_hash": entry_hash,
        "hmac_sha256": tag,
    }
    serialized = "".join(
        json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ) + "\n"
        for item in [*entries, entry]
    )
    atomic_write(ledger, serialized)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Maintain a tamper-evident Shuddho controlled-cohort release ledger."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    append_parser = sub.add_parser("append")
    append_parser.add_argument("--ledger", type=Path, required=True)
    append_parser.add_argument("--release-id", required=True)
    append_parser.add_argument("--event-type", choices=sorted(EVENT_DECISIONS), required=True)
    append_parser.add_argument("--actor-reference", required=True)
    append_parser.add_argument("--change-reference", required=True)
    append_parser.add_argument("--current-stage", required=True)
    append_parser.add_argument("--next-stage")
    append_parser.add_argument("--rollout", type=Path, required=True)
    append_parser.add_argument("--canary-plan", type=Path, required=True)
    append_parser.add_argument("--progression-decision", type=Path, required=True)
    append_parser.add_argument("--operator-status", type=Path, required=True)

    rollback_parser = sub.add_parser("append-rollback")
    rollback_parser.add_argument("--ledger", type=Path, required=True)
    rollback_parser.add_argument("--release-id", required=True)
    rollback_parser.add_argument("--actor-reference", required=True)
    rollback_parser.add_argument("--change-reference", required=True)
    rollback_parser.add_argument("--current-stage", required=True)
    rollback_parser.add_argument("--rollout", type=Path, required=True)
    rollback_parser.add_argument("--canary-plan", type=Path, required=True)
    rollback_parser.add_argument("--progression-decision", type=Path, required=True)
    rollback_parser.add_argument("--operator-status", type=Path, required=True)
    rollback_parser.add_argument("--rollback-completion", type=Path, required=True)

    recovery_parser = sub.add_parser("append-recovery")
    recovery_parser.add_argument("--ledger", type=Path, required=True)
    recovery_parser.add_argument("--release-id", required=True)
    recovery_parser.add_argument("--actor-reference", required=True)
    recovery_parser.add_argument("--change-reference", required=True)
    recovery_parser.add_argument("--current-stage", required=True)
    recovery_parser.add_argument("--rollout", type=Path, required=True)
    recovery_parser.add_argument("--canary-plan", type=Path, required=True)
    recovery_parser.add_argument("--progression-decision", type=Path, required=True)
    recovery_parser.add_argument("--operator-status", type=Path, required=True)
    recovery_parser.add_argument("--rollback-completion", type=Path, required=True)
    recovery_parser.add_argument("--recovery-verification", type=Path, required=True)

    scale_parser = sub.add_parser("append-scale")
    scale_parser.add_argument("--ledger", type=Path, required=True)
    scale_parser.add_argument("--release-id", required=True)
    scale_parser.add_argument("--actor-reference", required=True)
    scale_parser.add_argument("--change-reference", required=True)
    scale_parser.add_argument("--current-stage", required=True)
    scale_parser.add_argument("--next-stage", required=True)
    scale_parser.add_argument("--scale-decision", type=Path, required=True)
    scale_parser.add_argument("--deployment-change", type=Path, required=True)
    scale_parser.add_argument("--operator-status", type=Path, required=True)
    scale_parser.add_argument("--scale-activation", type=Path, required=True)

    policy_parser = sub.add_parser("append-provider-policy")
    policy_parser.add_argument("--ledger", type=Path, required=True)
    policy_parser.add_argument("--release-id", required=True)
    policy_parser.add_argument("--actor-reference", required=True)
    policy_parser.add_argument("--change-reference", required=True)
    policy_parser.add_argument("--current-stage", required=True)
    policy_parser.add_argument("--next-stage", required=True)
    policy_parser.add_argument("--provider-policy", type=Path, required=True)
    policy_parser.add_argument("--deployment-change", type=Path, required=True)
    policy_parser.add_argument("--operator-status", type=Path, required=True)
    policy_parser.add_argument("--policy-activation", type=Path, required=True)

    microsoft_parser = sub.add_parser("append-microsoft-rollout")
    microsoft_parser.add_argument("--ledger", type=Path, required=True)
    microsoft_parser.add_argument("--release-id", required=True)
    microsoft_parser.add_argument("--actor-reference", required=True)
    microsoft_parser.add_argument("--change-reference", required=True)
    microsoft_parser.add_argument("--current-stage", required=True)
    microsoft_parser.add_argument("--staging-evidence", type=Path, required=True)
    microsoft_parser.add_argument("--deployment-change", type=Path, required=True)
    microsoft_parser.add_argument("--operator-status", type=Path, required=True)
    microsoft_parser.add_argument("--rollout-activation", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--ledger", type=Path, required=True)

    args = parser.parse_args()
    try:
        key = ledger_key()
        if args.command == "verify":
            result = verify_entries(read_entries(args.ledger), key)
        elif args.command == "append-rollback":
            entry = append_rollback_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                rollout=args.rollout,
                canary_plan=args.canary_plan,
                progression_decision=args.progression_decision,
                operator_status=args.operator_status,
                rollback_completion=args.rollback_completion,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-provider-policy":
            entry = append_provider_policy_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                next_stage=args.next_stage,
                provider_policy=args.provider_policy,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                policy_activation=args.policy_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-microsoft-rollout":
            entry = append_microsoft_rollout_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                rollout_activation=args.rollout_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-scale":
            entry = append_scale_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                next_stage=args.next_stage,
                scale_decision=args.scale_decision,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                scale_activation=args.scale_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-recovery":
            entry = append_recovery_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                rollout=args.rollout,
                canary_plan=args.canary_plan,
                progression_decision=args.progression_decision,
                operator_status=args.operator_status,
                rollback_completion=args.rollback_completion,
                recovery_verification=args.recovery_verification,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        else:
            entry = append_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                event_type=args.event_type,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                next_stage=args.next_stage,
                rollout=args.rollout,
                canary_plan=args.canary_plan,
                progression_decision=args.progression_decision,
                operator_status=args.operator_status,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        print(json.dumps(result, indent=2))
    except (ReleaseLedgerError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
