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
ACTION_SELECTION_SCHEMA_VERSION = 7
ACTION_PROPOSALS_SCHEMA_VERSION = 8
ACTION_ATTACHMENTS_SCHEMA_VERSION = 9
ACTION_REMINDERS_SCHEMA_VERSION = 10
ACTION_RECIPIENTS_SCHEMA_VERSION = 11
ACTION_DOCUMENT_SHARING_SCHEMA_VERSION = 12
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
ACTION_SELECTION_ARTIFACT_KEYS = {
    "staging_evidence",
    "deployment_change",
    "operator_status",
    "action_selection_activation",
}
ACTION_PROPOSALS_ARTIFACT_KEYS = {
    "staging_evidence",
    "rollout_manifest",
    "deployment_change",
    "operator_status",
    "action_proposals_activation",
}
ACTION_ATTACHMENTS_ARTIFACT_KEYS = {
    "staging_evidence",
    "rollout_manifest",
    "deployment_change",
    "operator_status",
    "action_attachments_activation",
}
ACTION_REMINDERS_ARTIFACT_KEYS = {
    "staging_evidence",
    "rollout_manifest",
    "deployment_change",
    "operator_status",
    "action_reminders_activation",
}
ACTION_RECIPIENTS_ARTIFACT_KEYS = {
    "staging_evidence",
    "rollout_manifest",
    "deployment_change",
    "operator_status",
    "action_recipients_activation",
}
ACTION_DOCUMENT_SHARING_ARTIFACT_KEYS = {
    "staging_evidence",
    "rollout_manifest",
    "deployment_change",
    "operator_status",
    "action_document_sharing_activation",
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


def normalized_action_providers(rollout: dict) -> list[str]:
    capabilities = rollout.get("capabilities")
    actions_enabled = (
        isinstance(capabilities, dict)
        and capabilities.get("actions") is True
    )
    providers = rollout.get("action_providers")
    if providers is None:
        return ["google"] if actions_enabled else []
    if (
        not isinstance(providers, list)
        or any(
            not isinstance(item, str)
            or item not in {"google", "microsoft"}
            for item in providers
        )
        or len(providers) != len(set(providers))
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has an invalid action provider set."
        )
    if providers and not actions_enabled:
        raise ReleaseLedgerError(
            "Reviewed rollout declares action providers while actions are disabled."
        )
    if actions_enabled and "google" not in providers:
        raise ReleaseLedgerError(
            "Reviewed action rollout must retain the Google provider baseline."
        )
    return sorted(providers)


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
            ACTION_SELECTION_SCHEMA_VERSION,
            ACTION_PROPOSALS_SCHEMA_VERSION,
            ACTION_ATTACHMENTS_SCHEMA_VERSION,
            ACTION_REMINDERS_SCHEMA_VERSION,
            ACTION_RECIPIENTS_SCHEMA_VERSION,
            ACTION_DOCUMENT_SHARING_SCHEMA_VERSION,
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
        if (
            version == ACTION_SELECTION_SCHEMA_VERSION
            and event_type != "action_selection_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v7 event type."
            )
        if (
            version == ACTION_PROPOSALS_SCHEMA_VERSION
            and event_type != "action_proposals_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v8 event type."
            )
        if (
            version == ACTION_ATTACHMENTS_SCHEMA_VERSION
            and event_type != "action_attachments_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v9 event type."
            )
        if (
            version == ACTION_REMINDERS_SCHEMA_VERSION
            and event_type != "action_reminders_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v10 event type."
            )
        if (
            version == ACTION_RECIPIENTS_SCHEMA_VERSION
            and event_type != "action_recipients_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v11 event type."
            )
        if (
            version == ACTION_DOCUMENT_SHARING_SCHEMA_VERSION
            and event_type != "action_document_sharing_verified"
        ):
            raise ReleaseLedgerError(
                f"Ledger entry {index} has an unsupported schema-v12 event type."
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
            if version == MICROSOFT_ROLLOUT_SCHEMA_VERSION
            else ACTION_SELECTION_ARTIFACT_KEYS
            if version == ACTION_SELECTION_SCHEMA_VERSION
            else ACTION_PROPOSALS_ARTIFACT_KEYS
            if version == ACTION_PROPOSALS_SCHEMA_VERSION
            else ACTION_ATTACHMENTS_ARTIFACT_KEYS
            if version == ACTION_ATTACHMENTS_SCHEMA_VERSION
            else ACTION_REMINDERS_ARTIFACT_KEYS
            if version == ACTION_REMINDERS_SCHEMA_VERSION
            else ACTION_RECIPIENTS_ARTIFACT_KEYS
            if version == ACTION_RECIPIENTS_SCHEMA_VERSION
            else ACTION_DOCUMENT_SHARING_ARTIFACT_KEYS
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




def verified_release_entries(
    ledger: Path,
    release_id: str,
) -> tuple[list[dict], dict]:
    entries = read_entries(ledger)
    state = verify_entries(entries, ledger_key())
    if state.get("release_id") != release_id:
        raise ReleaseLedgerError(
            "Release ledger release_id does not match the expected release."
        )
    return entries, state


def require_exact_attested_event(
    entries: list[dict],
    *,
    schema_version: int,
    event_type: str,
    current_stage: str,
    next_stage: str | None,
    artifact_key: str,
    artifact_sha256: str,
    after_sequence: int | None = None,
    expected_sequence: int | None = None,
    expected_entry_hash: str | None = None,
    label: str = "release attestation",
) -> dict:
    if not valid_hash(artifact_sha256):
        raise ReleaseLedgerError(
            f"{label} requires a valid artifact SHA-256."
        )
    matches = [
        item
        for item in entries
        if item.get("schema_version") == schema_version
        and item.get("event_type") == event_type
        and item.get("current_stage") == current_stage
        and item.get("next_stage") == next_stage
        and item.get("artifact_sha256", {}).get(artifact_key)
        == artifact_sha256
        and (
            after_sequence is None
            or item.get("sequence", 0) > after_sequence
        )
    ]
    if len(matches) != 1:
        raise ReleaseLedgerError(
            f"{label} requires exactly one matching ledger event."
        )
    entry = matches[0]
    if (
        expected_sequence is not None
        and entry.get("sequence") != expected_sequence
    ):
        raise ReleaseLedgerError(
            f"{label} ledger sequence does not match."
        )
    if (
        expected_entry_hash is not None
        and entry.get("entry_hash") != expected_entry_hash
    ):
        raise ReleaseLedgerError(
            f"{label} ledger entry hash does not match."
        )
    return entry


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

    recovery_schema = recovery_value.get("schema_version")
    if recovery_schema in {2, 3, 4, 5, 6, 7}:
        requirements = recovery_value.get("runtime_requirements")
        expected_requirement_keys = {
            "microsoft_actions_enabled",
            "action_selection_enabled",
        }
        if recovery_schema in {3, 4, 5, 6, 7}:
            expected_requirement_keys.add("action_proposals_enabled")
        if recovery_schema in {4, 5, 6, 7}:
            expected_requirement_keys.add("action_attachments_enabled")
        if recovery_schema in {5, 6, 7}:
            expected_requirement_keys.add("action_reminders_enabled")
        if recovery_schema in {6, 7}:
            expected_requirement_keys.add("action_recipients_enabled")
        if recovery_schema == 7:
            expected_requirement_keys.add("action_document_sharing_enabled")
        if (
            not isinstance(requirements, dict)
            or set(requirements) != expected_requirement_keys
            or any(not isinstance(value, bool) for value in requirements.values())
        ):
            raise ReleaseLedgerError(
                f"Schema-v{recovery_schema} recovery evidence has invalid runtime_requirements."
            )

        microsoft_required = requirements["microsoft_actions_enabled"]
        microsoft_hash = recovery_hashes.get("microsoft_rollout_activation")
        microsoft_summary = recovery_value.get("microsoft_rollout")
        if microsoft_required:
            if not valid_hash(microsoft_hash) or not isinstance(microsoft_summary, dict):
                raise ReleaseLedgerError(
                    "Microsoft-enabled recovery evidence is missing its required attestation."
                )
            require_exact_attested_event(
                entries,
                schema_version=MICROSOFT_ROLLOUT_SCHEMA_VERSION,
                event_type="microsoft_rollout_verified",
                current_stage=current_stage,
                next_stage=None,
                artifact_key="rollout_activation",
                artifact_sha256=microsoft_hash,
                after_sequence=rollback_entry["sequence"],
                expected_sequence=microsoft_summary.get("ledger_sequence"),
                expected_entry_hash=microsoft_summary.get("ledger_entry_hash"),
                label="Microsoft recovery attestation",
            )
        elif microsoft_hash is not None or microsoft_summary is not None:
            raise ReleaseLedgerError(
                "Recovery evidence contains Microsoft attestation data while Microsoft is not required."
            )

        action_required = requirements["action_selection_enabled"]
        action_hash = recovery_hashes.get("action_selection_activation")
        action_summary = recovery_value.get("action_selection")
        if action_required:
            if not valid_hash(action_hash) or not isinstance(action_summary, dict):
                raise ReleaseLedgerError(
                    "Action-selection recovery evidence is missing its required attestation."
                )
            require_exact_attested_event(
                entries,
                schema_version=ACTION_SELECTION_SCHEMA_VERSION,
                event_type="action_selection_verified",
                current_stage=current_stage,
                next_stage=None,
                artifact_key="action_selection_activation",
                artifact_sha256=action_hash,
                after_sequence=rollback_entry["sequence"],
                expected_sequence=action_summary.get("ledger_sequence"),
                expected_entry_hash=action_summary.get("ledger_entry_hash"),
                label="Action-selection recovery attestation",
            )
        elif action_hash is not None or action_summary is not None:
            raise ReleaseLedgerError(
                "Recovery evidence contains action-selection attestation data while action selection is not required."
            )

        if recovery_schema in {3, 4, 5, 6, 7}:
            proposals_required = requirements["action_proposals_enabled"]
            proposals_hash = recovery_hashes.get("action_proposals_activation")
            proposals_summary = recovery_value.get("action_proposals")
            if proposals_required:
                if not valid_hash(proposals_hash) or not isinstance(proposals_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-proposals recovery evidence is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_PROPOSALS_SCHEMA_VERSION,
                    event_type="action_proposals_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_proposals_activation",
                    artifact_sha256=proposals_hash,
                    after_sequence=rollback_entry["sequence"],
                    expected_sequence=proposals_summary.get("ledger_sequence"),
                    expected_entry_hash=proposals_summary.get("ledger_entry_hash"),
                    label="Action-proposals recovery attestation",
                )
            elif proposals_hash is not None or proposals_summary is not None:
                raise ReleaseLedgerError(
                    "Recovery evidence contains action-proposals attestation data while action proposals are not required."
                )

        if recovery_schema in {4, 5, 6, 7}:
            attachments_required = requirements["action_attachments_enabled"]
            attachments_hash = recovery_hashes.get("action_attachments_activation")
            attachments_summary = recovery_value.get("action_attachments")
            if attachments_required:
                if not valid_hash(attachments_hash) or not isinstance(attachments_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-attachments recovery evidence is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_ATTACHMENTS_SCHEMA_VERSION,
                    event_type="action_attachments_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_attachments_activation",
                    artifact_sha256=attachments_hash,
                    after_sequence=rollback_entry["sequence"],
                    expected_sequence=attachments_summary.get("ledger_sequence"),
                    expected_entry_hash=attachments_summary.get("ledger_entry_hash"),
                    label="Action-attachments recovery attestation",
                )
            elif attachments_hash is not None or attachments_summary is not None:
                raise ReleaseLedgerError(
                    "Recovery evidence contains action-attachments attestation data while action attachments are not required."
                )

        if recovery_schema in {5, 6, 7}:
            reminders_required = requirements["action_reminders_enabled"]
            reminders_hash = recovery_hashes.get("action_reminders_activation")
            reminders_summary = recovery_value.get("action_reminders")
            if reminders_required:
                if not valid_hash(reminders_hash) or not isinstance(reminders_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-reminders recovery evidence is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_REMINDERS_SCHEMA_VERSION,
                    event_type="action_reminders_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_reminders_activation",
                    artifact_sha256=reminders_hash,
                    after_sequence=rollback_entry["sequence"],
                    expected_sequence=reminders_summary.get("ledger_sequence"),
                    expected_entry_hash=reminders_summary.get("ledger_entry_hash"),
                    label="Action-reminders recovery attestation",
                )
            elif reminders_hash is not None or reminders_summary is not None:
                raise ReleaseLedgerError(
                    "Recovery evidence contains action-reminders attestation data while action reminders are not required."
                )

        if recovery_schema in {6, 7}:
            recipients_required = requirements["action_recipients_enabled"]
            recipients_hash = recovery_hashes.get("action_recipients_activation")
            recipients_summary = recovery_value.get("action_recipients")
            if recipients_required:
                if not valid_hash(recipients_hash) or not isinstance(recipients_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-recipients recovery evidence is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_RECIPIENTS_SCHEMA_VERSION,
                    event_type="action_recipients_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_recipients_activation",
                    artifact_sha256=recipients_hash,
                    after_sequence=rollback_entry["sequence"],
                    expected_sequence=recipients_summary.get("ledger_sequence"),
                    expected_entry_hash=recipients_summary.get("ledger_entry_hash"),
                    label="Action-recipients recovery attestation",
                )
            elif recipients_hash is not None or recipients_summary is not None:
                raise ReleaseLedgerError(
                    "Recovery evidence contains action-recipients attestation data while action recipients are not required."
                )

        if recovery_schema == 7:
            document_required = requirements["action_document_sharing_enabled"]
            document_hash = recovery_hashes.get("action_document_sharing_activation")
            document_summary = recovery_value.get("action_document_sharing")
            if document_required:
                if not valid_hash(document_hash) or not isinstance(document_summary, dict):
                    raise ReleaseLedgerError(
                        "Document-sharing recovery evidence is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_DOCUMENT_SHARING_SCHEMA_VERSION,
                    event_type="action_document_sharing_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_document_sharing_activation",
                    artifact_sha256=document_hash,
                    after_sequence=rollback_entry["sequence"],
                    expected_sequence=document_summary.get("ledger_sequence"),
                    expected_entry_hash=document_summary.get("ledger_entry_hash"),
                    label="Document-sharing recovery attestation",
                )
            elif document_hash is not None or document_summary is not None:
                raise ReleaseLedgerError(
                    "Recovery evidence contains document-sharing attestation data while document sharing is not required."
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

    activation_schema = activation.get("schema_version")
    if activation_schema in {2, 3, 4, 5, 6, 7}:
        requirements = activation.get("runtime_requirements")
        expected_requirement_keys = {
            "microsoft_actions_enabled",
            "action_selection_enabled",
        }
        if activation_schema in {3, 4, 5, 6, 7}:
            expected_requirement_keys.add("action_proposals_enabled")
        if activation_schema in {4, 5, 6, 7}:
            expected_requirement_keys.add("action_attachments_enabled")
        if activation_schema in {5, 6, 7}:
            expected_requirement_keys.add("action_reminders_enabled")
        if activation_schema in {6, 7}:
            expected_requirement_keys.add("action_recipients_enabled")
        if activation_schema == 7:
            expected_requirement_keys.add("action_document_sharing_enabled")
        if (
            not isinstance(requirements, dict)
            or set(requirements) != expected_requirement_keys
            or any(not isinstance(value, bool) for value in requirements.values())
        ):
            raise ReleaseLedgerError(
                f"Schema-v{activation_schema} scale activation has invalid runtime_requirements."
            )

        microsoft_required = requirements["microsoft_actions_enabled"]
        microsoft_hash = hashes.get("microsoft_rollout_activation")
        if microsoft_required:
            if not valid_hash(microsoft_hash):
                raise ReleaseLedgerError(
                    "Microsoft-enabled scale activation is missing its required attestation."
                )
            require_exact_attested_event(
                entries,
                schema_version=MICROSOFT_ROLLOUT_SCHEMA_VERSION,
                event_type="microsoft_rollout_verified",
                current_stage=current_stage,
                next_stage=None,
                artifact_key="rollout_activation",
                artifact_sha256=microsoft_hash,
                label="Microsoft scale attestation",
            )
        elif microsoft_hash is not None:
            raise ReleaseLedgerError(
                "Scale activation contains Microsoft attestation data while Microsoft is not required."
            )

        action_required = requirements["action_selection_enabled"]
        action_hash = hashes.get("action_selection_activation")
        action_summary = activation.get("action_selection")
        if action_required:
            if not valid_hash(action_hash) or not isinstance(action_summary, dict):
                raise ReleaseLedgerError(
                    "Action-selection scale activation is missing its required attestation."
                )
            require_exact_attested_event(
                entries,
                schema_version=ACTION_SELECTION_SCHEMA_VERSION,
                event_type="action_selection_verified",
                current_stage=current_stage,
                next_stage=None,
                artifact_key="action_selection_activation",
                artifact_sha256=action_hash,
                expected_sequence=action_summary.get("ledger_sequence"),
                expected_entry_hash=action_summary.get("ledger_entry_hash"),
                label="Action-selection scale attestation",
            )
        elif action_hash is not None or action_summary is not None:
            raise ReleaseLedgerError(
                "Scale activation contains action-selection attestation data while action selection is not required."
            )

        if activation_schema in {3, 4, 5, 6, 7}:
            proposals_required = requirements["action_proposals_enabled"]
            proposals_hash = hashes.get("action_proposals_activation")
            proposals_summary = activation.get("action_proposals")
            if proposals_required:
                if not valid_hash(proposals_hash) or not isinstance(proposals_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-proposals scale activation is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_PROPOSALS_SCHEMA_VERSION,
                    event_type="action_proposals_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_proposals_activation",
                    artifact_sha256=proposals_hash,
                    expected_sequence=proposals_summary.get("ledger_sequence"),
                    expected_entry_hash=proposals_summary.get("ledger_entry_hash"),
                    label="Action-proposals scale attestation",
                )
            elif proposals_hash is not None or proposals_summary is not None:
                raise ReleaseLedgerError(
                    "Scale activation contains action-proposals attestation data while action proposals are not required."
                )

        if activation_schema in {4, 5, 6, 7}:
            attachments_required = requirements["action_attachments_enabled"]
            attachments_hash = hashes.get("action_attachments_activation")
            attachments_summary = activation.get("action_attachments")
            if attachments_required:
                if not valid_hash(attachments_hash) or not isinstance(attachments_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-attachments scale activation is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_ATTACHMENTS_SCHEMA_VERSION,
                    event_type="action_attachments_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_attachments_activation",
                    artifact_sha256=attachments_hash,
                    expected_sequence=attachments_summary.get("ledger_sequence"),
                    expected_entry_hash=attachments_summary.get("ledger_entry_hash"),
                    label="Action-attachments scale attestation",
                )
            elif attachments_hash is not None or attachments_summary is not None:
                raise ReleaseLedgerError(
                    "Scale activation contains action-attachments attestation data while action attachments are not required."
                )

        if activation_schema in {5, 6, 7}:
            reminders_required = requirements["action_reminders_enabled"]
            reminders_hash = hashes.get("action_reminders_activation")
            reminders_summary = activation.get("action_reminders")
            if reminders_required:
                if not valid_hash(reminders_hash) or not isinstance(reminders_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-reminders scale activation is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_REMINDERS_SCHEMA_VERSION,
                    event_type="action_reminders_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_reminders_activation",
                    artifact_sha256=reminders_hash,
                    expected_sequence=reminders_summary.get("ledger_sequence"),
                    expected_entry_hash=reminders_summary.get("ledger_entry_hash"),
                    label="Action-reminders scale attestation",
                )
            elif reminders_hash is not None or reminders_summary is not None:
                raise ReleaseLedgerError(
                    "Scale activation contains action-reminders attestation data while action reminders are not required."
                )

        if activation_schema in {6, 7}:
            recipients_required = requirements["action_recipients_enabled"]
            recipients_hash = hashes.get("action_recipients_activation")
            recipients_summary = activation.get("action_recipients")
            if recipients_required:
                if not valid_hash(recipients_hash) or not isinstance(recipients_summary, dict):
                    raise ReleaseLedgerError(
                        "Action-recipients scale activation is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_RECIPIENTS_SCHEMA_VERSION,
                    event_type="action_recipients_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_recipients_activation",
                    artifact_sha256=recipients_hash,
                    expected_sequence=recipients_summary.get("ledger_sequence"),
                    expected_entry_hash=recipients_summary.get("ledger_entry_hash"),
                    label="Action-recipients scale attestation",
                )
            elif recipients_hash is not None or recipients_summary is not None:
                raise ReleaseLedgerError(
                    "Scale activation contains action-recipients attestation data while action recipients are not required."
                )

        if activation_schema == 7:
            document_required = requirements["action_document_sharing_enabled"]
            document_hash = hashes.get("action_document_sharing_activation")
            document_summary = activation.get("action_document_sharing")
            if document_required:
                if not valid_hash(document_hash) or not isinstance(document_summary, dict):
                    raise ReleaseLedgerError(
                        "Document-sharing scale activation is missing its required attestation."
                    )
                require_exact_attested_event(
                    entries,
                    schema_version=ACTION_DOCUMENT_SHARING_SCHEMA_VERSION,
                    event_type="action_document_sharing_verified",
                    current_stage=current_stage,
                    next_stage=None,
                    artifact_key="action_document_sharing_activation",
                    artifact_sha256=document_hash,
                    expected_sequence=document_summary.get("ledger_sequence"),
                    expected_entry_hash=document_summary.get("ledger_entry_hash"),
                    label="Document-sharing scale attestation",
                )
            elif document_hash is not None or document_summary is not None:
                raise ReleaseLedgerError(
                    "Scale activation contains document-sharing attestation data while document sharing is not required."
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



def append_action_selection_event(
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
    action_selection_activation: Path,
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
            "Action-selection ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "action-selection live staging evidence",
    )
    deployment = load_json_object(
        deployment_change,
        "action-selection deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-action-selection operator status",
    )
    activation = load_json_object(
        action_selection_activation,
        "action-selection activation evidence",
    )

    for label, value in (
        ("deployment change", deployment),
        ("operator status", status),
        ("action-selection activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    staged = staging.get("action_selection")
    if (
        not isinstance(staged, dict)
        or staged.get("status") != "passed"
        or not isinstance(staged.get("evidence"), str)
        or not staged["evidence"].strip()
        or not isinstance(staged.get("verified_at"), str)
    ):
        raise ReleaseLedgerError(
            "action_selection_verified requires passed timestamped action-selection staging evidence."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-selection deployment change reference does not match."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-selection deployment current_stage does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Action-selection deployment does not bind this staging evidence."
        )
    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "action_selection_verified requires a clean post-deploy operator status."
        )
    if activation.get("status") != "action_selection_verified":
        raise ReleaseLedgerError(
            "Action-selection activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-selection activation change reference does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-selection activation current_stage does not match."
        )
    if activation.get("deployed_at") != deployment.get("deployed_at"):
        raise ReleaseLedgerError(
            "Action-selection activation does not bind deployment time."
        )

    runtime = activation.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("coworker_enabled") is not True
        or runtime.get("agent_runtime_enabled") is not True
        or runtime.get("intelligent_planner_enabled") is not True
        or runtime.get("actions_enabled") is not True
        or runtime.get("action_selection_enabled") is not True
        or runtime.get("cohort_enforced") is not True
    ):
        raise ReleaseLedgerError(
            "Action-selection activation does not prove required deployed runtime controls."
        )

    hashes = activation.get("artifact_sha256")
    if not isinstance(hashes, dict):
        raise ReleaseLedgerError(
            "Action-selection activation evidence has no artifact hashes."
        )
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Action-selection activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the action-selection event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "action_selection_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(action_selection_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == ACTION_SELECTION_SCHEMA_VERSION
        and item.get("event_type") == "action_selection_verified"
        and item.get("artifact_sha256", {}).get(
            "action_selection_activation"
        ) == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This action-selection activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": ACTION_SELECTION_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "action_selection_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "action_selection_activation": activation_hash,
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


def append_action_proposals_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    staging_evidence: Path,
    rollout_manifest: Path,
    deployment_change: Path,
    operator_status: Path,
    action_proposals_activation: Path,
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
            "Action-proposals ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "action-proposal live staging evidence",
    )
    rollout = load_json_object(
        rollout_manifest,
        "reviewed action-proposal rollout manifest",
    )
    deployment = load_json_object(
        deployment_change,
        "action-proposal deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-action-proposal operator status",
    )
    activation = load_json_object(
        action_proposals_activation,
        "action-proposal activation evidence",
    )

    for label, value in (
        ("rollout manifest", rollout),
        ("deployment change", deployment),
        ("operator status", status),
        ("action-proposal activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    staged = staging.get("action_proposals")
    if (
        not isinstance(staged, dict)
        or staged.get("status") != "passed"
        or not isinstance(staged.get("evidence"), str)
        or not staged["evidence"].strip()
        or not isinstance(staged.get("verified_at"), str)
    ):
        raise ReleaseLedgerError(
            "action_proposals_verified requires passed timestamped action-proposal staging evidence."
        )

    if rollout.get("environment") != "production":
        raise ReleaseLedgerError(
            "action_proposals_verified requires a production rollout manifest."
        )
    incident = rollout.get("incident")
    if (
        not isinstance(incident, dict)
        or incident.get("change_reference") != change_reference
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout change reference does not match."
        )
    rollout_cohort = rollout.get("cohort")
    if (
        not isinstance(rollout_cohort, dict)
        or not isinstance(rollout_cohort.get("max_users"), int)
        or isinstance(rollout_cohort.get("max_users"), bool)
        or rollout_cohort["max_users"] < 1
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has an invalid cohort ceiling."
        )
    capabilities = rollout.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or any(not isinstance(value, bool) for value in capabilities.values())
        or capabilities.get("coworker") is not True
        or capabilities.get("agent_runtime") is not True
        or capabilities.get("intelligent_planner") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_proposals") is not True
    ):
        raise ReleaseLedgerError(
            "action_proposals_verified requires the reviewed proposal runtime prerequisites."
        )
    rollback = rollout.get("rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("action_proposals_kill_switch")
        != "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false"
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has no exact action-proposals rollback switch."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-proposal deployment change reference does not match."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-proposal deployment current_stage does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Action-proposal deployment does not bind this staging evidence."
        )
    if deployment.get("rollout_manifest_sha256") != file_sha256(
        rollout_manifest
    ):
        raise ReleaseLedgerError(
            "Action-proposal deployment does not bind this rollout manifest."
        )
    revision = deployment.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ReleaseLedgerError(
            "Action-proposal deployment source_revision must be a full lowercase Git SHA-1."
        )

    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "action_proposals_verified requires a clean post-deploy operator status."
        )
    if activation.get("schema_version") != 1:
        raise ReleaseLedgerError(
            "Action-proposal activation evidence has an unsupported schema."
        )
    if activation.get("status") != "action_proposals_verified":
        raise ReleaseLedgerError(
            "Action-proposal activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-proposal activation change reference does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-proposal activation current_stage does not match."
        )
    if activation.get("deployed_at") != deployment.get("deployed_at"):
        raise ReleaseLedgerError(
            "Action-proposal activation does not bind deployment time."
        )
    if activation.get("source_revision") != revision:
        raise ReleaseLedgerError(
            "Action-proposal activation does not bind the deployed source revision."
        )
    if (
        activation.get("operator_status_generated_at")
        != status.get("generated_at")
    ):
        raise ReleaseLedgerError(
            "Action-proposal activation does not bind operator-status generation time."
        )

    runtime = activation.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {
            "schema_version",
            "source_revision",
            "environment",
            "capabilities",
            "action_providers",
            "cohort",
        }
        or runtime.get("schema_version") != 1
    ):
        raise ReleaseLedgerError(
            "Action-proposal activation has no valid runtime proof."
        )
    runtime_capabilities = runtime.get("capabilities")
    if not isinstance(runtime_capabilities, dict):
        raise ReleaseLedgerError(
            "Action-proposal activation has no valid runtime capability proof."
        )
    runtime_capabilities = dict(runtime_capabilities)
    expected_capabilities = dict(capabilities)
    for optional in ("action_attachments", "action_reminders", "action_recipients", "action_document_sharing", "action_selection", "action_proposals"):
        runtime_capabilities.setdefault(optional, False)
        expected_capabilities.setdefault(optional, False)
    expected_providers = normalized_action_providers(rollout)
    if (
        runtime.get("source_revision") != revision
        or runtime.get("environment") != rollout.get("environment")
        or runtime.get("action_providers") != expected_providers
        or runtime_capabilities != expected_capabilities
        or runtime_capabilities.get("coworker") is not True
        or runtime_capabilities.get("agent_runtime") is not True
        or runtime_capabilities.get("intelligent_planner") is not True
        or runtime_capabilities.get("actions") is not True
        or runtime_capabilities.get("action_proposals") is not True
    ):
        raise ReleaseLedgerError(
            "Action-proposal activation does not prove the exact reviewed runtime."
        )
    cohort = runtime.get("cohort")
    members = cohort.get("configured_members") if isinstance(cohort, dict) else None
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or cohort.get("max_users") != rollout_cohort["max_users"]
        or not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        raise ReleaseLedgerError(
            "Action-proposal activation does not prove reviewed cohort enforcement."
        )
    runtime_hash = activation.get("runtime_manifest_sha256")
    expected_runtime_hash = hashlib.sha256(canonical(runtime)).hexdigest()
    if runtime_hash != expected_runtime_hash:
        raise ReleaseLedgerError(
            "Action-proposal activation runtime manifest hash does not match its runtime snapshot."
        )

    hashes = activation.get("artifact_sha256")
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "rollout_manifest": file_sha256(rollout_manifest),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(expected_bound)
    ):
        raise ReleaseLedgerError(
            "Action-proposal activation evidence has invalid artifact hashes."
        )
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Action-proposal activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the action-proposals event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "action_proposals_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(action_proposals_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == ACTION_PROPOSALS_SCHEMA_VERSION
        and item.get("event_type") == "action_proposals_verified"
        and item.get("artifact_sha256", {}).get(
            "action_proposals_activation"
        ) == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This action-proposal activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": ACTION_PROPOSALS_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "action_proposals_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "rollout_manifest": file_sha256(rollout_manifest),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "action_proposals_activation": activation_hash,
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



def append_action_attachments_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    staging_evidence: Path,
    rollout_manifest: Path,
    deployment_change: Path,
    operator_status: Path,
    action_attachments_activation: Path,
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
            "Action-attachments ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "action-attachment live staging evidence",
    )
    rollout = load_json_object(
        rollout_manifest,
        "reviewed action-attachment rollout manifest",
    )
    deployment = load_json_object(
        deployment_change,
        "action-attachment deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-action-attachment operator status",
    )
    activation = load_json_object(
        action_attachments_activation,
        "action-attachment activation evidence",
    )

    for label, value in (
        ("rollout manifest", rollout),
        ("deployment change", deployment),
        ("operator status", status),
        ("action-attachment activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    staged = staging.get("action_attachments")
    if (
        not isinstance(staged, dict)
        or staged.get("status") != "passed"
        or not isinstance(staged.get("evidence"), str)
        or not staged["evidence"].strip()
        or not isinstance(staged.get("verified_at"), str)
    ):
        raise ReleaseLedgerError(
            "action_attachments_verified requires passed timestamped action-attachment staging evidence."
        )

    if rollout.get("environment") != "production":
        raise ReleaseLedgerError(
            "action_attachments_verified requires a production rollout manifest."
        )
    incident = rollout.get("incident")
    if (
        not isinstance(incident, dict)
        or incident.get("change_reference") != change_reference
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout change reference does not match."
        )
    rollout_cohort = rollout.get("cohort")
    if (
        not isinstance(rollout_cohort, dict)
        or not isinstance(rollout_cohort.get("max_users"), int)
        or isinstance(rollout_cohort.get("max_users"), bool)
        or rollout_cohort["max_users"] < 1
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has an invalid cohort ceiling."
        )
    capabilities = rollout.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or any(not isinstance(value, bool) for value in capabilities.values())
        or capabilities.get("coworker") is not True
        or capabilities.get("artifact_services") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_attachments") is not True
    ):
        raise ReleaseLedgerError(
            "action_attachments_verified requires reviewed artifact/action prerequisites."
        )
    rollback = rollout.get("rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("action_attachments_kill_switch")
        != "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false"
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has no exact action-attachments rollback switch."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-attachment deployment change reference does not match."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-attachment deployment current_stage does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Action-attachment deployment does not bind this staging evidence."
        )
    if deployment.get("rollout_manifest_sha256") != file_sha256(
        rollout_manifest
    ):
        raise ReleaseLedgerError(
            "Action-attachment deployment does not bind this rollout manifest."
        )
    revision = deployment.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ReleaseLedgerError(
            "Action-attachment deployment source_revision must be a full lowercase Git SHA-1."
        )

    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "action_attachments_verified requires a clean post-deploy operator status."
        )
    if activation.get("schema_version") != 1:
        raise ReleaseLedgerError(
            "Action-attachment activation evidence has an unsupported schema."
        )
    if activation.get("status") != "action_attachments_verified":
        raise ReleaseLedgerError(
            "Action-attachment activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-attachment activation change reference does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-attachment activation current_stage does not match."
        )
    if activation.get("deployed_at") != deployment.get("deployed_at"):
        raise ReleaseLedgerError(
            "Action-attachment activation does not bind deployment time."
        )
    if activation.get("source_revision") != revision:
        raise ReleaseLedgerError(
            "Action-attachment activation does not bind the deployed source revision."
        )
    if (
        activation.get("operator_status_generated_at")
        != status.get("generated_at")
    ):
        raise ReleaseLedgerError(
            "Action-attachment activation does not bind operator-status generation time."
        )

    runtime = activation.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {
            "schema_version",
            "source_revision",
            "environment",
            "capabilities",
            "action_providers",
            "cohort",
        }
        or runtime.get("schema_version") != 1
    ):
        raise ReleaseLedgerError(
            "Action-attachment activation has no valid runtime proof."
        )
    runtime_capabilities = runtime.get("capabilities")
    if not isinstance(runtime_capabilities, dict):
        raise ReleaseLedgerError(
            "Action-attachment activation has no valid runtime capability proof."
        )
    runtime_capabilities = dict(runtime_capabilities)
    expected_capabilities = dict(capabilities)
    for optional in ("action_attachments", "action_reminders", "action_recipients", "action_document_sharing", "action_selection", "action_proposals"):
        runtime_capabilities.setdefault(optional, False)
        expected_capabilities.setdefault(optional, False)
    expected_providers = normalized_action_providers(rollout)
    if (
        runtime.get("source_revision") != revision
        or runtime.get("environment") != rollout.get("environment")
        or runtime.get("action_providers") != expected_providers
        or runtime_capabilities != expected_capabilities
        or runtime_capabilities.get("coworker") is not True
        or runtime_capabilities.get("artifact_services") is not True
        or runtime_capabilities.get("actions") is not True
        or runtime_capabilities.get("action_attachments") is not True
    ):
        raise ReleaseLedgerError(
            "Action-attachment activation does not prove the exact reviewed runtime."
        )
    cohort = runtime.get("cohort")
    members = cohort.get("configured_members") if isinstance(cohort, dict) else None
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or cohort.get("max_users") != rollout_cohort["max_users"]
        or not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        raise ReleaseLedgerError(
            "Action-attachment activation does not prove reviewed cohort enforcement."
        )
    runtime_hash = activation.get("runtime_manifest_sha256")
    expected_runtime_hash = hashlib.sha256(canonical(runtime)).hexdigest()
    if runtime_hash != expected_runtime_hash:
        raise ReleaseLedgerError(
            "Action-attachment activation runtime manifest hash does not match its runtime snapshot."
        )

    hashes = activation.get("artifact_sha256")
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "rollout_manifest": file_sha256(rollout_manifest),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(expected_bound)
    ):
        raise ReleaseLedgerError(
            "Action-attachment activation evidence has invalid artifact hashes."
        )
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Action-attachment activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the action-attachments event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "action_attachments_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(action_attachments_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == ACTION_ATTACHMENTS_SCHEMA_VERSION
        and item.get("event_type") == "action_attachments_verified"
        and item.get("artifact_sha256", {}).get(
            "action_attachments_activation"
        ) == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This action-attachment activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": ACTION_ATTACHMENTS_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "action_attachments_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "rollout_manifest": file_sha256(rollout_manifest),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "action_attachments_activation": activation_hash,
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



