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


class ReminderProbeFailure(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_SIMPLE_REMINDER", "").lower() != "true":
        raise ReminderProbeFailure(
            "Set SHUDDHO_STAGING_ALLOW_SIMPLE_REMINDER=true only in approved controlled staging."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise ReminderProbeFailure(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a dedicated synthetic staging account."
        )


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ReminderProbeFailure(f"{name} is required.")
    return value


def clean_origin(value: str) -> str:
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ReminderProbeFailure(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    return clean


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
        raise ReminderProbeFailure(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ReminderProbeFailure(f"{label} must contain a JSON object.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def json_object(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise ReminderProbeFailure(
            f"{label} returned HTTP {response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise ReminderProbeFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ReminderProbeFailure(f"{label} returned an unexpected shape.")
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
        raise ReminderProbeFailure("Rollout manifest release_id is required.")
    manifest = json_object(
        client.get("/api/v1/runtime-manifest", headers=auth(token)),
        "runtime manifest",
    )
    environment = env("SHUDDHO_STAGING_EXPECTED_ENVIRONMENT").strip()
    if environment.lower() in PRODUCTION_NAMES:
        raise ReminderProbeFailure(
            "SHUDDHO_STAGING_EXPECTED_ENVIRONMENT must identify non-production."
        )
    if manifest.get("environment") != environment:
        raise ReminderProbeFailure(
            "Runtime environment does not match the expected staging environment."
        )
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ReminderProbeFailure(
            "Runtime manifest must expose a full lowercase source revision."
        )
    capabilities = manifest.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("automations") is not True
        or capabilities.get("personal_goals") is not True
    ):
        raise ReminderProbeFailure(
            "Automations and personal goals must be enabled in controlled staging."
        )
    deployment_reference = env("SHUDDHO_STAGING_DEPLOYMENT_REFERENCE").strip()
    if not deployment_reference:
        raise ReminderProbeFailure(
            "SHUDDHO_STAGING_DEPLOYMENT_REFERENCE must not be blank."
        )
    return {
        "release_id": release_id.strip(),
        "source_revision": revision,
        "environment": environment,
        "deployment_reference": deployment_reference,
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "provider_policy_sha256": sha256_file(provider_policy_path),
    }


def owned_state(client: httpx.Client, token: str, automation_id: str) -> dict:
    me = json_object(client.get("/api/v1/me", headers=auth(token)), "staging account")
    owner_id = str(me.get("account_id") or "")
    if not owner_id:
        raise ReminderProbeFailure("Synthetic staging account has no account_id.")

    payload = json_object(
        client.get("/api/v1/automations", headers=auth(token)),
        "automations",
    )
    rows = payload.get("automations")
    if payload.get("enabled") is not True or not isinstance(rows, list):
        raise ReminderProbeFailure("Automations are disabled or unavailable.")
    selected = [
        item for item in rows
        if str(item.get("id") or "") == automation_id
        and item.get("state") == "active"
        and item.get("run_profile") == "reminder"
    ]
    if len(selected) != 1:
        raise ReminderProbeFailure(
            "Expected one active owner-scoped reminder automation."
        )
    automation = selected[0]
    schedule = automation.get("schedule")
    if not isinstance(schedule, dict) or schedule.get("kind") not in {"daily", "weekly"}:
        raise ReminderProbeFailure(
            "Simple reminder must use a daily or weekly Temporal schedule."
        )
    if automation.get("connector_read_grant_ids") or automation.get("tool_allowlist"):
        raise ReminderProbeFailure(
            "Simple reminder must have no connector or tool authority."
        )

    history = json_object(
        client.get(f"/api/v1/automations/{automation_id}/history", headers=auth(token)),
        "automation history",
    ).get("history")
    notices = json_object(
        client.get("/api/v1/notifications", headers=auth(token)),
        "notifications",
    ).get("notifications")
    runs = json_object(
        client.get("/api/v1/agent-runs", headers=auth(token)),
        "agent runs",
    ).get("runs")
    if not isinstance(history, list) or not isinstance(notices, list) or not isinstance(runs, list):
        raise ReminderProbeFailure(
            "Reminder evidence endpoints returned an unexpected shape."
        )
    return {
        "owner_id": owner_id,
        "automation": automation,
        "history": history,
        "notifications": notices,
        "runs": runs,
    }


def prepare(args: argparse.Namespace) -> dict:
    require_guard()
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = release_identity(
            client, token, args.rollout, args.provider_policy_plan
        )
        current = owned_state(client, token, args.automation_id)

    state = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": "pa10_simple_scheduled_reminder",
        "release": release,
        "synthetic_account_label": env(
            "SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL"
        ).strip(),
        "owner_id": current["owner_id"],
        "automation_id": args.automation_id,
        "automation_revision": int(current["automation"]["revision"]),
        "timezone": current["automation"]["timezone"],
        "schedule": current["automation"]["schedule"],
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
        "baseline_agent_run_ids": sorted(
            str(item.get("id"))
            for item in current["runs"]
            if item.get("id") is not None
        ),
        "prepared_at": utcnow_iso(),
    }
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def verify(args: argparse.Namespace) -> dict:
    require_guard()
    state = load_json(args.state, "simple reminder state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ReminderProbeFailure("Simple reminder state has an unexpected schema.")
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    old_occurrences = set(state.get("baseline_occurrence_ids") or [])
    old_notices = set(state.get("baseline_notification_ids") or [])
    old_runs = set(state.get("baseline_agent_run_ids") or [])
    deadline = time.monotonic() + max(1, args.timeout)
    last_error: ReminderProbeFailure | None = None

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                release = release_identity(
                    client, token, args.rollout, args.provider_policy_plan
                )
                if release != state.get("release"):
                    raise ReminderProbeFailure(
                        "Deployed release identity changed between prepare and verify."
                    )
                current = owned_state(client, token, str(state["automation_id"]))
                if current["owner_id"] != state.get("owner_id"):
                    raise ReminderProbeFailure(
                        "Synthetic account identity changed during the exercise."
                    )
                if int(current["automation"]["revision"]) != int(state["automation_revision"]):
                    raise ReminderProbeFailure(
                        "Reminder automation revision changed during the exercise."
                    )

                history = [
                    item for item in current["history"]
                    if str(item.get("occurrence_id") or "") not in old_occurrences
                ]
                if len(history) != 1:
                    raise ReminderProbeFailure(
                        f"Expected exactly one new reminder occurrence; found {len(history)}."
                    )
                occurrence = history[0]
                if (
                    occurrence.get("trigger_type") != "schedule"
                    or occurrence.get("occurrence_state") != "notified"
                    or occurrence.get("run_id") is not None
                    or occurrence.get("run_state") is not None
                ):
                    raise ReminderProbeFailure(
                        "Reminder occurrence must be schedule-triggered, notified and have no Agent run."
                    )
                occurrence_id = str(occurrence.get("occurrence_id") or "")
                notices = [
                    item for item in current["notifications"]
                    if str(item.get("id") or "") not in old_notices
                    and str(item.get("automation_id") or "") == str(state["automation_id"])
                    and str(item.get("occurrence_id") or "") == occurrence_id
                ]
                if len(notices) != 1 or notices[0].get("kind") != "automation_reminder":
                    raise ReminderProbeFailure(
                        "Expected exactly one delivered automation_reminder notice."
                    )
                new_runs = [
                    item for item in current["runs"]
                    if str(item.get("id") or "") not in old_runs
                ]
                if new_runs:
                    raise ReminderProbeFailure(
                        "Simple reminder created an Agent run; zero new Agent runs are required."
                    )
                reference = args.operator_case_reference.strip()
                if not reference:
                    raise ReminderProbeFailure(
                        "A durable operator case/reference is required."
                    )

                evidence = {
                    "schema_version": SCHEMA_VERSION,
                    "evidence_kind": "pa10_simple_scheduled_reminder",
                    "status": "passed",
                    "release": release,
                    "synthetic_account_label": state["synthetic_account_label"],
                    "owner_id": state["owner_id"],
                    "automation_id": state["automation_id"],
                    "automation_revision": state["automation_revision"],
                    "timezone": state["timezone"],
                    "schedule": state["schedule"],
                    "prepared_at": state["prepared_at"],
                    "verified_at": utcnow_iso(),
                    "occurrence_id": occurrence_id,
                    "occurrence_state": occurrence["occurrence_state"],
                    "agent_run_count": 0,
                    "notification_count": 1,
                    "notification_kind": "automation_reminder",
                    "notification_id": str(notices[0]["id"]),
                    "notification_state": notices[0].get("state"),
                    "operator_case_reference": reference,
                }
                args.output.write_text(
                    json.dumps(evidence, indent=2) + "\n",
                    encoding="utf-8",
                )
                return evidence
            except ReminderProbeFailure as error:
                last_error = error
                time.sleep(max(1, args.poll_interval))

    raise last_error or ReminderProbeFailure(
        "Simple reminder evidence did not become available before timeout."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect release-bound controlled-staging evidence for one PA-10 simple "
            "scheduled reminder: exactly one delivered reminder and zero Agent runs."
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
    verify_parser.add_argument("--operator-case-reference", required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--timeout", type=int, default=300)
    verify_parser.add_argument("--poll-interval", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        result = prepare(args) if args.command == "prepare" else verify(args)
    except (httpx.HTTPError, ReminderProbeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    if args.command == "prepare":
        print(json.dumps({
            "status": "prepared",
            "state": str(args.state),
            "automation_id": result["automation_id"],
            "release": result["release"],
            "next": (
                "Keep the app/browser closed if that is the qualification case, allow exactly "
                "one reviewed Temporal reminder occurrence, then run verify."
            ),
        }, indent=2))
    else:
        print(json.dumps({
            "status": result["status"],
            "output": str(args.output),
            "occurrence_id": result["occurrence_id"],
            "notification_id": result["notification_id"],
            "agent_run_count": result["agent_run_count"],
        }, indent=2))


if __name__ == "__main__":
    main()
