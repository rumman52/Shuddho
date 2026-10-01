from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx


SCHEMA_VERSION = 1
PRODUCTION_NAMES = {"prod", "production"}


class ManagedRecoveryProbeFailure(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ManagedRecoveryProbeFailure(f"{label} is not a valid ISO-8601 timestamp.") from None
    if parsed.tzinfo is None:
        raise ManagedRecoveryProbeFailure(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_MANAGED_RECOVERY", "").lower() != "true":
        raise ManagedRecoveryProbeFailure(
            "Set SHUDDHO_STAGING_ALLOW_MANAGED_RECOVERY=true only for an approved staging recovery drill."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise ManagedRecoveryProbeFailure(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a dedicated synthetic staging account."
        )


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ManagedRecoveryProbeFailure(f"{name} is required.")
    return value


def clean_https_origin(value: str) -> str:
    value = value.rstrip("/")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ManagedRecoveryProbeFailure(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    return value


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
        raise ManagedRecoveryProbeFailure(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ManagedRecoveryProbeFailure(f"{label} must contain a JSON object.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def response_json(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise ManagedRecoveryProbeFailure(
            f"{label} returned HTTP {response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise ManagedRecoveryProbeFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ManagedRecoveryProbeFailure(f"{label} returned an unexpected shape.")
    return value


def release_identity(
    client: httpx.Client,
    token: str,
    rollout_path: Path,
    provider_policy_path: Path,
) -> dict:
    rollout = load_json(rollout_path, "rollout manifest")
    load_json(provider_policy_path, "provider-policy plan")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ManagedRecoveryProbeFailure("Rollout manifest release_id is required.")
    manifest = response_json(
        client.get("/api/v1/runtime-manifest", headers=auth(token)),
        "runtime manifest",
    )
    expected_environment = env("SHUDDHO_STAGING_EXPECTED_ENVIRONMENT").strip()
    if expected_environment.lower() in PRODUCTION_NAMES:
        raise ManagedRecoveryProbeFailure(
            "SHUDDHO_STAGING_EXPECTED_ENVIRONMENT must identify non-production."
        )
    if manifest.get("environment") != expected_environment:
        raise ManagedRecoveryProbeFailure(
            "Runtime environment does not match SHUDDHO_STAGING_EXPECTED_ENVIRONMENT."
        )
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ManagedRecoveryProbeFailure(
            "Runtime manifest must expose a full lowercase source revision."
        )
    capabilities = manifest.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("coworker") is not True
        or capabilities.get("automations") is not True
    ):
        raise ManagedRecoveryProbeFailure(
            "Coworker and automations must be enabled in the controlled-staging release."
        )
    deployment_reference = env("SHUDDHO_STAGING_DEPLOYMENT_REFERENCE").strip()
    if not deployment_reference:
        raise ManagedRecoveryProbeFailure(
            "SHUDDHO_STAGING_DEPLOYMENT_REFERENCE must not be blank."
        )
    return {
        "release_id": release_id.strip(),
        "source_revision": revision,
        "environment": expected_environment,
        "deployment_reference": deployment_reference,
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "provider_policy_sha256": sha256_file(provider_policy_path),
    }


def owned_state(client: httpx.Client, token: str, automation_id: str) -> dict:
    me = response_json(client.get("/api/v1/me", headers=auth(token)), "staging account")
    owner_id = str(me.get("account_id") or "")
    if not owner_id:
        raise ManagedRecoveryProbeFailure("Synthetic account has no account_id.")

    automations = response_json(
        client.get("/api/v1/automations", headers=auth(token)),
        "automations",
    )
    if automations.get("enabled") is not True:
        raise ManagedRecoveryProbeFailure("Automations are disabled.")
    rows = automations.get("automations")
    if not isinstance(rows, list):
        raise ManagedRecoveryProbeFailure("Automation list has an unexpected shape.")
    selected = [
        item for item in rows
        if str(item.get("id") or "") == automation_id
        and item.get("state") == "active"
    ]
    if len(selected) != 1:
        raise ManagedRecoveryProbeFailure(
            "The requested recovery automation must be one active owner-scoped automation."
        )
    automation = selected[0]

    history = response_json(
        client.get(f"/api/v1/automations/{automation_id}/history", headers=auth(token)),
        "automation history",
    ).get("history")
    notices = response_json(
        client.get("/api/v1/notifications", headers=auth(token)),
        "notifications",
    ).get("notifications")
    if not isinstance(history, list) or not isinstance(notices, list):
        raise ManagedRecoveryProbeFailure(
            "Recovery evidence endpoints returned an unexpected shape."
        )
    return {
        "owner_id": owner_id,
        "automation": automation,
        "history": history,
        "notifications": notices,
    }


def prepare(args: argparse.Namespace) -> dict:
    require_guard()
    base_url = clean_https_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    label = env("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL").strip()
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = release_identity(
            client, token, args.rollout, args.provider_policy_plan
        )
        current = owned_state(client, token, args.automation_id)

    state = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": "pa10_managed_recovery",
        "release": release,
        "synthetic_account_label": label,
        "owner_id": current["owner_id"],
        "automation_id": args.automation_id,
        "automation_revision": int(current["automation"]["revision"]),
        "baseline_occurrence_ids": sorted(
            str(item.get("occurrence_id"))
            for item in current["history"]
            if item.get("occurrence_id") is not None
        ),
        "baseline_notification_ids": sorted(
            str(item.get("id"))
            for item in current["notifications"]
            if item.get("id") is not None
        ),
        "prepared_at": utcnow_iso(),
    }
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def require_restart(
    *,
    name: str,
    at_value: str,
    reference: str,
    prepared_at: datetime,
) -> dict:
    at = parse_time(at_value, f"{name} restart time")
    if at < prepared_at:
        raise ManagedRecoveryProbeFailure(
            f"{name} restart occurred before the recovery exercise was prepared."
        )
    if not reference.strip() or len(reference.strip()) > 500:
        raise ManagedRecoveryProbeFailure(
            f"{name} restart reference must be non-empty and at most 500 characters."
        )
    return {"component": name, "restarted_at": at.isoformat(), "reference": reference.strip()}


def verify(args: argparse.Namespace) -> dict:
    require_guard()
    state = load_json(args.state, "managed recovery state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ManagedRecoveryProbeFailure("Managed recovery state has an unexpected schema.")
    prepared_at = parse_time(str(state.get("prepared_at") or ""), "prepared_at")
    restarts = [
        require_restart(
            name="api",
            at_value=args.api_restart_at,
            reference=args.api_restart_reference,
            prepared_at=prepared_at,
        ),
        require_restart(
            name="coworker-worker",
            at_value=args.worker_restart_at,
            reference=args.worker_restart_reference,
            prepared_at=prepared_at,
        ),
    ]
    base_url = clean_https_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    old_occurrences = set(state.get("baseline_occurrence_ids") or [])
    old_notices = set(state.get("baseline_notification_ids") or [])
    deadline = time.monotonic() + max(1, args.timeout)
    last_error: ManagedRecoveryProbeFailure | None = None

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                release = release_identity(
                    client, token, args.rollout, args.provider_policy_plan
                )
                if release != state.get("release"):
                    raise ManagedRecoveryProbeFailure(
                        "Deployed release identity changed between prepare and verify."
                    )
                current = owned_state(client, token, str(state["automation_id"]))
                if current["owner_id"] != state.get("owner_id"):
                    raise ManagedRecoveryProbeFailure(
                        "Synthetic account identity changed during the drill."
                    )
                if int(current["automation"]["revision"]) != int(state["automation_revision"]):
                    raise ManagedRecoveryProbeFailure(
                        "Automation revision changed during the recovery drill."
                    )
                history = [
                    item for item in current["history"]
                    if str(item.get("occurrence_id") or "") not in old_occurrences
                ]
                if len(history) != 1:
                    raise ManagedRecoveryProbeFailure(
                        f"Expected exactly one new logical occurrence; found {len(history)}."
                    )
                occurrence = history[0]
                if occurrence.get("run_state") != "completed":
                    raise ManagedRecoveryProbeFailure(
                        "Recovered automation run is not completed yet."
                    )
                run_id = str(occurrence.get("run_id") or "")
                if not run_id:
                    raise ManagedRecoveryProbeFailure(
                        "Recovered occurrence did not bind an Agent run."
                    )
                due_at = parse_time(
                    str(occurrence.get("due_at") or ""),
                    "recovered occurrence due_at",
                )
                completed_at = parse_time(
                    str(occurrence.get("run_updated_at") or ""),
                    "recovered run_updated_at",
                )
                if completed_at < due_at:
                    raise ManagedRecoveryProbeFailure(
                        "Recovered run completion precedes the occurrence due time."
                    )
                for restart in restarts:
                    restarted_at = parse_time(
                        restart["restarted_at"],
                        f"{restart['component']} restart time",
                    )
                    if restarted_at < due_at or restarted_at > completed_at:
                        raise ManagedRecoveryProbeFailure(
                            f"{restart['component']} restart did not occur between the "
                            "new occurrence due time and completed run update."
                        )
                occurrence_id = str(occurrence.get("occurrence_id") or "")
                notices = [
                    item for item in current["notifications"]
                    if str(item.get("id") or "") not in old_notices
                    and str(item.get("automation_id") or "") == str(state["automation_id"])
                    and str(item.get("occurrence_id") or "") == occurrence_id
                ]
                completion = [
                    item for item in notices
                    if item.get("kind") == "automation_completed"
                ]
                if len(completion) != 1:
                    raise ManagedRecoveryProbeFailure(
                        f"Expected exactly one completion notification after recovery; found {len(completion)}."
                    )
                verified_at = utcnow()
                if completed_at > verified_at:
                    raise ManagedRecoveryProbeFailure(
                        "Recovered run completion timestamp is in the future."
                    )
                evidence = {
                    "schema_version": SCHEMA_VERSION,
                    "evidence_kind": "pa10_managed_recovery",
                    "status": "passed",
                    "release": release,
                    "synthetic_account_label": state["synthetic_account_label"],
                    "owner_id": state["owner_id"],
                    "automation_id": state["automation_id"],
                    "automation_revision": state["automation_revision"],
                    "prepared_at": state["prepared_at"],
                    "verified_at": verified_at.isoformat(),
                    "restarts": restarts,
                    "occurrence_id": occurrence_id,
                    "trigger_type": occurrence.get("trigger_type"),
                    "due_at": due_at.isoformat(),
                    "run_id": run_id,
                    "run_state": "completed",
                    "run_completed_at": completed_at.isoformat(),
                    "completion_notification_id": str(completion[0]["id"]),
                    "new_notification_count": len(notices),
                    "duplicate_completion_notice_count": len(completion) - 1,
                    "exercise_reference": args.exercise_reference.strip(),
                }
                if not evidence["exercise_reference"]:
                    raise ManagedRecoveryProbeFailure(
                        "A durable managed-recovery exercise reference is required."
                    )
                args.output.write_text(
                    json.dumps(evidence, indent=2) + "\n",
                    encoding="utf-8",
                )
                return evidence
            except ManagedRecoveryProbeFailure as error:
                last_error = error
                time.sleep(max(1, args.poll_interval))
    raise last_error or ManagedRecoveryProbeFailure(
        "Managed recovery evidence did not become available before timeout."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect release-bound PA-10 evidence across real staging API and Coworker-worker "
            "restarts. The operator performs the platform restarts; this script verifies one "
            "logical completed automation occurrence and one completion notification afterwards."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--automation-id", required=True)
    prepare_parser.add_argument("--rollout", type=Path, required=True)
    prepare_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--rollout", type=Path, required=True)
    verify_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--api-restart-at", required=True)
    verify_parser.add_argument("--api-restart-reference", required=True)
    verify_parser.add_argument("--worker-restart-at", required=True)
    verify_parser.add_argument("--worker-restart-reference", required=True)
    verify_parser.add_argument("--exercise-reference", required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--timeout", type=int, default=300)
    verify_parser.add_argument("--poll-interval", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        result = prepare(args) if args.command == "prepare" else verify(args)
    except (httpx.HTTPError, ManagedRecoveryProbeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    if args.command == "prepare":
        print(json.dumps({
            "status": "prepared",
            "state": str(args.state),
            "automation_id": result["automation_id"],
            "release": result["release"],
            "next": (
                "Allow exactly one approved synthetic automation occurrence during the drill. "
                "Restart/replace the staging API and Coworker worker through the real platform, "
                "retain their timestamps and platform references, then run verify."
            ),
        }, indent=2))
    else:
        print(json.dumps({
            "status": result["status"],
            "output": str(args.output),
            "occurrence_id": result["occurrence_id"],
            "run_id": result["run_id"],
            "completion_notification_id": result["completion_notification_id"],
        }, indent=2))


if __name__ == "__main__":
    main()