def append_action_reminders_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    staging_evidence: Path,
    rollout_manifest: Path,
    deployment_change: Path,
    operator_status: Path,
    action_reminders_activation: Path,
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
            "Action-reminders ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "action-reminder live staging evidence",
    )
    rollout = load_json_object(
        rollout_manifest,
        "reviewed action-reminder rollout manifest",
    )
    deployment = load_json_object(
        deployment_change,
        "action-reminder deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-action-reminder operator status",
    )
    activation = load_json_object(
        action_reminders_activation,
        "action-reminder activation evidence",
    )

    for label, value in (
        ("rollout manifest", rollout),
        ("deployment change", deployment),
        ("operator status", status),
        ("action-reminder activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    expected_providers = normalized_action_providers(rollout)
    for provider in expected_providers:
        staged = staging.get(f"action_reminders_{provider}")
        if (
            not isinstance(staged, dict)
            or staged.get("status") != "passed"
            or not isinstance(staged.get("evidence"), str)
            or not staged["evidence"].strip()
            or not isinstance(staged.get("verified_at"), str)
        ):
            raise ReleaseLedgerError(
                f"action_reminders_verified requires passed timestamped {provider} reminder staging evidence."
            )

    if rollout.get("environment") != "production":
        raise ReleaseLedgerError(
            "action_reminders_verified requires a production rollout manifest."
        )
    incident = rollout.get("incident")
    if (
        not isinstance(incident, dict)
        or incident.get("change_reference") != change_reference
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout change reference does not match."
        )
    rollout_cohort = rollout.get("cohort")
    if (
        not isinstance(rollout_cohort, dict)
        or not isinstance(rollout_cohort.get("max_users"), int)
        or isinstance(rollout_cohort.get("max_users"), bool)
        or rollout_cohort["max_users"] < 1
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has an invalid cohort ceiling."
        )
    capabilities = rollout.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or any(not isinstance(value, bool) for value in capabilities.values())
        or capabilities.get("coworker") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_reminders") is not True
    ):
        raise ReleaseLedgerError(
            "action_reminders_verified requires reviewed action prerequisites."
        )
    rollback = rollout.get("rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("action_reminders_kill_switch")
        != "SHUDDHO_ACTION_REMINDERS_ENABLED=false"
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has no exact action-reminders rollback switch."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-reminder deployment change reference does not match."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-reminder deployment current_stage does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Action-reminder deployment does not bind this staging evidence."
        )
    if deployment.get("rollout_manifest_sha256") != file_sha256(
        rollout_manifest
    ):
        raise ReleaseLedgerError(
            "Action-reminder deployment does not bind this rollout manifest."
        )
    revision = deployment.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ReleaseLedgerError(
            "Action-reminder deployment source_revision must be a full lowercase Git SHA-1."
        )

    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "action_reminders_verified requires a clean post-deploy operator status."
        )
    if activation.get("schema_version") != 1:
        raise ReleaseLedgerError(
            "Action-reminder activation evidence has an unsupported schema."
        )
    if activation.get("status") != "action_reminders_verified":
        raise ReleaseLedgerError(
            "Action-reminder activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-reminder activation change reference does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-reminder activation current_stage does not match."
        )
    if activation.get("deployed_at") != deployment.get("deployed_at"):
        raise ReleaseLedgerError(
            "Action-reminder activation does not bind deployment time."
        )
    if activation.get("source_revision") != revision:
        raise ReleaseLedgerError(
            "Action-reminder activation does not bind the deployed source revision."
        )
    if (
        activation.get("operator_status_generated_at")
        != status.get("generated_at")
    ):
        raise ReleaseLedgerError(
            "Action-reminder activation does not bind operator-status generation time."
        )

    runtime = activation.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {
            "schema_version",
            "source_revision",
            "environment",
            "capabilities",
            "action_providers",
            "cohort",
        }
        or runtime.get("schema_version") != 1
    ):
        raise ReleaseLedgerError(
            "Action-reminder activation has no valid runtime proof."
        )
    runtime_capabilities = runtime.get("capabilities")
    if not isinstance(runtime_capabilities, dict):
        raise ReleaseLedgerError(
            "Action-reminder activation has no valid runtime capability proof."
        )
    runtime_capabilities = dict(runtime_capabilities)
    expected_capabilities = dict(capabilities)
    for optional in ("action_attachments", "action_reminders", "action_recipients", "action_document_sharing", "action_selection", "action_proposals"):
        runtime_capabilities.setdefault(optional, False)
        expected_capabilities.setdefault(optional, False)
    if (
        runtime.get("source_revision") != revision
        or runtime.get("environment") != rollout.get("environment")
        or runtime.get("action_providers") != expected_providers
        or runtime_capabilities != expected_capabilities
        or runtime_capabilities.get("coworker") is not True
        or runtime_capabilities.get("actions") is not True
        or runtime_capabilities.get("action_reminders") is not True
    ):
        raise ReleaseLedgerError(
            "Action-reminder activation does not prove the exact reviewed runtime."
        )
    cohort = runtime.get("cohort")
    members = cohort.get("configured_members") if isinstance(cohort, dict) else None
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or cohort.get("max_users") != rollout_cohort["max_users"]
        or not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        raise ReleaseLedgerError(
            "Action-reminder activation does not prove reviewed cohort enforcement."
        )
    runtime_hash = activation.get("runtime_manifest_sha256")
    expected_runtime_hash = hashlib.sha256(canonical(runtime)).hexdigest()
    if runtime_hash != expected_runtime_hash:
        raise ReleaseLedgerError(
            "Action-reminder activation runtime manifest hash does not match its runtime snapshot."
        )

    hashes = activation.get("artifact_sha256")
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "rollout_manifest": file_sha256(rollout_manifest),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(expected_bound)
    ):
        raise ReleaseLedgerError(
            "Action-reminder activation evidence has invalid artifact hashes."
        )
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Action-reminder activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the action-reminders event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "action_reminders_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(action_reminders_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == ACTION_REMINDERS_SCHEMA_VERSION
        and item.get("event_type") == "action_reminders_verified"
        and item.get("artifact_sha256", {}).get(
            "action_reminders_activation"
        ) == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This action-reminder activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": ACTION_REMINDERS_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "action_reminders_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "rollout_manifest": file_sha256(rollout_manifest),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "action_reminders_activation": activation_hash,
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



