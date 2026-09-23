from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.cohort_release_ledger import (
    file_sha256 as ledger_file_sha256,
    ledger_key,
    read_entries,
    require_exact_attested_event,
    verified_release_entries,
    verify_entries,
)
from scripts.staging_api_exercise import env_secret, require_https_base
from scripts.staging_cohort_admission import assert_denied_unprovisioned, token_account_id
from services.coworker.config import Settings


class ScaleActivationError(RuntimeError):
    pass


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ScaleActivationError(f"{label} must be an ISO-8601 timestamp.") from None
    if result.tzinfo is None:
        raise ScaleActivationError(f"{label} must include a timezone.")
    return result.astimezone(timezone.utc)


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScaleActivationError(f"Could not read {label}: {type(error).__name__}") from None
    if not isinstance(value, dict):
        raise ScaleActivationError(f"{label} must contain a JSON object.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_scale_decision(value: dict) -> datetime:
    if value.get("decision") != "ELIGIBLE_FOR_BOUNDED_EXPANSION":
        raise ScaleActivationError("Scale decision is not eligible for bounded expansion.")
    for key in ("release_id", "current_stage", "proposed_stage"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ScaleActivationError(f"Scale decision {key} is required.")
    current_users = value.get("current_max_users")
    proposed_users = value.get("proposed_max_users")
    if not isinstance(current_users, int) or isinstance(current_users, bool) or current_users < 1:
        raise ScaleActivationError("Scale decision current_max_users must be a positive integer.")
    if not isinstance(proposed_users, int) or isinstance(proposed_users, bool) or proposed_users <= current_users:
        raise ScaleActivationError("Scale decision proposed_max_users must exceed current_max_users.")
    if value.get("failures") != []:
        raise ScaleActivationError("Scale decision contains review failures.")
    references = value.get("references")
    if not isinstance(references, dict):
        raise ScaleActivationError("Scale decision is missing references.")
    change_reference = references.get("change_reference")
    if not isinstance(change_reference, str) or not change_reference.strip():
        raise ScaleActivationError("Scale decision is missing change_reference.")
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ScaleActivationError("Scale decision has no generated_at timestamp.")
    return parse_time(generated_at, "scale decision generated_at")


def validate_deployment_change(value: dict, decision: dict, *, not_before: datetime) -> datetime:
    required = {
        "release_id",
        "change_reference",
        "deployed_at",
        "stage",
        "max_users",
    }
    if set(value) != required:
        raise ScaleActivationError("Deployment change has an unexpected schema.")
    if value["release_id"] != decision["release_id"]:
        raise ScaleActivationError("Deployment change release_id does not match.")
    if value["change_reference"] != decision["references"]["change_reference"]:
        raise ScaleActivationError("Deployment change reference does not match the reviewed change.")
    if value["stage"] != decision["proposed_stage"]:
        raise ScaleActivationError("Deployment stage does not match the reviewed proposed stage.")
    if value["max_users"] != decision["proposed_max_users"]:
        raise ScaleActivationError("Deployment max_users does not match the reviewed cohort ceiling.")
    deployed_at = parse_time(str(value["deployed_at"]), "deployment deployed_at")
    if deployed_at < not_before:
        raise ScaleActivationError("Deployment change predates the scale-review decision.")
    return deployed_at


def validate_operator_status(
    value: dict,
    decision: dict,
    *,
    not_before: datetime,
    freshness_minutes: int,
    now: datetime,
) -> datetime:
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError("Operator status release_id does not match.")
    if value.get("decision") != "CONTINUE_COHORT" or value.get("breaches") != []:
        raise ScaleActivationError("Operator status must be CONTINUE_COHORT with zero breaches.")
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ScaleActivationError("Operator status has no generated_at timestamp.")
    generated = parse_time(generated_at, "operator status generated_at")
    if generated < not_before:
        raise ScaleActivationError("Operator status must be generated after the deployment change.")
    age_minutes = (now - generated).total_seconds() / 60
    if age_minutes < -1:
        raise ScaleActivationError("Operator status is from the future.")
    if age_minutes > freshness_minutes:
        raise ScaleActivationError(f"Operator status is stale ({age_minutes:.1f} minutes old).")
    return generated



def validate_provider_policy_activation(
    path: Path,
    ledger_path: Path,
    decision: dict,
) -> dict:
    value = load_json(path, "provider policy activation")
    if value.get("status") != "provider_policy_verified":
        raise ScaleActivationError(
            "Provider policy activation has not been verified."
        )
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Provider policy activation release_id does not match."
        )
    if (
        value.get("current_stage") != decision["current_stage"]
        or value.get("proposed_stage") != decision["proposed_stage"]
    ):
        raise ScaleActivationError(
            "Provider policy activation stages do not match the scale decision."
        )

    try:
        entries = read_entries(ledger_path)
        state = verify_entries(entries, ledger_key())
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None
    if state.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Release ledger release_id does not match the scale decision."
        )

    activation_hash = ledger_file_sha256(path)
    matches = [
        item
        for item in entries
        if item.get("schema_version") == 5
        and item.get("event_type") == "provider_policy_verified"
        and item.get("current_stage") == decision["current_stage"]
        and item.get("next_stage") == decision["proposed_stage"]
        and item.get("artifact_sha256", {}).get("policy_activation")
        == activation_hash
    ]
    if len(matches) != 1:
        raise ScaleActivationError(
            "Release ledger must contain exactly one matching provider_policy_verified event."
        )
    return value



