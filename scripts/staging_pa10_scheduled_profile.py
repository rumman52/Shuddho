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
SCENARIOS = {
    "daily_coworker": {"profile": "briefing", "schedule": {"daily"}},
    "weekly_coworker": {"profile": "briefing", "schedule": {"weekly"}},
    "deadline_coworker": {"profile": "deadline", "schedule": {"daily", "weekly"}},
    "goal_driven_proactivity": {"profile": "proactive", "schedule": {"daily", "weekly"}},
}


class ScheduledProfileProbeFailure(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "").lower() != "true":
        raise ScheduledProfileProbeFailure(
            "Set SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES=true only in approved controlled staging."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise ScheduledProfileProbeFailure(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a synthetic staging account."
        )


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ScheduledProfileProbeFailure(f"{name} is required.")
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
        raise ScheduledProfileProbeFailure(
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
        raise ScheduledProfileProbeFailure(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ScheduledProfileProbeFailure(f"{label} must contain a JSON object.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def json_object(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise ScheduledProfileProbeFailure(
            f"{label} returned HTTP {response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise ScheduledProfileProbeFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ScheduledProfileProbeFailure(f"{label} returned an unexpected shape.")
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
        raise ScheduledProfileProbeFailure("Rollout manifest release_id is required.")
    manifest = json_object(
        client.get("/api/v1/runtime-manifest", headers=auth(token)),
        "runtime manifest",
    )
    environment = env("SHUDDHO_STAGING_EXPECTED_ENVIRONMENT").strip()
    if environment.lower() in PRODUCTION_NAMES:
        raise ScheduledProfileProbeFailure(
            "SHUDDHO_STAGING_EXPECTED_ENVIRONMENT must identify non-production."
        )
    if manifest.get("environment") != environment:
        raise ScheduledProfileProbeFailure(
            "Runtime environment does not match the expected staging environment."
        )
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ScheduledProfileProbeFailure(
            "Runtime manifest must expose a full lowercase source revision."
        )
    capabilities = manifest.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("automations") is not True
        or capabilities.get("personal_goals") is not True
    ):
        raise ScheduledProfileProbeFailure(
            "Automations and personal goals must be enabled in controlled staging."
        )
    deployment_reference = env("SHUDDHO_STAGING_DEPLOYMENT_REFERENCE").strip()
    if not deployment_reference:
        raise ScheduledProfileProbeFailure(
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


def load_owned(
    client: httpx.Client,
    token: str,
    automation_id: str,
    scenario: str,
) -> dict:
    me = json_object(client.get("/api/v1/me", headers=auth(token)), "staging account")
    owner_id = str(me.get("account_id") or "")
    if not owner_id:
        raise ScheduledProfileProbeFailure("Synthetic account has no account_id.")

    payload = json_object(
        client.get("/api/v1/automations", headers=auth(token)),
        "automations",
    )
    if payload.get("enabled") is not True:
        raise ScheduledProfileProbeFailure("Automations are disabled.")
    rows = payload.get("automations")
    if not isinstance(rows, list):
        raise ScheduledProfileProbeFailure("Automation list has an unexpected shape.")
    selected = [
        item for item in rows
        if str(item.get("id") or "") == automation_id and item.get("state") == "active"
    ]
    if len(selected) != 1:
        raise ScheduledProfileProbeFailure(
            "Expected one active owner-scoped automation with the requested id."
        )
    automation = selected[0]
    contract = SCENARIOS[scenario]
    schedule = automation.get("schedule")
    if (
        automation.get("run_profile") != contract["profile"]
        or not isinstance(schedule, dict)
        or schedule.get("kind") not in contract["schedule"]
    ):
        raise ScheduledProfileProbeFailure(
            f"Automation does not match the {scenario} profile/schedule contract."
        )

    history = json_object(
        client.get(f"/api/v1/automations/{automation_id}/history", headers=auth(token)),
        "automation history",
    ).get("history")
    notices = json_object(
        client.get("/api/v1/notifications", headers=auth(token)),
        "notifications",
    ).get("notifications")
    if not isinstance(history, list) or not isinstance(notices, list):
        raise ScheduledProfileProbeFailure(
            "Scheduled-profile evidence endpoints returned an unexpected shape."
        )
    return {
        "owner_id": owner_id,
        "automation": automation,
        "history": history,
        "notifications": notices,
    }


def prepare(args: argparse.Namespace) -> dict:
    require_guard()
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = release_identity(
            client, token, args.rollout, args.provider_policy_plan
        )
        current = load_owned(client, token, args.automation_id, args.scenario)
    state = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": "pa10_scheduled_profile",
        "scenario": args.scenario,
        "release": release,
        "synthetic_account_label": env(
            "SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL"
        ).strip(),
        "owner_id": current["owner_id"],
        "automation_id": args.automation_id,
        "automation_revision": int(current["automation"]["revision"]),
        "timezone": current["automation"]["timezone"],
        "schedule": current["automation"]["schedule"],
        "run_profile": current["automation"]["run_profile"],
        "output_language": current["automation"]["output_language"],
        "quiet_hours": current["automation"].get("quiet_hours"),
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


def verify(args: argparse.Namespace) -> dict:
    require_guard()
    state = load_json(args.state, "scheduled-profile state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ScheduledProfileProbeFailure(
            "Scheduled-profile state has an unexpected schema."
        )
    scenario = str(state.get("scenario") or "")
    if scenario not in SCENARIOS:
        raise ScheduledProfileProbeFailure("Scheduled-profile scenario is unsupported.")
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    old_occurrences = set(state.get("baseline_occurrence_ids") or [])
    old_notices = set(state.get("baseline_notification_ids") or [])
    deadline = time.monotonic() + max(1, args.timeout)
    last_error: ScheduledProfileProbeFailure | None = None

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                release = release_identity(
                    client, token, args.rollout, args.provider_policy_plan
                )
                if release != state.get("release"):
                    raise ScheduledProfileProbeFailure(
                        "Deployed release identity changed between prepare and verify."
                    )
                current = load_owned(
                    client, token, str(state["automation_id"]), scenario
                )
                if current["owner_id"] != state.get("owner_id"):
                    raise ScheduledProfileProbeFailure(
                        "Synthetic account identity changed during the scenario."
                    )
                if int(current["automation"]["revision"]) != int(state["automation_revision"]):
                    raise ScheduledProfileProbeFailure(
                        "Automation revision changed during the scenario."
                    )
                history = [
                    item for item in current["history"]
                    if str(item.get("occurrence_id") or "") not in old_occurrences
                ]
                if len(history) != 1:
                    raise ScheduledProfileProbeFailure(
                        f"Expected exactly one new logical occurrence; found {len(history)}."
                    )
                occurrence = history[0]
                if occurrence.get("trigger_type") != "schedule":
                    raise ScheduledProfileProbeFailure(
                        "Scheduled-profile occurrence did not use the schedule trigger."
                    )
                if occurrence.get("occurrence_state") != "accepted":
                    raise ScheduledProfileProbeFailure(
                        f"Occurrence state is {occurrence.get('occurrence_state')!r}; expected 'accepted'."
                    )
                if occurrence.get("run_state") != "completed":
                    raise ScheduledProfileProbeFailure(
                        "Scheduled-profile Agent run is not completed."
                    )
                occurrence_id = str(occurrence.get("occurrence_id") or "")
                run_id = str(occurrence.get("run_id") or "")
                if not occurrence_id or not run_id:
                    raise ScheduledProfileProbeFailure(
                        "Scheduled-profile occurrence is missing its occurrence/run identity."
                    )
                notices = [
                    item for item in current["notifications"]
                    if str(item.get("id") or "") not in old_notices
                    and str(item.get("automation_id") or "") == str(state["automation_id"])
                    and str(item.get("occurrence_id") or "") == occurrence_id
                ]
                started = [item for item in notices if item.get("kind") == "automation_started"]
                completed = [item for item in notices if item.get("kind") == "automation_completed"]
                if len(started) != 1 or len(completed) != 1:
                    raise ScheduledProfileProbeFailure(
                        "Expected exactly one start notice and one completion notice."
                    )
                evidence = {
                    "schema_version": SCHEMA_VERSION,
                    "evidence_kind": "pa10_scheduled_profile",
                    "scenario": scenario,
                    "status": "passed",
                    "release": release,
                    "synthetic_account_label": state["synthetic_account_label"],
                    "owner_id": state["owner_id"],
                    "automation_id": state["automation_id"],
                    "automation_revision": state["automation_revision"],
                    "timezone": state["timezone"],
                    "schedule": state["schedule"],
                    "run_profile": state["run_profile"],
                    "output_language": state["output_language"],
                    "quiet_hours": state["quiet_hours"],
                    "prepared_at": state["prepared_at"],
                    "verified_at": utcnow_iso(),
                    "occurrence_id": occurrence_id,
                    "due_at": occurrence.get("due_at"),
                    "run_id": run_id,
                    "run_state": "completed",
                    "run_updated_at": occurrence.get("run_updated_at"),
                    "started_notification_id": str(started[0]["id"]),
                    "completion_notification_id": str(completed[0]["id"]),
                    "new_notification_count": len(notices),
                    "operator_case_reference": args.operator_case_reference.strip(),
                }
                if not evidence["operator_case_reference"]:
                    raise ScheduledProfileProbeFailure(
                        "A durable operator case/reference is required."
                    )
                args.output.write_text(
                    json.dumps(evidence, indent=2) + "\n",
                    encoding="utf-8",
                )
                return evidence
            except ScheduledProfileProbeFailure as error:
                last_error = error
                time.sleep(max(1, args.poll_interval))
    raise last_error or ScheduledProfileProbeFailure(
        "Scheduled-profile evidence did not become available before timeout."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect release-bound evidence for one Agent-backed scheduled PA-10 profile occurrence. "
            "The separate one-notice reminder gate is intentionally not represented here. "
            "Repeat with fresh evidence for DST, edits, pause/resume, quiet-hours and other cases."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
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
    except (httpx.HTTPError, ScheduledProfileProbeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    if args.command == "prepare":
        print(json.dumps({
            "status": "prepared",
            "state": str(args.state),
            "scenario": result["scenario"],
            "automation_id": result["automation_id"],
            "release": result["release"],
            "next": (
                "Allow exactly one reviewed synthetic scheduled occurrence through Temporal, "
                "retain the operator case reference, then run verify."
            ),
        }, indent=2))
    else:
        print(json.dumps({
            "status": result["status"],
            "scenario": result["scenario"],
            "output": str(args.output),
            "occurrence_id": result["occurrence_id"],
            "run_id": result["run_id"],
            "completion_notification_id": result["completion_notification_id"],
        }, indent=2))


if __name__ == "__main__":
    main()