def append_action_recipients_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    staging_evidence: Path,
    rollout_manifest: Path,
    deployment_change: Path,
    operator_status: Path,
    action_recipients_activation: Path,
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
            "Action-recipients ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "action-recipient live staging evidence",
    )
    rollout = load_json_object(
        rollout_manifest,
        "reviewed action-recipient rollout manifest",
    )
    deployment = load_json_object(
        deployment_change,
        "action-recipient deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-action-recipient operator status",
    )
    activation = load_json_object(
        action_recipients_activation,
        "action-recipient activation evidence",
    )

    for label, value in (
        ("rollout manifest", rollout),
        ("deployment change", deployment),
        ("operator status", status),
        ("action-recipient activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    staged = staging.get("action_recipients")
    if (
        not isinstance(staged, dict)
        or staged.get("status") != "passed"
        or not isinstance(staged.get("evidence"), str)
        or not staged["evidence"].strip()
        or not isinstance(staged.get("verified_at"), str)
    ):
        raise ReleaseLedgerError(
            "action_recipients_verified requires passed timestamped saved-recipient staging evidence."
        )


    if rollout.get("environment") != "production":
        raise ReleaseLedgerError(
            "action_recipients_verified requires a production rollout manifest."
        )
    incident = rollout.get("incident")
    if (
        not isinstance(incident, dict)
        or incident.get("change_reference") != change_reference
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout change reference does not match."
        )
    rollout_cohort = rollout.get("cohort")
    if (
        not isinstance(rollout_cohort, dict)
        or not isinstance(rollout_cohort.get("max_users"), int)
        or isinstance(rollout_cohort.get("max_users"), bool)
        or rollout_cohort["max_users"] < 1
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has an invalid cohort ceiling."
        )
    capabilities = rollout.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or any(not isinstance(value, bool) for value in capabilities.values())
        or capabilities.get("coworker") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_recipients") is not True
    ):
        raise ReleaseLedgerError(
            "action_recipients_verified requires reviewed action prerequisites."
        )
    rollback = rollout.get("rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("action_recipients_kill_switch")
        != "SHUDDHO_ACTION_RECIPIENTS_ENABLED=false"
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has no exact action-recipients rollback switch."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-recipient deployment change reference does not match."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-recipient deployment current_stage does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Action-recipient deployment does not bind this staging evidence."
        )
    if deployment.get("rollout_manifest_sha256") != file_sha256(
        rollout_manifest
    ):
        raise ReleaseLedgerError(
            "Action-recipient deployment does not bind this rollout manifest."
        )
    revision = deployment.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ReleaseLedgerError(
            "Action-recipient deployment source_revision must be a full lowercase Git SHA-1."
        )

    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "action_recipients_verified requires a clean post-deploy operator status."
        )
    if activation.get("schema_version") != 1:
        raise ReleaseLedgerError(
            "Action-recipient activation evidence has an unsupported schema."
        )
    if activation.get("status") != "action_recipients_verified":
        raise ReleaseLedgerError(
            "Action-recipient activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Action-recipient activation change reference does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Action-recipient activation current_stage does not match."
        )
    if activation.get("deployed_at") != deployment.get("deployed_at"):
        raise ReleaseLedgerError(
            "Action-recipient activation does not bind deployment time."
        )
    if activation.get("source_revision") != revision:
        raise ReleaseLedgerError(
            "Action-recipient activation does not bind the deployed source revision."
        )
    if (
        activation.get("operator_status_generated_at")
        != status.get("generated_at")
    ):
        raise ReleaseLedgerError(
            "Action-recipient activation does not bind operator-status generation time."
        )

    runtime = activation.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {
            "schema_version",
            "source_revision",
            "environment",
            "capabilities",
            "action_providers",
            "cohort",
        }
        or runtime.get("schema_version") != 1
    ):
        raise ReleaseLedgerError(
            "Action-recipient activation has no valid runtime proof."
        )
    runtime_capabilities = runtime.get("capabilities")
    if not isinstance(runtime_capabilities, dict):
        raise ReleaseLedgerError(
            "Action-recipient activation has no valid runtime capability proof."
        )
    runtime_capabilities = dict(runtime_capabilities)
    expected_capabilities = dict(capabilities)
    expected_providers = normalized_action_providers(rollout)
    for optional in ("action_attachments", "action_reminders", "action_recipients", "action_document_sharing", "action_selection", "action_proposals"):
        runtime_capabilities.setdefault(optional, False)
        expected_capabilities.setdefault(optional, False)
    if (
        runtime.get("source_revision") != revision
        or runtime.get("environment") != rollout.get("environment")
        or runtime.get("action_providers") != expected_providers
        or runtime_capabilities != expected_capabilities
        or runtime_capabilities.get("coworker") is not True
        or runtime_capabilities.get("actions") is not True
        or runtime_capabilities.get("action_recipients") is not True
    ):
        raise ReleaseLedgerError(
            "Action-recipient activation does not prove the exact reviewed runtime."
        )
    cohort = runtime.get("cohort")
    members = cohort.get("configured_members") if isinstance(cohort, dict) else None
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or cohort.get("max_users") != rollout_cohort["max_users"]
        or not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        raise ReleaseLedgerError(
            "Action-recipient activation does not prove reviewed cohort enforcement."
        )
    runtime_hash = activation.get("runtime_manifest_sha256")
    expected_runtime_hash = hashlib.sha256(canonical(runtime)).hexdigest()
    if runtime_hash != expected_runtime_hash:
        raise ReleaseLedgerError(
            "Action-recipient activation runtime manifest hash does not match its runtime snapshot."
        )

    hashes = activation.get("artifact_sha256")
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "rollout_manifest": file_sha256(rollout_manifest),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(expected_bound)
    ):
        raise ReleaseLedgerError(
            "Action-recipient activation evidence has invalid artifact hashes."
        )
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Action-recipient activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the action-recipients event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "action_recipients_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(action_recipients_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == ACTION_RECIPIENTS_SCHEMA_VERSION
        and item.get("event_type") == "action_recipients_verified"
        and item.get("artifact_sha256", {}).get(
            "action_recipients_activation"
        ) == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This action-recipient activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": ACTION_RECIPIENTS_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "action_recipients_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "rollout_manifest": file_sha256(rollout_manifest),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "action_recipients_activation": activation_hash,
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