def validate_microsoft_rollout_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not settings.microsoft_actions_enabled:
        return None
    if path is None:
        raise ScaleActivationError(
            "Microsoft actions are enabled but --microsoft-rollout-activation is required."
        )

    value = load_json(path, "Microsoft rollout activation")
    if value.get("status") != "microsoft_rollout_verified":
        raise ScaleActivationError(
            "Microsoft rollout activation has not been verified."
        )
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Microsoft rollout activation release_id does not match."
        )
    backend = value.get("backend")
    frontend = value.get("frontend")
    if (
        not isinstance(backend, dict)
        or backend.get("actions_enabled") is not True
        or backend.get("microsoft_actions_enabled") is not True
        or not isinstance(frontend, dict)
        or frontend.get("coworker_enabled") is not True
        or frontend.get("microsoft_actions_enabled") is not True
    ):
        raise ScaleActivationError(
            "Microsoft rollout activation does not prove enabled backend/frontend controls."
        )

    try:
        entries = read_entries(ledger_path)
        state = verify_entries(entries, ledger_key())
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None
    if state.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Release ledger release_id does not match the scale decision."
        )

    activation_hash = ledger_file_sha256(path)
    matches = [
        item
        for item in entries
        if item.get("schema_version") == 6
        and item.get("event_type") == "microsoft_rollout_verified"
        and item.get("current_stage") == decision["current_stage"]
        and item.get("next_stage") is None
        and item.get("artifact_sha256", {}).get("rollout_activation")
        == activation_hash
    ]
    if len(matches) != 1:
        raise ScaleActivationError(
            "Microsoft-enabled expansion requires exactly one matching "
            "schema-v6 microsoft_rollout_verified ledger event."
        )
    return value




def validate_action_selection_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not getattr(settings, "agent_action_selection_enabled", False):
        return None
    if path is None:
        raise ScaleActivationError(
            "Agent action selection is enabled but "
            "--action-selection-activation is required."
        )

    value = load_json(path, "action selection activation")
    if value.get("status") != "action_selection_verified":
        raise ScaleActivationError(
            "Action selection activation has not been verified."
        )
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Action selection activation release_id does not match."
        )
    if value.get("current_stage") != decision["current_stage"]:
        raise ScaleActivationError(
            "Action selection activation current_stage does not match."
        )
    runtime = value.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("coworker_enabled") is not True
        or runtime.get("agent_runtime_enabled") is not True
        or runtime.get("intelligent_planner_enabled") is not True
        or runtime.get("actions_enabled") is not True
        or runtime.get("action_selection_enabled") is not True
        or runtime.get("cohort_enforced") is not True
    ):
        raise ScaleActivationError(
            "Action selection activation does not prove required runtime controls."
        )

    try:
        entries, _ = verified_release_entries(
            ledger_path,
            decision["release_id"],
        )
        entry = require_exact_attested_event(
            entries,
            schema_version=7,
            event_type="action_selection_verified",
            current_stage=decision["current_stage"],
            next_stage=None,
            artifact_key="action_selection_activation",
            artifact_sha256=ledger_file_sha256(path),
            label="Action-selection scale attestation",
        )
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None

    return {
        "activation": value,
        "ledger_sequence": entry["sequence"],
        "ledger_entry_hash": entry["entry_hash"],
        "activation_sha256": ledger_file_sha256(path),
    }


