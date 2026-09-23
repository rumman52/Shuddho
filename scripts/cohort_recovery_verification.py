from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.cohort_canary_progression import load_plan
from scripts.cohort_health_gate import collect_snapshot, evaluate, load_thresholds
from scripts.cohort_observability_export import atomic_write, operator_status
from scripts.cohort_release_gate import load_rollout
from scripts.cohort_release_ledger import (
    file_sha256 as ledger_file_sha256,
    ledger_key,
    read_entries,
    require_exact_attested_event,
    verified_release_entries,
    verify_entries,
)
from scripts.staging_cohort_admission import token_account_id
from services.coworker.config import Settings, enabled as coworker_enabled

TERMINAL = {"completed", "failed", "cancelled", "needs_input"}
CAPABILITY_ATTRS = {
    "work_services": "work_services_enabled",
    "artifact_services": "artifact_services_enabled",
    "agent_runtime": "agent_runtime_enabled",
    "intelligent_planner": "intelligent_planner_enabled",
    "memory": "agent_memory_enabled",
    "handoffs": "agent_handoffs_enabled",
    "multi_handoffs": "agent_multi_handoffs_enabled",
    "dependency_graph": "agent_dependency_graph_enabled",
    "parallel_execution": "agent_parallel_execution_enabled",
    "outcome_replan": "agent_outcome_replan_enabled",
    "research": "research_services_enabled",
    "actions": "actions_enabled",
    "action_selection": "agent_action_selection_enabled",
}


class RecoveryVerificationError(RuntimeError):
    pass


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RecoveryVerificationError(f"{label} must be an ISO-8601 timestamp.") from None
    if result.tzinfo is None:
        raise RecoveryVerificationError(f"{label} must include a timezone.")
    return result.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecoveryVerificationError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise RecoveryVerificationError(f"{label} must contain a JSON object.")
    return value


