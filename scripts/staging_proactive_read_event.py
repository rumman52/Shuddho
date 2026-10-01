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
ALLOWED_PROVIDERS = {"google", "microsoft"}
ALLOWED_CAPABILITIES = {"email_read", "calendar_read"}
ALLOWED_SUBSCRIPTION_STATES = {"active", "renewing"}
PRODUCTION_NAMES = {"prod", "production"}


class ProactiveReadProbeFailure(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_PROACTIVE_READ_EVENTS", "").lower() != "true":
        raise ProactiveReadProbeFailure(
            "Set SHUDDHO_STAGING_ALLOW_PROACTIVE_READ_EVENTS=true only in approved controlled staging."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise ProactiveReadProbeFailure(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a dedicated synthetic staging account."
        )


def env_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ProactiveReadProbeFailure(f"{name} is required.")
    return value


def require_https_base(value: str) -> str:
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ProactiveReadProbeFailure(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    return clean


def require_revision(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ProactiveReadProbeFailure(
            "The deployed runtime manifest must expose a full lowercase source revision."
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rollout_identity(path: Path, provider_policy_path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProactiveReadProbeFailure(
            f"Could not read rollout manifest: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ProactiveReadProbeFailure("Rollout manifest must contain a JSON object.")
    release_id = value.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ProactiveReadProbeFailure("Rollout manifest release_id is required.")
    try:
        policy = json.loads(provider_policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProactiveReadProbeFailure(
            f"Could not read provider-policy plan: {type(error).__name__}"
        ) from None
    if not isinstance(policy, dict):
        raise ProactiveReadProbeFailure("Provider-policy plan must contain a JSON object.")
    deployment_reference = env_secret("SHUDDHO_STAGING_DEPLOYMENT_REFERENCE").strip()
    if not deployment_reference:
        raise ProactiveReadProbeFailure("SHUDDHO_STAGING_DEPLOYMENT_REFERENCE must not be blank.")
    return {
        "release_id": release_id.strip(),
        "rollout_manifest_sha256": sha256_file(path),
        "provider_policy_sha256": sha256_file(provider_policy_path),
        "deployment_reference": deployment_reference,
    }


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def json_object(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise ProactiveReadProbeFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise ProactiveReadProbeFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ProactiveReadProbeFailure(f"{label} returned an unexpected JSON shape.")
    return value


def runtime_context(
    client: httpx.Client,
    token: str,
    rollout: dict,
) -> dict:
    manifest = json_object(
        client.get("/api/v1/runtime-manifest", headers=auth(token)),
        "runtime manifest",
    )
    expected_environment = env_secret("SHUDDHO_STAGING_EXPECTED_ENVIRONMENT").strip()
    if expected_environment.lower() in PRODUCTION_NAMES:
        raise ProactiveReadProbeFailure(
            "SHUDDHO_STAGING_EXPECTED_ENVIRONMENT must identify a non-production environment."
        )
    environment = str(manifest.get("environment") or "").strip()
    if environment != expected_environment:
        raise ProactiveReadProbeFailure(
            "Deployed runtime environment does not match SHUDDHO_STAGING_EXPECTED_ENVIRONMENT."
        )
    revision = require_revision(manifest.get("source_revision"))
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        raise ProactiveReadProbeFailure("Runtime manifest capabilities are missing.")
    required = ("coworker", "personal_goals", "automations", "runtime_v3", "connector_reads")
    missing = [name for name in required if capabilities.get(name) is not True]
    if missing:
        raise ProactiveReadProbeFailure(
            "Required controlled-staging capabilities are not enabled: " + ", ".join(missing)
        )
    return {
        **rollout,
        "source_revision": revision,
        "environment": environment,
    }


def one(items: list[dict], label: str) -> dict:
    if len(items) != 1:
        raise ProactiveReadProbeFailure(
            f"Expected exactly one {label}; found {len(items)}. Pass an explicit id if the staging account has multiple candidates."
        )
    return items[0]


def select_grant(
    grants: list[dict],
    provider: str,
    capability: str,
    grant_id: str | None,
) -> dict:
    matches = [
        item
        for item in grants
        if item.get("provider") == provider
        and item.get("capability") == capability
        and item.get("state") == "active"
        and (grant_id is None or str(item.get("id")) == grant_id)
    ]
    return one(matches, f"active {provider} {capability} read grant")


def select_automation(
    automations: list[dict],
    grant_id: str,
    capability: str,
    automation_id: str | None,
) -> dict:
    expected_profile = "email" if capability == "email_read" else "meeting"
    expected_schedule = "event" if capability == "email_read" else "meeting"
    matches = []
    for item in automations:
        schedule = item.get("schedule")
        if not isinstance(schedule, dict):
            continue
        if (
            item.get("state") == "active"
            and item.get("run_profile") == expected_profile
            and schedule.get("kind") == expected_schedule
            and str(schedule.get("grant_id") or "") == grant_id
            and grant_id in [str(value) for value in item.get("connector_read_grant_ids") or []]
            and (automation_id is None or str(item.get("id")) == automation_id)
        ):
            matches.append(item)
    return one(matches, f"active {expected_profile} automation bound to grant {grant_id}")


def snapshot_signatures(items: list[dict]) -> list[str]:
    signatures = []
    for item in items:
        signatures.append(
            "|".join(
                [
                    str(item.get("id") or ""),
                    str(item.get("provider_version") or ""),
                    str(item.get("sha256") or ""),
                ]
            )
        )
    return sorted(signatures)


def ids(items: list[dict], key: str = "id") -> list[str]:
    return sorted(
        str(item.get(key))
        for item in items
        if item.get(key) is not None
    )


def load_owned_state(
    client: httpx.Client,
    token: str,
    *,
    provider: str,
    capability: str,
    grant_id: str | None,
    automation_id: str | None,
) -> dict:
    me = json_object(client.get("/api/v1/me", headers=auth(token)), "staging account")
    owner_id = str(me.get("account_id") or "")
    if not owner_id:
        raise ProactiveReadProbeFailure("Synthetic staging account did not expose an account_id.")

    grant_response = json_object(
        client.get("/api/v1/connector-read-grants", headers=auth(token)),
        "connector read grants",
    )
    if grant_response.get("enabled") is not True:
        raise ProactiveReadProbeFailure("Connected reads are not enabled in the deployed staging release.")
    grants = grant_response.get("grants")
    if not isinstance(grants, list):
        raise ProactiveReadProbeFailure("Connector read grant response has an unexpected shape.")
    grant = select_grant(grants, provider, capability, grant_id)
    selected_grant_id = str(grant["id"])

    subscription_response = json_object(
        client.get(
            f"/api/v1/connector-read-grants/{selected_grant_id}/subscription",
            headers=auth(token),
        ),
        "connector subscription",
    )
    subscription = subscription_response.get("subscription")
    if not isinstance(subscription, dict):
        raise ProactiveReadProbeFailure("The selected grant has no active provider subscription.")
    if (
        subscription.get("provider") != provider
        or subscription.get("capability") != capability
        or subscription.get("state") not in ALLOWED_SUBSCRIPTION_STATES
    ):
        raise ProactiveReadProbeFailure(
            "The selected provider subscription is not active/renewing for the requested read capability."
        )

    automation_response = json_object(
        client.get("/api/v1/automations", headers=auth(token)),
        "automations",
    )
    if automation_response.get("enabled") is not True:
        raise ProactiveReadProbeFailure("Automations are not enabled in the deployed staging release.")
    automations = automation_response.get("automations")
    if not isinstance(automations, list):
        raise ProactiveReadProbeFailure("Automation response has an unexpected shape.")
    automation = select_automation(
        automations,
        selected_grant_id,
        capability,
        automation_id,
    )
    if automation.get("quiet_hours") is not None:
        raise ProactiveReadProbeFailure(
            "Use a dedicated staging automation without quiet hours for provider-event qualification so completion evidence is observable deterministically."
        )
    selected_automation_id = str(automation["id"])

    snapshots = json_object(
        client.get(
            f"/api/v1/connector-read-grants/{selected_grant_id}/snapshots",
            headers=auth(token),
        ),
        "connector snapshots",
    ).get("snapshots")
    history = json_object(
        client.get(
            f"/api/v1/automations/{selected_automation_id}/history",
            headers=auth(token),
        ),
        "automation history",
    ).get("history")
    notifications = json_object(
        client.get("/api/v1/notifications", headers=auth(token)),
        "notifications",
    ).get("notifications")
    runs = json_object(
        client.get("/api/v1/agent-runs", headers=auth(token)),
        "agent runs",
    ).get("runs")

    if not all(isinstance(value, list) for value in (snapshots, history, notifications, runs)):
        raise ProactiveReadProbeFailure("One or more staging evidence endpoints returned an unexpected shape.")

    return {
        "owner_id": owner_id,
        "grant": grant,
        "subscription": subscription,
        "automation": automation,
        "snapshots": snapshots,
        "history": history,
        "notifications": notifications,
        "runs": runs,
    }


def baseline(value: dict) -> dict:
    return {
        "snapshot_signatures": snapshot_signatures(value["snapshots"]),
        "snapshot_ids": ids(value["snapshots"]),
        "occurrence_ids": ids(value["history"], "occurrence_id"),
        "notification_ids": ids(value["notifications"]),
        "run_ids": ids(value["runs"]),
    }


def transition_evidence(state: dict, current: dict) -> dict:
    before = state.get("baseline")
    if not isinstance(before, dict):
        raise ProactiveReadProbeFailure("Probe state baseline is missing.")

    old_snapshot_ids = set(before.get("snapshot_ids") or [])
    new_snapshot_ids = sorted(
        str(item.get("id"))
        for item in current["snapshots"]
        if item.get("id") is not None
        and (
            str(item.get("id")) not in old_snapshot_ids
            or "|".join(
                [
                    str(item.get("id") or ""),
                    str(item.get("provider_version") or ""),
                    str(item.get("sha256") or ""),
                ]
            )
            not in set(before.get("snapshot_signatures") or [])
        )
    )
    new_snapshot_signatures = sorted(
        set(snapshot_signatures(current["snapshots"]))
        - set(before.get("snapshot_signatures") or [])
    )
    new_history = [
        item
        for item in current["history"]
        if str(item.get("occurrence_id") or "") not in set(before.get("occurrence_ids") or [])
    ]
    if not new_snapshot_signatures:
        raise ProactiveReadProbeFailure(
            "No new/changed connector snapshot was observed after the real provider event."
        )
    if len(new_history) != 1:
        raise ProactiveReadProbeFailure(
            f"Expected exactly one new logical automation occurrence; found {len(new_history)}."
        )
    occurrence = new_history[0]
    expected_trigger = "event" if state["capability"] == "email_read" else "meeting"
    if occurrence.get("trigger_type") != expected_trigger:
        raise ProactiveReadProbeFailure(
            f"New automation occurrence trigger_type was {occurrence.get('trigger_type')!r}; expected {expected_trigger!r}."
        )
    trigger_event_id = str(occurrence.get("trigger_event_id") or "")
    trigger_snapshot_id = str(occurrence.get("trigger_snapshot_id") or "")
    if state["capability"] == "email_read" and not trigger_event_id:
        raise ProactiveReadProbeFailure("Email Coworker history did not expose its trigger_event_id.")
    if state["capability"] == "calendar_read":
        if not trigger_snapshot_id:
            raise ProactiveReadProbeFailure("Meeting Coworker history did not expose its trigger_snapshot_id.")
        if trigger_snapshot_id not in new_snapshot_ids:
            raise ProactiveReadProbeFailure(
                "Meeting Coworker trigger snapshot was not one of the provider snapshots changed by this exercise."
            )
    run_id = str(occurrence.get("run_id") or "")
    if not run_id:
        raise ProactiveReadProbeFailure("New automation occurrence did not bind an Agent run.")
    if occurrence.get("run_state") != "completed":
        raise ProactiveReadProbeFailure(
            f"New proactive Agent run ended in state {occurrence.get('run_state')!r}; expected 'completed'."
        )
    if run_id in set(before.get("run_ids") or []):
        raise ProactiveReadProbeFailure("New occurrence reused a pre-probe Agent run unexpectedly.")

    new_notifications = [
        item
        for item in current["notifications"]
        if str(item.get("id") or "") not in set(before.get("notification_ids") or [])
        and str(item.get("automation_id") or "") == state["automation_id"]
        and str(item.get("occurrence_id") or "") == str(occurrence.get("occurrence_id") or "")
    ]
    completion = [
        item for item in new_notifications if item.get("kind") == "automation_completed"
    ]
    if len(completion) != 1:
        raise ProactiveReadProbeFailure(
            f"Expected exactly one new delivered automation_completed notice; found {len(completion)}."
        )

    return {
        "new_snapshot_change_count": len(new_snapshot_signatures),
        "new_snapshot_ids": new_snapshot_ids,
        "occurrence_id": str(occurrence["occurrence_id"]),
        "trigger_type": str(occurrence["trigger_type"]),
        "trigger_event_id": trigger_event_id or None,
        "trigger_snapshot_id": trigger_snapshot_id or None,
        "run_id": run_id,
        "run_state": str(occurrence["run_state"]),
        "completion_notification_id": str(completion[0]["id"]),
        "new_notification_count": len(new_notifications),
    }


def prepare(args: argparse.Namespace) -> dict:
    require_guard()
    if args.provider not in ALLOWED_PROVIDERS:
        raise ProactiveReadProbeFailure("Unsupported provider.")
    if args.capability not in ALLOWED_CAPABILITIES:
        raise ProactiveReadProbeFailure("Unsupported read capability.")

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    synthetic_label = env_secret("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL").strip()
    rollout = rollout_identity(args.rollout, args.provider_policy_plan)

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = runtime_context(client, token, rollout)
        owned = load_owned_state(
            client,
            token,
            provider=args.provider,
            capability=args.capability,
            grant_id=args.grant_id,
            automation_id=args.automation_id,
        )

    state = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": "pa10_proactive_read_event",
        "release": release,
        "synthetic_account_label": synthetic_label,
        "owner_id": owned["owner_id"],
        "provider": args.provider,
        "capability": args.capability,
        "grant_id": str(owned["grant"]["id"]),
        "subscription_id": str(owned["subscription"]["id"]),
        "subscription_generation": int(owned["subscription"].get("generation") or 0),
        "automation_id": str(owned["automation"]["id"]),
        "automation_revision": int(owned["automation"]["revision"]),
        "meeting_scan_interval_minutes": (
            int((owned["automation"].get("schedule") or {}).get("scan_interval_minutes") or 0)
            if args.capability == "calendar_read"
            else 0
        ),
        "baseline": baseline(owned),
        "prepared_at": utcnow_iso(),
    }
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def verify(args: argparse.Namespace) -> dict:
    require_guard()
    try:
        state = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProactiveReadProbeFailure(
            f"Could not read proactive read-event state: {type(error).__name__}"
        ) from None
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise ProactiveReadProbeFailure("Proactive read-event state has an unexpected schema.")

    rollout = rollout_identity(args.rollout, args.provider_policy_plan)
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    minimum_timeout = 1
    if state.get("capability") == "calendar_read":
        scan_minutes = max(5, int(state.get("meeting_scan_interval_minutes") or 0))
        minimum_timeout = scan_minutes * 60 + 300
    deadline = time.monotonic() + max(minimum_timeout, args.timeout)
    last_error: ProactiveReadProbeFailure | None = None

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                release = runtime_context(client, token, rollout)
                if release != state.get("release"):
                    raise ProactiveReadProbeFailure(
                        "Deployed release identity changed between prepare and verify."
                    )
                owned = load_owned_state(
                    client,
                    token,
                    provider=str(state["provider"]),
                    capability=str(state["capability"]),
                    grant_id=str(state["grant_id"]),
                    automation_id=str(state["automation_id"]),
                )
                if owned["owner_id"] != state.get("owner_id"):
                    raise ProactiveReadProbeFailure(
                        "Synthetic staging account identity changed between prepare and verify."
                    )
                if int(owned["automation"]["revision"]) != int(state["automation_revision"]):
                    raise ProactiveReadProbeFailure(
                        "Automation revision changed during the provider-event exercise."
                    )
                if int(owned["subscription"].get("generation") or 0) < int(state["subscription_generation"]):
                    raise ProactiveReadProbeFailure(
                        "Provider subscription generation moved backwards unexpectedly."
                    )
                transition = transition_evidence(state, owned)
                run_context = json_object(
                    client.get(
                        f"/api/v1/agent-runs/{transition['run_id']}/context",
                        headers=auth(token),
                    ),
                    "agent run context",
                )
                context_items = run_context.get("items")
                if not isinstance(context_items, list):
                    raise ProactiveReadProbeFailure("Agent run context returned an unexpected shape.")
                context_snapshot_ids = sorted(
                    str((item.get("provenance") or {}).get("snapshot_id"))
                    for item in context_items
                    if isinstance(item, dict)
                    and isinstance(item.get("provenance"), dict)
                    and (item.get("provenance") or {}).get("snapshot_id")
                )
                if not set(context_snapshot_ids).intersection(transition["new_snapshot_ids"]):
                    raise ProactiveReadProbeFailure(
                        "Proactive Agent run context did not include any provider snapshot changed by this exercise."
                    )
                transition["run_context_snapshot_ids"] = context_snapshot_ids
                evidence = {
                    "schema_version": SCHEMA_VERSION,
                    "evidence_kind": "pa10_proactive_read_event",
                    "status": "passed",
                    "release": release,
                    "synthetic_account_label": state["synthetic_account_label"],
                    "owner_id": state["owner_id"],
                    "provider": state["provider"],
                    "capability": state["capability"],
                    "grant_id": state["grant_id"],
                    "subscription_id_before": state["subscription_id"],
                    "subscription_id_after": str(owned["subscription"]["id"]),
                    "subscription_generation_after": int(owned["subscription"].get("generation") or 0),
                    "automation_id": state["automation_id"],
                    "automation_revision": state["automation_revision"],
                    "prepared_at": state["prepared_at"],
                    "verified_at": utcnow_iso(),
                    **transition,
                }
                args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                return evidence
            except ProactiveReadProbeFailure as error:
                last_error = error
                time.sleep(max(1, args.poll_interval))

    raise last_error or ProactiveReadProbeFailure(
        "Provider-event evidence did not become available before timeout."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect release-bound evidence for one real controlled-staging Gmail/Outlook/Calendar "
            "read event and its existing Shuddho proactive workflow. The script never injects provider "
            "events and never receives provider credentials."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--provider", choices=sorted(ALLOWED_PROVIDERS), required=True)
    prepare_parser.add_argument("--capability", choices=sorted(ALLOWED_CAPABILITIES), required=True)
    prepare_parser.add_argument("--grant-id")
    prepare_parser.add_argument("--automation-id")
    prepare_parser.add_argument("--rollout", type=Path, required=True)
    prepare_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--rollout", type=Path, required=True)
    verify_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--timeout", type=int, default=180)
    verify_parser.add_argument("--poll-interval", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        result = prepare(args) if args.command == "prepare" else verify(args)
    except (httpx.HTTPError, ProactiveReadProbeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    if args.command == "prepare":
        print(
            json.dumps(
                {
                    "status": "prepared",
                    "state": str(args.state),
                    "provider": result["provider"],
                    "capability": result["capability"],
                    "release": result["release"],
                    "next": (
                        "Perform exactly one approved real provider change using the dedicated synthetic account, "
                        "then run verify. Do not replay or inject the provider webhook manually."
                    ),
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "output": str(args.output),
                    "provider": result["provider"],
                    "capability": result["capability"],
                    "occurrence_id": result["occurrence_id"],
                    "run_id": result["run_id"],
                    "completion_notification_id": result["completion_notification_id"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