def validate_action_proposals_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not getattr(settings, "agent_action_proposals_enabled", False):
        return None
    if path is None:
        raise ScaleActivationError(
            "Agent action proposals are enabled but "
            "--action-proposals-activation is required."
        )

    value = load_json(path, "action proposals activation")
    if value.get("status") != "action_proposals_verified":
        raise ScaleActivationError(
            "Action proposals activation has not been verified."
        )
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Action proposals activation release_id does not match."
        )
    if value.get("current_stage") != decision["current_stage"]:
        raise ScaleActivationError(
            "Action proposals activation current_stage does not match."
        )
    runtime = value.get("runtime")
    capabilities = runtime.get("capabilities") if isinstance(runtime, dict) else None
    cohort = runtime.get("cohort") if isinstance(runtime, dict) else None
    if (
        not isinstance(runtime, dict)
        or not isinstance(capabilities, dict)
        or capabilities.get("coworker") is not True
        or capabilities.get("agent_runtime") is not True
        or capabilities.get("intelligent_planner") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_proposals") is not True
        or not isinstance(cohort, dict)
        or cohort.get("enforced") is not True
    ):
        raise ScaleActivationError(
            "Action proposals activation does not prove required runtime controls."
        )

    try:
        entries, _ = verified_release_entries(
            ledger_path,
            decision["release_id"],
        )
        entry = require_exact_attested_event(
            entries,
            schema_version=8,
            event_type="action_proposals_verified",
            current_stage=decision["current_stage"],
            next_stage=None,
            artifact_key="action_proposals_activation",
            artifact_sha256=ledger_file_sha256(path),
            label="Action-proposals scale attestation",
        )
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None

    return {
        "activation": value,
        "ledger_sequence": entry["sequence"],
        "ledger_entry_hash": entry["entry_hash"],
        "activation_sha256": ledger_file_sha256(path),
    }


def validate_action_attachments_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not getattr(settings, "action_attachments_enabled", False):
        return None
    if path is None:
        raise ScaleActivationError(
            "Approved action attachments are enabled but "
            "--action-attachments-activation is required."
        )

    value = load_json(path, "action attachments activation")
    if value.get("status") != "action_attachments_verified":
        raise ScaleActivationError(
            "Action attachments activation has not been verified."
        )
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError(
            "Action attachments activation release_id does not match."
        )
    if value.get("current_stage") != decision["current_stage"]:
        raise ScaleActivationError(
            "Action attachments activation current_stage does not match."
        )
    runtime = value.get("runtime")
    capabilities = runtime.get("capabilities") if isinstance(runtime, dict) else None
    cohort = runtime.get("cohort") if isinstance(runtime, dict) else None
    if (
        not isinstance(runtime, dict)
        or not isinstance(capabilities, dict)
        or capabilities.get("coworker") is not True
        or capabilities.get("artifact_services") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_attachments") is not True
        or not isinstance(cohort, dict)
        or cohort.get("enforced") is not True
    ):
        raise ScaleActivationError(
            "Action attachments activation does not prove required runtime controls."
        )

    try:
        entries, _ = verified_release_entries(
            ledger_path,
            decision["release_id"],
        )
        entry = require_exact_attested_event(
            entries,
            schema_version=9,
            event_type="action_attachments_verified",
            current_stage=decision["current_stage"],
            next_stage=None,
            artifact_key="action_attachments_activation",
            artifact_sha256=ledger_file_sha256(path),
            label="Action-attachments scale attestation",
        )
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None

    return {
        "activation": value,
        "ledger_sequence": entry["sequence"],
        "ledger_entry_hash": entry["entry_hash"],
        "activation_sha256": ledger_file_sha256(path),
    }