def https_origin(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RecoveryVerificationError(
            "SHUDDHO_RECOVERY_API_BASE_URL must be a clean HTTPS origin."
        )
    return value.rstrip("/")


def secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RecoveryVerificationError(f"{name} is required.")
    return value


def stage_for(plan: dict, name: str) -> dict:
    for stage in plan["stages"]:
        if stage["name"] == name:
            return stage
    raise RecoveryVerificationError(f"Unknown current canary stage: {name}")


def validate_recovery_configuration(
    settings: Settings,
    rollout: dict,
    plan: dict,
    rollback_completion: dict,
    *,
    rollout_path: Path,
    current_stage: str,
    deployed_at: datetime,
) -> dict:
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise RecoveryVerificationError("Rollout manifest release_id is required.")
    if plan.get("release_id") != release_id:
        raise RecoveryVerificationError("Canary plan release_id does not match rollout manifest.")
    if rollback_completion.get("release_id") != release_id:
        raise RecoveryVerificationError("Rollback completion release_id does not match rollout manifest.")
    if rollback_completion.get("status") != "rollback_completed":
        raise RecoveryVerificationError("Recovery requires passed rollback-completion evidence.")
    if rollback_completion.get("mode") != "global":
        raise RecoveryVerificationError(
            "This recovery increment only re-enables Coworker after a completed global rollback."
        )
    rollback_hashes = rollback_completion.get("artifact_sha256")
    if not isinstance(rollback_hashes, dict) or rollback_hashes.get("rollout_manifest") != sha256_file(rollout_path):
        raise RecoveryVerificationError("Rollback completion does not bind this rollout manifest.")
    rollback_verified = rollback_completion.get("verified_at")
    if not isinstance(rollback_verified, str):
        raise RecoveryVerificationError("Rollback completion has no verified_at timestamp.")
    if deployed_at <= parse_time(rollback_verified, "rollback verified_at"):
        raise RecoveryVerificationError(
            "Recovery deployment must occur after rollback completion was verified."
        )

    capabilities = rollout.get("capabilities")
    if not isinstance(capabilities, dict):
        raise RecoveryVerificationError("Rollout manifest has no capabilities object.")
    if capabilities.get("coworker") is not True:
        raise RecoveryVerificationError("Recovery requires coworker=true in the approved rollout manifest.")
    if not coworker_enabled():
        raise RecoveryVerificationError("SHUDDHO_COWORKER_ENABLED is not enabled after recovery deployment.")

    mismatches: list[str] = []
    for key, attr in CAPABILITY_ATTRS.items():
        expected = capabilities.get(key, False) if key == "action_selection" else capabilities.get(key)
        if not isinstance(expected, bool):
            raise RecoveryVerificationError(f"Rollout capability {key!r} must be boolean.")
        actual = bool(getattr(settings, attr))
        if actual != expected:
            mismatches.append(f"{key} expected={str(expected).lower()} actual={str(actual).lower()}")
    if mismatches:
        raise RecoveryVerificationError(
            "Deployed capability flags do not match the approved rollout manifest: "
            + ", ".join(mismatches)
        )

    if not settings.cohort_enforced or not settings.cohort_account_ids:
        raise RecoveryVerificationError("Backend cohort enforcement must remain enabled during recovery.")
    stage = stage_for(plan, current_stage)
    members = len(settings.cohort_account_ids)
    if members < stage["min_members"] or members > stage["max_users"]:
        raise RecoveryVerificationError(
            f"Configured cohort members ({members}) are outside {current_stage} bounds "
            f"{stage['min_members']}..{stage['max_users']}."
        )
    rollout_max = rollout.get("cohort", {}).get("max_users") if isinstance(rollout.get("cohort"), dict) else None
    if not isinstance(rollout_max, int) or isinstance(rollout_max, bool) or members > rollout_max:
        raise RecoveryVerificationError("Configured cohort exceeds the approved rollout-manifest maximum.")
    return {
        "release_id": release_id,
        "members": members,
        "stage_min": stage["min_members"],
        "stage_max": stage["max_users"],
        "capabilities": {key: bool(capabilities[key]) for key in ["coworker", *CAPABILITY_ATTRS]},
    }



def validate_microsoft_recovery_activation(
    *,
    settings: Settings,
    activation_path: Path | None,
    ledger_path: Path | None,
    release_id: str,
    current_stage: str,
    rollback_completion: dict,
    rollback_path: Path,
    recovery_deployed_at: datetime,
) -> dict | None:
    if not getattr(settings, "microsoft_actions_enabled", False):
        return None
    if activation_path is None or ledger_path is None:
        raise RecoveryVerificationError(
            "Microsoft actions are enabled but fresh Microsoft rollout activation "
            "and the release ledger are required for recovery."
        )

    activation = load_json(
        activation_path,
        "post-rollback Microsoft rollout activation",
    )
    if activation.get("status") != "microsoft_rollout_verified":
        raise RecoveryVerificationError(
            "Post-rollback Microsoft rollout activation has not been verified."
        )
    if activation.get("release_id") != release_id:
        raise RecoveryVerificationError(
            "Post-rollback Microsoft rollout activation release_id does not match."
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
        raise RecoveryVerificationError(
            "Post-rollback Microsoft activation does not prove enabled backend/frontend controls."
        )

    deployed_at = activation.get("deployed_at")
    verified_at = activation.get("verified_at")
    if not isinstance(deployed_at, str) or not isinstance(verified_at, str):
        raise RecoveryVerificationError(
            "Post-rollback Microsoft activation is missing deployment/verification timestamps."
        )
    microsoft_deployed = parse_time(
        deployed_at,
        "Microsoft rollout deployed_at",
    )
    microsoft_verified = parse_time(
        verified_at,
        "Microsoft rollout verified_at",
    )
    rollback_verified_at = rollback_completion.get("verified_at")
    if not isinstance(rollback_verified_at, str):
        raise RecoveryVerificationError(
            "Rollback completion has no verified_at timestamp."
        )
    rollback_verified = parse_time(
        rollback_verified_at,
        "rollback verified_at",
    )
    if microsoft_deployed < recovery_deployed_at:
        raise RecoveryVerificationError(
            "Microsoft rollout activation predates the recovery deployment."
        )
    if microsoft_verified < microsoft_deployed:
        raise RecoveryVerificationError(
            "Microsoft rollout activation was verified before its deployment."
        )
    if microsoft_verified <= rollback_verified:
        raise RecoveryVerificationError(
            "Microsoft rollout activation must be freshly verified after rollback completion."
        )

    try:
        entries = read_entries(ledger_path)
        state = verify_entries(entries, ledger_key())
    except Exception as error:
        raise RecoveryVerificationError(
            f"Release ledger verification failed: {error}"
        ) from None
    if state.get("release_id") != release_id:
        raise RecoveryVerificationError(
            "Release ledger release_id does not match recovery."
        )

    rollback_hash = ledger_file_sha256(rollback_path)
    rollback_entries = [
        item
        for item in entries
        if item.get("schema_version") == 2
        and item.get("event_type") == "rollback_completed"
        and item.get("current_stage") == current_stage
        and item.get("artifact_sha256", {}).get("rollback_completion")
        == rollback_hash
    ]
    if len(rollback_entries) != 1:
        raise RecoveryVerificationError(
            "Recovery requires exactly one ledgered rollback_completed event "
            "for the exact rollback evidence."
        )
    rollback_entry = rollback_entries[0]

    activation_hash = ledger_file_sha256(activation_path)
    microsoft_entries = [
        item
        for item in entries
        if item.get("schema_version") == 6
        and item.get("event_type") == "microsoft_rollout_verified"
        and item.get("current_stage") == current_stage
        and item.get("next_stage") is None
        and item.get("artifact_sha256", {}).get("rollout_activation")
        == activation_hash
        and item.get("sequence", 0) > rollback_entry.get("sequence", 0)
    ]
    if len(microsoft_entries) != 1:
        raise RecoveryVerificationError(
            "Microsoft-enabled recovery requires exactly one fresh schema-v6 "
            "microsoft_rollout_verified event after the exact rollback completion."
        )

    return {
        "activation": activation,
        "ledger_sequence": microsoft_entries[0]["sequence"],
        "ledger_entry_hash": microsoft_entries[0]["entry_hash"],
        "activation_sha256": activation_hash,
    }




def validate_action_selection_recovery_activation(
    *,
    settings: Settings,
    activation_path: Path | None,
    ledger_path: Path | None,
    release_id: str,
    current_stage: str,
    rollback_completion: dict,
    rollback_path: Path,
    recovery_deployed_at: datetime,
) -> dict | None:
    if not getattr(settings, "agent_action_selection_enabled", False):
        return None
    if activation_path is None or ledger_path is None:
        raise RecoveryVerificationError(
            "Agent action selection is enabled but a fresh action-selection "
            "activation and the release ledger are required for recovery."
        )

    activation = load_json(
        activation_path,
        "post-rollback action-selection activation",
    )
    if activation.get("status") != "action_selection_verified":
        raise RecoveryVerificationError(
            "Post-rollback action-selection activation has not been verified."
        )
    if activation.get("release_id") != release_id:
        raise RecoveryVerificationError(
            "Post-rollback action-selection activation release_id does not match."
        )
    if activation.get("current_stage") != current_stage:
        raise RecoveryVerificationError(
            "Post-rollback action-selection activation current_stage does not match."
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
        raise RecoveryVerificationError(
            "Post-rollback action-selection activation does not prove "
            "required runtime controls."
        )

    deployed_at = activation.get("deployed_at")
    verified_at = activation.get("verified_at")
    if not isinstance(deployed_at, str) or not isinstance(verified_at, str):
        raise RecoveryVerificationError(
            "Post-rollback action-selection activation is missing "
            "deployment/verification timestamps."
        )
    action_deployed = parse_time(
        deployed_at,
        "action-selection deployed_at",
    )
    action_verified = parse_time(
        verified_at,
        "action-selection verified_at",
    )
    rollback_verified_at = rollback_completion.get("verified_at")
    if not isinstance(rollback_verified_at, str):
        raise RecoveryVerificationError(
            "Rollback completion has no verified_at timestamp."
        )
    rollback_verified = parse_time(
        rollback_verified_at,
        "rollback verified_at",
    )
    if action_deployed < recovery_deployed_at:
        raise RecoveryVerificationError(
            "Action-selection activation predates the recovery deployment."
        )
    if action_verified < action_deployed:
        raise RecoveryVerificationError(
            "Action-selection activation was verified before its deployment."
        )
    if action_verified <= rollback_verified:
        raise RecoveryVerificationError(
            "Action-selection activation must be freshly verified after rollback completion."
        )

    try:
        entries, _ = verified_release_entries(
            ledger_path,
            release_id,
        )
        rollback_hash = ledger_file_sha256(rollback_path)
        rollback_entry = require_exact_attested_event(
            entries,
            schema_version=2,
            event_type="rollback_completed",
            current_stage=current_stage,
            next_stage=None,
            artifact_key="rollback_completion",
            artifact_sha256=rollback_hash,
            label="Recovery rollback attestation",
        )
        activation_hash = ledger_file_sha256(activation_path)
        action_entry = require_exact_attested_event(
            entries,
            schema_version=7,
            event_type="action_selection_verified",
            current_stage=current_stage,
            next_stage=None,
            artifact_key="action_selection_activation",
            artifact_sha256=activation_hash,
            after_sequence=rollback_entry["sequence"],
            label="Action-selection recovery attestation",
        )
    except Exception as error:
        raise RecoveryVerificationError(
            f"Release ledger verification failed: {error}"
        ) from None

    return {
        "activation": activation,
        "ledger_sequence": action_entry["sequence"],
        "ledger_entry_hash": action_entry["entry_hash"],
        "activation_sha256": activation_hash,
    }


def expect_json(response: httpx.Response, status: int, label: str) -> dict:
    if response.status_code != status:
        raise RecoveryVerificationError(
            f"{label} returned HTTP {response.status_code}; expected {status}."
        )
    try:
        value = response.json()
    except ValueError:
        raise RecoveryVerificationError(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise RecoveryVerificationError(f"{label} returned an unexpected JSON shape.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def run_live_recovery_probe(
    *,
    base_url: str,
    allowed_token: str,
    denied_token: str,
    settings: Settings,
    timeout_seconds: int,
) -> dict:
    allowed_id = token_account_id(allowed_token, settings)
    denied_id = token_account_id(denied_token, settings)
    if allowed_id == denied_id:
        raise RecoveryVerificationError("Allowed and denied recovery tokens resolve to the same account.")
    if allowed_id not in settings.cohort_account_ids:
        raise RecoveryVerificationError("Allowed recovery account is not in the backend cohort allowlist.")
    if denied_id in settings.cohort_account_ids:
        raise RecoveryVerificationError("Denied recovery account is unexpectedly in the cohort allowlist.")

    marker = uuid.uuid4().hex
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        expect_json(client.get("/api/v1/me", headers=auth(allowed_token)), 200, "allowed recovery /me")
        denied = expect_json(client.get("/api/v1/me", headers=auth(denied_token)), 403, "denied recovery /me")
        if denied.get("error", {}).get("code") != "cohort_not_enabled":
            raise RecoveryVerificationError("Denied recovery identity did not return cohort_not_enabled.")

        task = expect_json(
            client.post(
                "/api/v1/tasks",
                headers=auth(allowed_token) | {"Idempotency-Key": "recovery-" + marker},
                json={
                    "skill_id": "report_email",
                    "instruction": "Create a short synthetic Shuddho recovery validation report and email draft.",
                    "notes": "Synthetic recovery probe only. No customer data.",
                    "document_ids": [],
                    "output_language": "en",
                },
            ),
            202,
            "recovery task create",
        )
        task_id = str(task.get("id") or "")
        if not task_id:
            raise RecoveryVerificationError("Recovery task creation returned no task id.")

        deadline = time.monotonic() + max(30, timeout_seconds)
        result = task
        while time.monotonic() < deadline:
            result = expect_json(
                client.get(f"/api/v1/tasks/{task_id}", headers=auth(allowed_token)),
                200,
                "recovery task status",
            )
            if result.get("state") in TERMINAL:
                break
            time.sleep(2)
        else:
            client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth(allowed_token))
            raise RecoveryVerificationError("Recovery task did not finish before timeout.")

        if result.get("state") != "completed":
            raise RecoveryVerificationError(
                f"Recovery task ended in state {result.get('state')!r}; expected 'completed'."
            )
        artifacts = result.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise RecoveryVerificationError("Recovery task produced no artifact.")
        artifact_id = str(artifacts[0].get("id") or "")
        if not artifact_id:
            raise RecoveryVerificationError("Recovery artifact metadata has no id.")

        download = expect_json(
            client.get(f"/api/v1/artifacts/{artifact_id}/download", headers=auth(allowed_token)),
            200,
            "recovery artifact download authorization",
        )
        if download.get("url"):
            response = httpx.get(str(download["url"]), timeout=20, follow_redirects=False)
            if response.status_code != 200 or not response.content:
                raise RecoveryVerificationError(
                    f"Recovery signed artifact returned HTTP {response.status_code} or empty content."
                )
        elif download.get("content_path"):
            response = client.get(str(download["content_path"]), headers=auth(allowed_token))
            if response.status_code != 200 or not response.content:
                raise RecoveryVerificationError(
                    f"Recovery owned artifact returned HTTP {response.status_code} or empty content."
                )
        else:
            raise RecoveryVerificationError("Recovery artifact response has no download location.")

    updated_at = result.get("updated_at")
    if not isinstance(updated_at, str):
        raise RecoveryVerificationError("Recovery task response has no updated_at timestamp.")
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    return {
        "task_state": "completed",
        "task_updated_at": parse_time(updated_at, "recovery task updated_at").isoformat(),
        "artifact_count": len(artifacts),
        "model_attempts": int(usage.get("model_attempts") or 0),
        "accounted_tokens": int(usage.get("accounted_tokens") or 0),
        "admission": {"allowed": 200, "denied": 403},
    }


def build_recovery_evidence(
    *,
    settings: Settings,
    rollout: dict,
    rollout_path: Path,
    plan: dict,
    plan_path: Path,
    rollback_completion: dict,
    rollback_path: Path,
    thresholds: dict,
    current_stage: str,
    deployment_reference: str,
    deployed_at: str,
    base_url: str,
    allowed_token: str,
    denied_token: str,
    task_timeout: int,
    status_output: Path,
    microsoft_rollout_activation_path: Path | None = None,
    action_selection_activation_path: Path | None = None,
    release_ledger_path: Path | None = None,
) -> dict:
    if not deployment_reference.strip() or len(deployment_reference) > 500:
        raise RecoveryVerificationError(
            "deployment_reference must be non-empty and at most 500 characters."
        )
    deployment_time = parse_time(deployed_at, "deployed_at")
    config = validate_recovery_configuration(
        settings,
        rollout,
        plan,
        rollback_completion,
        rollout_path=rollout_path,
        current_stage=current_stage,
        deployed_at=deployment_time,
    )
    microsoft_recovery = validate_microsoft_recovery_activation(
        settings=settings,
        activation_path=microsoft_rollout_activation_path,
        ledger_path=release_ledger_path,
        release_id=config["release_id"],
        current_stage=current_stage,
        rollback_completion=rollback_completion,
        rollback_path=rollback_path,
        recovery_deployed_at=deployment_time,
    )
    action_selection_recovery = validate_action_selection_recovery_activation(
        settings=settings,
        activation_path=action_selection_activation_path,
        ledger_path=release_ledger_path,
        release_id=config["release_id"],
        current_stage=current_stage,
        rollback_completion=rollback_completion,
        rollback_path=rollback_path,
        recovery_deployed_at=deployment_time,
    )

    probe = run_live_recovery_probe(
        base_url=base_url,
        allowed_token=allowed_token,
        denied_token=denied_token,
        settings=settings,
        timeout_seconds=task_timeout,
    )
    probe_finished = parse_time(probe["task_updated_at"], "recovery task updated_at")
    if probe_finished < deployment_time:
        raise RecoveryVerificationError("Recovery smoke task predates the recovery deployment.")

    snapshot = collect_snapshot(
        settings,
        window_minutes=thresholds["window_minutes"],
    )
    result = evaluate(snapshot, rollout, thresholds)
    if result["decision"] != "CONTINUE_COHORT" or result["breaches"]:
        names = ", ".join(item["metric"] for item in result["breaches"])
        raise RecoveryVerificationError(
            "Post-recovery health is not clean"
            + (f": {names}" if names else ".")
        )
    status = operator_status(result)
    health_time = parse_time(status["generated_at"], "post-recovery health generated_at")
    if health_time < probe_finished:
        raise RecoveryVerificationError(
            "Post-recovery health snapshot predates completion of the recovery smoke task."
        )
    if status["cohort_members_configured"] != config["members"]:
        raise RecoveryVerificationError(
            "Post-recovery health cohort count differs from the deployed cohort allowlist."
        )
    atomic_write(status_output, json.dumps(status, indent=2) + "\n")

    artifact_sha256 = {
        "rollout_manifest": sha256_file(rollout_path),
        "canary_plan": sha256_file(plan_path),
        "rollback_completion": sha256_file(rollback_path),
        "operator_status": sha256_file(status_output),
    }
    microsoft_summary = None
    if microsoft_recovery is not None:
        artifact_sha256["microsoft_rollout_activation"] = (
            microsoft_recovery["activation_sha256"]
        )
        microsoft_summary = {
            "ledger_sequence": microsoft_recovery["ledger_sequence"],
            "ledger_entry_hash": microsoft_recovery["ledger_entry_hash"],
        }

    action_selection_summary = None
    if action_selection_recovery is not None:
        artifact_sha256["action_selection_activation"] = (
            action_selection_recovery["activation_sha256"]
        )
        action_selection_summary = {
            "ledger_sequence": action_selection_recovery["ledger_sequence"],
            "ledger_entry_hash": action_selection_recovery["ledger_entry_hash"],
        }

    return {
        "schema_version": 2,
        "release_id": config["release_id"],
        "status": "recovery_verified",
        "current_stage": current_stage,
        "deployment_reference": deployment_reference,
        "deployed_at": deployment_time.isoformat(),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "configured_members": config["members"],
        "capabilities": config["capabilities"],
        "probe": probe,
        "post_recovery_health": {
            "generated_at": status["generated_at"],
            "decision": status["decision"],
            "breaches": len(status["breaches"]),
        },
        "microsoft_rollout": microsoft_summary,
        "action_selection": action_selection_summary,
        "artifact_sha256": artifact_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify controlled Shuddho Coworker recovery after a completed global rollback."
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--canary-plan", type=Path, required=True)
    parser.add_argument("--rollback-completion", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--current-stage", required=True)
    parser.add_argument("--deployment-reference", required=True)
    parser.add_argument("--deployed-at", required=True)
    parser.add_argument("--task-timeout", type=int, default=180)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--microsoft-rollout-activation", type=Path)
    parser.add_argument("--action-selection-activation", type=Path)
    parser.add_argument("--release-ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        rollout = load_rollout(args.rollout)
        plan = load_plan(args.canary_plan)
        rollback_completion = load_json(args.rollback_completion, "rollback completion evidence")
        thresholds = load_thresholds(args.thresholds)
        evidence = build_recovery_evidence(
            settings=settings,
            rollout=rollout,
            rollout_path=args.rollout,
            plan=plan,
            plan_path=args.canary_plan,
            rollback_completion=rollback_completion,
            rollback_path=args.rollback_completion,
            thresholds=thresholds,
            current_stage=args.current_stage,
            deployment_reference=args.deployment_reference,
            deployed_at=args.deployed_at,
            base_url=https_origin(secret("SHUDDHO_RECOVERY_API_BASE_URL")),
            allowed_token=secret("SHUDDHO_RECOVERY_TOKEN_ALLOWED"),
            denied_token=secret("SHUDDHO_RECOVERY_TOKEN_DENIED"),
            task_timeout=max(30, args.task_timeout),
            status_output=args.status_output,
            microsoft_rollout_activation_path=args.microsoft_rollout_activation,
            action_selection_activation_path=args.action_selection_activation,
            release_ledger_path=args.release_ledger,
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": evidence["status"],
            "current_stage": evidence["current_stage"],
            "deployment_reference": evidence["deployment_reference"],
        }, indent=2))
    except (RecoveryVerificationError, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