def append_action_document_sharing_event(
    *,
    ledger: Path,
    key: bytes,
    release_id: str,
    actor_reference: str,
    change_reference: str,
    current_stage: str,
    staging_evidence: Path,
    rollout_manifest: Path,
    deployment_change: Path,
    operator_status: Path,
    action_document_sharing_activation: Path,
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
            "Document-sharing ledger event requires a valid current_stage."
        )

    staging = load_json_object(
        staging_evidence,
        "document-sharing live staging evidence",
    )
    rollout = load_json_object(
        rollout_manifest,
        "reviewed document-sharing rollout manifest",
    )
    deployment = load_json_object(
        deployment_change,
        "document-sharing deployment change",
    )
    status = load_json_object(
        operator_status,
        "post-document-sharing operator status",
    )
    activation = load_json_object(
        action_document_sharing_activation,
        "document-sharing activation evidence",
    )

    for label, value in (
        ("rollout manifest", rollout),
        ("deployment change", deployment),
        ("operator status", status),
        ("document-sharing activation evidence", activation),
    ):
        if value.get("release_id") != release_id:
            raise ReleaseLedgerError(
                f"{label} release_id does not match {release_id!r}."
            )

    staged = staging.get("action_document_sharing")
    if (
        not isinstance(staged, dict)
        or staged.get("status") != "passed"
        or not isinstance(staged.get("evidence"), str)
        or not staged["evidence"].strip()
        or not isinstance(staged.get("verified_at"), str)
    ):
        raise ReleaseLedgerError(
            "action_document_sharing_verified requires passed timestamped document-sharing staging evidence."
        )


    if rollout.get("environment") != "production":
        raise ReleaseLedgerError(
            "action_document_sharing_verified requires a production rollout manifest."
        )
    incident = rollout.get("incident")
    if (
        not isinstance(incident, dict)
        or incident.get("change_reference") != change_reference
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout change reference does not match."
        )
    rollout_cohort = rollout.get("cohort")
    if (
        not isinstance(rollout_cohort, dict)
        or not isinstance(rollout_cohort.get("max_users"), int)
        or isinstance(rollout_cohort.get("max_users"), bool)
        or rollout_cohort["max_users"] < 1
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has an invalid cohort ceiling."
        )
    capabilities = rollout.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or any(not isinstance(value, bool) for value in capabilities.values())
        or capabilities.get("coworker") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("artifact_services") is not True
        or capabilities.get("action_document_sharing") is not True
    ):
        raise ReleaseLedgerError(
            "action_document_sharing_verified requires reviewed action prerequisites."
        )
    rollback = rollout.get("rollback")
    if (
        not isinstance(rollback, dict)
        or rollback.get("action_document_sharing_kill_switch")
        != "SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false"
    ):
        raise ReleaseLedgerError(
            "Reviewed rollout has no exact document-sharing rollback switch."
        )

    if deployment.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Document-sharing deployment change reference does not match."
        )
    if deployment.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Document-sharing deployment current_stage does not match."
        )
    if deployment.get("staging_evidence_sha256") != file_sha256(
        staging_evidence
    ):
        raise ReleaseLedgerError(
            "Document-sharing deployment does not bind this staging evidence."
        )
    if deployment.get("rollout_manifest_sha256") != file_sha256(
        rollout_manifest
    ):
        raise ReleaseLedgerError(
            "Document-sharing deployment does not bind this rollout manifest."
        )
    revision = deployment.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ReleaseLedgerError(
            "Document-sharing deployment source_revision must be a full lowercase Git SHA-1."
        )

    if (
        status.get("decision") != "CONTINUE_COHORT"
        or status.get("breaches") != []
    ):
        raise ReleaseLedgerError(
            "action_document_sharing_verified requires a clean post-deploy operator status."
        )
    if activation.get("schema_version") != 1:
        raise ReleaseLedgerError(
            "Document-sharing activation evidence has an unsupported schema."
        )
    if activation.get("status") != "action_document_sharing_verified":
        raise ReleaseLedgerError(
            "Document-sharing activation evidence has not passed."
        )
    if activation.get("change_reference") != change_reference:
        raise ReleaseLedgerError(
            "Document-sharing activation change reference does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise ReleaseLedgerError(
            "Document-sharing activation current_stage does not match."
        )
    if activation.get("deployed_at") != deployment.get("deployed_at"):
        raise ReleaseLedgerError(
            "Document-sharing activation does not bind deployment time."
        )
    if activation.get("source_revision") != revision:
        raise ReleaseLedgerError(
            "Document-sharing activation does not bind the deployed source revision."
        )
    if (
        activation.get("operator_status_generated_at")
        != status.get("generated_at")
    ):
        raise ReleaseLedgerError(
            "Document-sharing activation does not bind operator-status generation time."
        )

    runtime = activation.get("runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {
            "schema_version",
            "source_revision",
            "environment",
            "capabilities",
            "action_providers",
            "cohort",
        }
        or runtime.get("schema_version") != 1
    ):
        raise ReleaseLedgerError(
            "Document-sharing activation has no valid runtime proof."
        )
    runtime_capabilities = runtime.get("capabilities")
    if not isinstance(runtime_capabilities, dict):
        raise ReleaseLedgerError(
            "Document-sharing activation has no valid runtime capability proof."
        )
    runtime_capabilities = dict(runtime_capabilities)
    expected_capabilities = dict(capabilities)
    expected_providers = normalized_action_providers(rollout)
    for optional in ("action_attachments", "action_reminders", "action_recipients", "action_document_sharing", "action_selection", "action_proposals"):
        runtime_capabilities.setdefault(optional, False)
        expected_capabilities.setdefault(optional, False)
    if (
        runtime.get("source_revision") != revision
        or runtime.get("environment") != rollout.get("environment")
        or runtime.get("action_providers") != expected_providers
        or runtime_capabilities != expected_capabilities
        or runtime_capabilities.get("coworker") is not True
        or runtime_capabilities.get("actions") is not True
        or runtime_capabilities.get("artifact_services") is not True
        or runtime_capabilities.get("action_document_sharing") is not True
    ):
        raise ReleaseLedgerError(
            "Document-sharing activation does not prove the exact reviewed runtime."
        )
    cohort = runtime.get("cohort")
    members = cohort.get("configured_members") if isinstance(cohort, dict) else None
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or cohort.get("max_users") != rollout_cohort["max_users"]
        or not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        raise ReleaseLedgerError(
            "Document-sharing activation does not prove reviewed cohort enforcement."
        )
    runtime_hash = activation.get("runtime_manifest_sha256")
    expected_runtime_hash = hashlib.sha256(canonical(runtime)).hexdigest()
    if runtime_hash != expected_runtime_hash:
        raise ReleaseLedgerError(
            "Document-sharing activation runtime manifest hash does not match its runtime snapshot."
        )

    hashes = activation.get("artifact_sha256")
    expected_bound = {
        "staging_evidence": file_sha256(staging_evidence),
        "rollout_manifest": file_sha256(rollout_manifest),
        "deployment_change": file_sha256(deployment_change),
        "operator_status": file_sha256(operator_status),
    }
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(expected_bound)
    ):
        raise ReleaseLedgerError(
            "Document-sharing activation evidence has invalid artifact hashes."
        )
    for name, value in expected_bound.items():
        if hashes.get(name) != value:
            raise ReleaseLedgerError(
                f"Document-sharing activation does not bind this {name}."
            )

    entries = read_entries(ledger)
    state = verify_entries(entries, key)
    if (
        state["release_id"] is not None
        and state["release_id"] != release_id
    ):
        raise ReleaseLedgerError(
            "Ledger release_id does not match the document-sharing event."
        )
    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseLedgerError(
            "action_document_sharing_verified requires an existing ledger chain that reached current_stage."
        )

    activation_hash = file_sha256(action_document_sharing_activation)
    duplicates = [
        item
        for item in entries
        if item.get("schema_version") == ACTION_DOCUMENT_SHARING_SCHEMA_VERSION
        and item.get("event_type") == "action_document_sharing_verified"
        and item.get("artifact_sha256", {}).get(
            "action_document_sharing_activation"
        ) == activation_hash
    ]
    if duplicates:
        raise ReleaseLedgerError(
            "This document-sharing activation is already recorded in the release ledger."
        )

    core = {
        "schema_version": ACTION_DOCUMENT_SHARING_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "created_at": created_at or utc_timestamp(),
        "release_id": release_id,
        "event_type": "action_document_sharing_verified",
        "actor_reference": actor_reference,
        "change_reference": change_reference,
        "current_stage": current_stage,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": file_sha256(staging_evidence),
            "rollout_manifest": file_sha256(rollout_manifest),
            "deployment_change": file_sha256(deployment_change),
            "operator_status": file_sha256(operator_status),
            "action_document_sharing_activation": activation_hash,
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

    action_selection_parser = sub.add_parser("append-action-selection")
    action_selection_parser.add_argument("--ledger", type=Path, required=True)
    action_selection_parser.add_argument("--release-id", required=True)
    action_selection_parser.add_argument("--actor-reference", required=True)
    action_selection_parser.add_argument("--change-reference", required=True)
    action_selection_parser.add_argument("--current-stage", required=True)
    action_selection_parser.add_argument("--staging-evidence", type=Path, required=True)
    action_selection_parser.add_argument("--deployment-change", type=Path, required=True)
    action_selection_parser.add_argument("--operator-status", type=Path, required=True)
    action_selection_parser.add_argument(
        "--action-selection-activation",
        type=Path,
        required=True,
    )

    action_proposals_parser = sub.add_parser("append-action-proposals")
    action_proposals_parser.add_argument("--ledger", type=Path, required=True)
    action_proposals_parser.add_argument("--release-id", required=True)
    action_proposals_parser.add_argument("--actor-reference", required=True)
    action_proposals_parser.add_argument("--change-reference", required=True)
    action_proposals_parser.add_argument("--current-stage", required=True)
    action_proposals_parser.add_argument("--staging-evidence", type=Path, required=True)
    action_proposals_parser.add_argument("--rollout", type=Path, required=True)
    action_proposals_parser.add_argument("--deployment-change", type=Path, required=True)
    action_proposals_parser.add_argument("--operator-status", type=Path, required=True)
    action_proposals_parser.add_argument(
        "--action-proposals-activation",
        type=Path,
        required=True,
    )

    action_attachments_parser = sub.add_parser("append-action-attachments")
    action_attachments_parser.add_argument("--ledger", type=Path, required=True)
    action_attachments_parser.add_argument("--release-id", required=True)
    action_attachments_parser.add_argument("--actor-reference", required=True)
    action_attachments_parser.add_argument("--change-reference", required=True)
    action_attachments_parser.add_argument("--current-stage", required=True)
    action_attachments_parser.add_argument("--staging-evidence", type=Path, required=True)
    action_attachments_parser.add_argument("--rollout", type=Path, required=True)
    action_attachments_parser.add_argument("--deployment-change", type=Path, required=True)
    action_attachments_parser.add_argument("--operator-status", type=Path, required=True)
    action_attachments_parser.add_argument(
        "--action-attachments-activation",
        type=Path,
        required=True,
    )

    action_reminders_parser = sub.add_parser("append-action-reminders")
    action_reminders_parser.add_argument("--ledger", type=Path, required=True)
    action_reminders_parser.add_argument("--release-id", required=True)
    action_reminders_parser.add_argument("--actor-reference", required=True)
    action_reminders_parser.add_argument("--change-reference", required=True)
    action_reminders_parser.add_argument("--current-stage", required=True)
    action_reminders_parser.add_argument("--staging-evidence", type=Path, required=True)
    action_reminders_parser.add_argument("--rollout", type=Path, required=True)
    action_reminders_parser.add_argument("--deployment-change", type=Path, required=True)
    action_reminders_parser.add_argument("--operator-status", type=Path, required=True)
    action_reminders_parser.add_argument(
        "--action-reminders-activation",
        type=Path,
        required=True,
    )

    action_recipients_parser = sub.add_parser("append-action-recipients")
    action_recipients_parser.add_argument("--ledger", type=Path, required=True)
    action_recipients_parser.add_argument("--release-id", required=True)
    action_recipients_parser.add_argument("--actor-reference", required=True)
    action_recipients_parser.add_argument("--change-reference", required=True)
    action_recipients_parser.add_argument("--current-stage", required=True)
    action_recipients_parser.add_argument("--staging-evidence", type=Path, required=True)
    action_recipients_parser.add_argument("--rollout", type=Path, required=True)
    action_recipients_parser.add_argument("--deployment-change", type=Path, required=True)
    action_recipients_parser.add_argument("--operator-status", type=Path, required=True)
    action_recipients_parser.add_argument(
        "--action-recipients-activation",
        type=Path,
        required=True,
    )

    action_document_sharing_parser = sub.add_parser("append-action-document-sharing")
    action_document_sharing_parser.add_argument("--ledger", type=Path, required=True)
    action_document_sharing_parser.add_argument("--release-id", required=True)
    action_document_sharing_parser.add_argument("--actor-reference", required=True)
    action_document_sharing_parser.add_argument("--change-reference", required=True)
    action_document_sharing_parser.add_argument("--current-stage", required=True)
    action_document_sharing_parser.add_argument("--staging-evidence", type=Path, required=True)
    action_document_sharing_parser.add_argument("--rollout", type=Path, required=True)
    action_document_sharing_parser.add_argument("--deployment-change", type=Path, required=True)
    action_document_sharing_parser.add_argument("--operator-status", type=Path, required=True)
    action_document_sharing_parser.add_argument(
        "--action-document-sharing-activation",
        type=Path,
        required=True,
    )

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
        elif args.command == "append-action-selection":
            entry = append_action_selection_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                action_selection_activation=args.action_selection_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-action-proposals":
            entry = append_action_proposals_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                rollout_manifest=args.rollout,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                action_proposals_activation=args.action_proposals_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-action-attachments":
            entry = append_action_attachments_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                rollout_manifest=args.rollout,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                action_attachments_activation=args.action_attachments_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-action-reminders":
            entry = append_action_reminders_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                rollout_manifest=args.rollout,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                action_reminders_activation=args.action_reminders_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-action-recipients":
            entry = append_action_recipients_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                rollout_manifest=args.rollout,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                action_recipients_activation=args.action_recipients_activation,
            )
            result = {
                "appended": True,
                "sequence": entry["sequence"],
                "release_id": entry["release_id"],
                "event_type": entry["event_type"],
                "head_entry_hash": entry["entry_hash"],
            }
        elif args.command == "append-action-document-sharing":
            entry = append_action_document_sharing_event(
                ledger=args.ledger,
                key=key,
                release_id=args.release_id,
                actor_reference=args.actor_reference,
                change_reference=args.change_reference,
                current_stage=args.current_stage,
                staging_evidence=args.staging_evidence,
                rollout_manifest=args.rollout,
                deployment_change=args.deployment_change,
                operator_status=args.operator_status,
                action_document_sharing_activation=args.action_document_sharing_activation,
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