def validate_action_reminders_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not getattr(settings, "action_reminders_enabled", False):
        return None
    if path is None:
        raise ScaleActivationError(
            "Approved calendar reminders are enabled but "
            "--action-reminders-activation is required."
        )
    value = load_json(path, "action reminders activation")
    if value.get("status") != "action_reminders_verified":
        raise ScaleActivationError("Action reminders activation has not been verified.")
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError("Action reminders activation release_id does not match.")
    if value.get("current_stage") != decision["current_stage"]:
        raise ScaleActivationError("Action reminders activation current_stage does not match.")
    runtime = value.get("runtime")
    capabilities = runtime.get("capabilities") if isinstance(runtime, dict) else None
    cohort = runtime.get("cohort") if isinstance(runtime, dict) else None
    if (
        not isinstance(runtime, dict)
        or not isinstance(capabilities, dict)
        or capabilities.get("coworker") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_reminders") is not True
        or not isinstance(cohort, dict)
        or cohort.get("enforced") is not True
    ):
        raise ScaleActivationError(
            "Action reminders activation does not prove required runtime controls."
        )
    try:
        entries, _ = verified_release_entries(ledger_path, decision["release_id"])
        entry = require_exact_attested_event(
            entries,
            schema_version=10,
            event_type="action_reminders_verified",
            current_stage=decision["current_stage"],
            next_stage=None,
            artifact_key="action_reminders_activation",
            artifact_sha256=ledger_file_sha256(path),
            label="Action-reminders scale attestation",
        )
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None
    return {
        "activation": value,
        "ledger_sequence": entry["sequence"],
        "ledger_entry_hash": entry["entry_hash"],
        "activation_sha256": ledger_file_sha256(path),
    }


def validate_action_recipients_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not getattr(settings, "action_recipients_enabled", False):
        return None
    if path is None:
        raise ScaleActivationError(
            "Saved action recipients are enabled but --action-recipients-activation is required."
        )
    value = load_json(path, "action recipients activation")
    if value.get("status") != "action_recipients_verified":
        raise ScaleActivationError("Action recipients activation has not been verified.")
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError("Action recipients activation release_id does not match.")
    if value.get("current_stage") != decision["current_stage"]:
        raise ScaleActivationError("Action recipients activation current_stage does not match.")
    runtime = value.get("runtime")
    capabilities = runtime.get("capabilities") if isinstance(runtime, dict) else None
    cohort = runtime.get("cohort") if isinstance(runtime, dict) else None
    if (
        not isinstance(runtime, dict)
        or not isinstance(capabilities, dict)
        or capabilities.get("coworker") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_recipients") is not True
        or not isinstance(cohort, dict)
        or cohort.get("enforced") is not True
    ):
        raise ScaleActivationError(
            "Action recipients activation does not prove required runtime controls."
        )
    try:
        entries, _ = verified_release_entries(ledger_path, decision["release_id"])
        entry = require_exact_attested_event(
            entries,
            schema_version=11,
            event_type="action_recipients_verified",
            current_stage=decision["current_stage"],
            next_stage=None,
            artifact_key="action_recipients_activation",
            artifact_sha256=ledger_file_sha256(path),
            label="Action-recipients scale attestation",
        )
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None
    return {
        "activation": value,
        "ledger_sequence": entry["sequence"],
        "ledger_entry_hash": entry["entry_hash"],
        "activation_sha256": ledger_file_sha256(path),
    }



def validate_action_document_sharing_activation(
    path: Path | None,
    ledger_path: Path,
    decision: dict,
    settings: Settings,
) -> dict | None:
    if not getattr(settings, "action_document_sharing_enabled", False):
        return None
    if path is None:
        raise ScaleActivationError(
            "Saved document sharing are enabled but --document-sharing-activation is required."
        )
    value = load_json(path, "document sharing activation")
    if value.get("status") != "action_document_sharing_verified":
        raise ScaleActivationError("Document sharing activation has not been verified.")
    if value.get("release_id") != decision["release_id"]:
        raise ScaleActivationError("Document sharing activation release_id does not match.")
    if value.get("current_stage") != decision["current_stage"]:
        raise ScaleActivationError("Document sharing activation current_stage does not match.")
    runtime = value.get("runtime")
    capabilities = runtime.get("capabilities") if isinstance(runtime, dict) else None
    cohort = runtime.get("cohort") if isinstance(runtime, dict) else None
    if (
        not isinstance(runtime, dict)
        or not isinstance(capabilities, dict)
        or capabilities.get("coworker") is not True
        or capabilities.get("actions") is not True
        or capabilities.get("action_recipients") is not True
        or not isinstance(cohort, dict)
        or cohort.get("enforced") is not True
    ):
        raise ScaleActivationError(
            "Document sharing activation does not prove required runtime controls."
        )
    try:
        entries, _ = verified_release_entries(ledger_path, decision["release_id"])
        entry = require_exact_attested_event(
            entries,
            schema_version=12,
            event_type="action_document_sharing_verified",
            current_stage=decision["current_stage"],
            next_stage=None,
            artifact_key="action_document_sharing_activation",
            artifact_sha256=ledger_file_sha256(path),
            label="Document-sharing scale attestation",
        )
    except Exception as error:
        raise ScaleActivationError(
            f"Release ledger verification failed: {error}"
        ) from None
    return {
        "activation": value,
        "ledger_sequence": entry["sequence"],
        "ledger_entry_hash": entry["entry_hash"],
        "activation_sha256": ledger_file_sha256(path),
    }


def require_deployed_configuration(settings: Settings, decision: dict, allowed_id: str, denied_id: str) -> None:
    if not settings.cohort_enforced:
        raise ScaleActivationError("SHUDDHO_COWORKER_COHORT_ENFORCED must remain true.")
    expected_max = decision["proposed_max_users"]
    if settings.cohort_max_users != expected_max:
        raise ScaleActivationError("Deployed cohort max does not match the reviewed proposed_max_users.")
    configured_members = len(settings.cohort_account_ids)
    if configured_members <= decision["current_max_users"]:
        raise ScaleActivationError("Deployed cohort membership has not expanded beyond the prior cohort.")
    if configured_members > expected_max:
        raise ScaleActivationError("Deployed cohort membership exceeds the reviewed maximum.")
    if allowed_id not in settings.cohort_account_ids:
        raise ScaleActivationError("The allowed verification account is not in the deployed cohort.")
    if denied_id in settings.cohort_account_ids:
        raise ScaleActivationError("The denied verification account is unexpectedly in the deployed cohort.")


def build_evidence(
    *,
    decision: dict,
    deployment: dict,
    operator_status: dict,
    settings: Settings,
    scale_decision_path: Path,
    deployment_change_path: Path,
    operator_status_path: Path,
    provider_policy_activation_path: Path,
    now: datetime,
    microsoft_rollout_activation_path: Path | None = None,
    action_selection_activation_path: Path | None = None,
    action_selection_attestation: dict | None = None,
    action_proposals_activation_path: Path | None = None,
    action_proposals_attestation: dict | None = None,
    action_attachments_activation_path: Path | None = None,
    action_attachments_attestation: dict | None = None,
    action_reminders_activation_path: Path | None = None,
    action_reminders_attestation: dict | None = None,
    action_recipients_activation_path: Path | None = None,
    action_recipients_attestation: dict | None = None,
    action_document_sharing_activation_path: Path | None = None,
    action_document_sharing_attestation: dict | None = None,
) -> dict:
    artifact_sha256 = {
        "scale_decision": sha256_file(scale_decision_path),
        "deployment_change": sha256_file(deployment_change_path),
        "operator_status": sha256_file(operator_status_path),
        "provider_policy_activation": sha256_file(
            provider_policy_activation_path
        ),
    }
    if settings.microsoft_actions_enabled:
        if microsoft_rollout_activation_path is None:
            raise ScaleActivationError(
                "Microsoft rollout activation evidence is required when Microsoft actions are enabled."
            )
        artifact_sha256["microsoft_rollout_activation"] = sha256_file(
            microsoft_rollout_activation_path
        )

    action_selection_summary = None
    if getattr(settings, "agent_action_selection_enabled", False):
        if (
            action_selection_activation_path is None
            or action_selection_attestation is None
        ):
            raise ScaleActivationError(
                "Action selection activation evidence and ledger attestation "
                "are required when action selection is enabled."
            )
        artifact_sha256["action_selection_activation"] = sha256_file(
            action_selection_activation_path
        )
        action_selection_summary = {
            "ledger_sequence": action_selection_attestation["ledger_sequence"],
            "ledger_entry_hash": action_selection_attestation["ledger_entry_hash"],
        }

    action_proposals_summary = None
    if getattr(settings, "agent_action_proposals_enabled", False):
        if (
            action_proposals_activation_path is None
            or action_proposals_attestation is None
        ):
            raise ScaleActivationError(
                "Action proposals activation evidence and ledger attestation "
                "are required when action proposals are enabled."
            )
        artifact_sha256["action_proposals_activation"] = sha256_file(
            action_proposals_activation_path
        )
        action_proposals_summary = {
            "ledger_sequence": action_proposals_attestation["ledger_sequence"],
            "ledger_entry_hash": action_proposals_attestation["ledger_entry_hash"],
        }

    action_attachments_summary = None
    if getattr(settings, "action_attachments_enabled", False):
        if (
            action_attachments_activation_path is None
            or action_attachments_attestation is None
        ):
            raise ScaleActivationError(
                "Action attachments activation evidence and ledger attestation "
                "are required when approved action attachments are enabled."
            )
        artifact_sha256["action_attachments_activation"] = sha256_file(
            action_attachments_activation_path
        )
        action_attachments_summary = {
            "ledger_sequence": action_attachments_attestation["ledger_sequence"],
            "ledger_entry_hash": action_attachments_attestation["ledger_entry_hash"],
        }

    action_reminders_summary = None
    if getattr(settings, "action_reminders_enabled", False):
        if (
            action_reminders_activation_path is None
            or action_reminders_attestation is None
        ):
            raise ScaleActivationError(
                "Action reminders activation evidence and ledger attestation "
                "are required when approved calendar reminders are enabled."
            )
        artifact_sha256["action_reminders_activation"] = sha256_file(
            action_reminders_activation_path
        )
        action_reminders_summary = {
            "ledger_sequence": action_reminders_attestation["ledger_sequence"],
            "ledger_entry_hash": action_reminders_attestation["ledger_entry_hash"],
        }

    action_recipients_summary = None
    if getattr(settings, "action_recipients_enabled", False):
        if (
            action_recipients_activation_path is None
            or action_recipients_attestation is None
        ):
            raise ScaleActivationError(
                "Action recipients activation evidence and ledger attestation "
                "are required when saved action recipients are enabled."
            )
        artifact_sha256["action_recipients_activation"] = sha256_file(
            action_recipients_activation_path
        )
        action_recipients_summary = {
            "ledger_sequence": action_recipients_attestation["ledger_sequence"],
            "ledger_entry_hash": action_recipients_attestation["ledger_entry_hash"],
        }

    action_document_sharing_summary = None
    if getattr(settings, "action_document_sharing_enabled", False):
        if (
            action_document_sharing_activation_path is None
            or action_document_sharing_attestation is None
        ):
            raise ScaleActivationError(
                "Document sharing activation evidence and ledger attestation "
                "are required when document sharing is enabled."
            )
        artifact_sha256["action_document_sharing_activation"] = sha256_file(
            action_document_sharing_activation_path
        )
        action_document_sharing_summary = {
            "ledger_sequence": action_document_sharing_attestation["ledger_sequence"],
            "ledger_entry_hash": action_document_sharing_attestation["ledger_entry_hash"],
        }

    return {
        "schema_version": (
            7 if getattr(settings, "action_document_sharing_enabled", False)
            else 6 if getattr(settings, "action_recipients_enabled", False)
            else 5 if getattr(settings, "action_reminders_enabled", False)
            else 4 if getattr(settings, "action_attachments_enabled", False)
            else 3
        ),
        "status": "bounded_expansion_verified",
        "release_id": decision["release_id"],
        "verified_at": now.isoformat(),
        "current_stage": decision["current_stage"],
        "proposed_stage": decision["proposed_stage"],
        "current_max_users": decision["current_max_users"],
        "proposed_max_users": decision["proposed_max_users"],
        "configured_members": len(settings.cohort_account_ids),
        "configured_max_users": settings.cohort_max_users,
        "change_reference": deployment["change_reference"],
        "deployment_deployed_at": deployment["deployed_at"],
        "operator_status_generated_at": operator_status["generated_at"],
        "runtime_requirements": {
            "microsoft_actions_enabled": bool(
                settings.microsoft_actions_enabled
            ),
            "action_selection_enabled": bool(
                getattr(
                    settings,
                    "agent_action_selection_enabled",
                    False,
                )
            ),
            "action_proposals_enabled": bool(
                getattr(
                    settings,
                    "agent_action_proposals_enabled",
                    False,
                )
            ),
            **({
                "action_attachments_enabled": bool(getattr(settings, "action_attachments_enabled", False)),
                "action_reminders_enabled": bool(getattr(settings, "action_reminders_enabled", False)),
                "action_recipients_enabled": bool(getattr(settings, "action_recipients_enabled", False)),
                "action_document_sharing_enabled": True,
            } if getattr(settings, "action_document_sharing_enabled", False) else ({
                "action_attachments_enabled": bool(getattr(settings, "action_attachments_enabled", False)),
                "action_reminders_enabled": bool(getattr(settings, "action_reminders_enabled", False)),
                "action_recipients_enabled": True,
            } if getattr(settings, "action_recipients_enabled", False) else ({
                "action_attachments_enabled": bool(getattr(settings, "action_attachments_enabled", False)),
                "action_reminders_enabled": True,
            } if getattr(settings, "action_reminders_enabled", False) else ({
                "action_attachments_enabled": True,
            } if getattr(settings, "action_attachments_enabled", False) else {})))),
        },
        "action_selection": action_selection_summary,
        "action_proposals": action_proposals_summary,
        **({
            "action_attachments": action_attachments_summary,
        } if getattr(settings, "action_attachments_enabled", False) else {}),
        **({
            "action_reminders": action_reminders_summary,
        } if getattr(settings, "action_reminders_enabled", False) else {}),
        **({
            "action_recipients": action_recipients_summary,
        } if getattr(settings, "action_recipients_enabled", False) else {}),
        **({
            "action_document_sharing": action_document_sharing_summary,
        } if getattr(settings, "action_document_sharing_enabled", False) else {}),
        "artifact_sha256": artifact_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a reviewed Shuddho Coworker cohort expansion after deployment."
    )
    parser.add_argument("--scale-decision", type=Path, required=True)
    parser.add_argument("--deployment-change", type=Path, required=True)
    parser.add_argument("--operator-status", type=Path, required=True)
    parser.add_argument("--provider-policy-activation", type=Path, required=True)
    parser.add_argument("--microsoft-rollout-activation", type=Path)
    parser.add_argument("--action-selection-activation", type=Path)
    parser.add_argument("--action-proposals-activation", type=Path)
    parser.add_argument("--action-attachments-activation", type=Path)
    parser.add_argument("--action-reminders-activation", type=Path)
    parser.add_argument("--action-recipients-activation", type=Path)
    parser.add_argument("--action-document-sharing-activation", type=Path)
    parser.add_argument("--release-ledger", type=Path, required=True)
    parser.add_argument("--freshness-minutes", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.freshness_minutes < 1:
        raise SystemExit("--freshness-minutes must be positive.")

    try:
        decision = load_json(args.scale_decision, "scale decision")
        decision_time = validate_scale_decision(decision)
        deployment = load_json(args.deployment_change, "deployment change")
        deployment_time = validate_deployment_change(
            deployment,
            decision,
            not_before=decision_time,
        )
        validate_provider_policy_activation(
            args.provider_policy_activation,
            args.release_ledger,
            decision,
        )
        operator_status = load_json(args.operator_status, "operator status")
        now = datetime.now(timezone.utc)
        validate_operator_status(
            operator_status,
            decision,
            not_before=deployment_time,
            freshness_minutes=args.freshness_minutes,
            now=now,
        )

        settings = Settings.from_env()
        validate_microsoft_rollout_activation(
            args.microsoft_rollout_activation,
            args.release_ledger,
            decision,
            settings,
        )
        action_selection_attestation = validate_action_selection_activation(
            args.action_selection_activation,
            args.release_ledger,
            decision,
            settings,
        )
        action_proposals_attestation = validate_action_proposals_activation(
            args.action_proposals_activation,
            args.release_ledger,
            decision,
            settings,
        )
        action_attachments_attestation = validate_action_attachments_activation(
            args.action_attachments_activation,
            args.release_ledger,
            decision,
            settings,
        )
        action_reminders_attestation = validate_action_reminders_activation(
            args.action_reminders_activation,
            args.release_ledger,
            decision,
            settings,
        )
        action_recipients_attestation = validate_action_recipients_activation(
            args.action_recipients_activation,
            args.release_ledger,
            decision,
            settings,
        )
        action_document_sharing_attestation = validate_action_document_sharing_activation(
            args.action_document_sharing_activation,
            args.release_ledger,
            decision,
            settings,
        )
        base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
        allowed_token = env_secret("SHUDDHO_SCALE_VERIFY_TOKEN_ALLOWED")
        denied_token = env_secret("SHUDDHO_SCALE_VERIFY_TOKEN_DENIED")
        if allowed_token == denied_token:
            raise ScaleActivationError("Allowed and denied verification tokens must be different.")
        allowed_id = token_account_id(allowed_token, settings)
        denied_id = token_account_id(denied_token, settings)
        if allowed_id == denied_id:
            raise ScaleActivationError("Allowed and denied verification tokens resolve to the same account.")

        require_deployed_configuration(settings, decision, allowed_id, denied_id)
        assert_denied_unprovisioned(settings, denied_id)

        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            allowed = client.get("/api/v1/me", headers={"Authorization": "Bearer " + allowed_token})
            if allowed.status_code != 200:
                raise ScaleActivationError(
                    f"Allowed expanded-cohort account returned HTTP {allowed.status_code}; expected 200."
                )

            denied = client.get("/api/v1/me", headers={"Authorization": "Bearer " + denied_token})
            if denied.status_code != 403:
                raise ScaleActivationError(
                    f"Denied non-member account returned HTTP {denied.status_code}; expected 403."
                )
            try:
                denied_body = denied.json()
            except ValueError:
                raise ScaleActivationError("Denied cohort response did not return JSON.") from None
            if (
                not isinstance(denied_body, dict)
                or denied_body.get("error", {}).get("code") != "cohort_not_enabled"
            ):
                raise ScaleActivationError("Denied cohort response did not return cohort_not_enabled.")

        assert_denied_unprovisioned(settings, denied_id)
        evidence = build_evidence(
            decision=decision,
            deployment=deployment,
            operator_status=operator_status,
            settings=settings,
            scale_decision_path=args.scale_decision,
            deployment_change_path=args.deployment_change,
            operator_status_path=args.operator_status,
            provider_policy_activation_path=args.provider_policy_activation,
            microsoft_rollout_activation_path=args.microsoft_rollout_activation,
            action_selection_activation_path=args.action_selection_activation,
            action_selection_attestation=action_selection_attestation,
            action_proposals_activation_path=args.action_proposals_activation,
            action_proposals_attestation=action_proposals_attestation,
            action_attachments_activation_path=args.action_attachments_activation,
            action_attachments_attestation=action_attachments_attestation,
            action_reminders_activation_path=args.action_reminders_activation,
            action_reminders_attestation=action_reminders_attestation,
            action_recipients_activation_path=args.action_recipients_activation,
            action_recipients_attestation=action_recipients_attestation,
            action_document_sharing_activation_path=args.action_document_sharing_activation,
            action_document_sharing_attestation=action_document_sharing_attestation,
            now=now,
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": evidence["status"],
            "proposed_stage": evidence["proposed_stage"],
            "configured_members": evidence["configured_members"],
            "configured_max_users": evidence["configured_max_users"],
        }, indent=2))
    except (ScaleActivationError, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
