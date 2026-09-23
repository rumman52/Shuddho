from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_repository import digest
from services.coworker.action_schemas import address
from services.coworker.config import Settings


TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}


class ReminderValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_REMINDERS", "").lower() != "true":
        raise ReminderValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_ACTION_REMINDERS=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise ReminderValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise ReminderValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ReminderValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def connection_for(connections: list[dict], provider: str) -> dict:
    matches = [
        item for item in connections
        if isinstance(item, dict)
        and item.get("provider") == provider
        and item.get("capability") == "calendar"
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise ReminderValidationFailure(
            f"Expected exactly one active {provider} calendar staging connection; found {len(matches)}."
        )
    return matches[0]


def wrong_hash(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ReminderValidationFailure("Prepared preview hash is invalid.")
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_prepared(
    action: dict,
    provider: str,
    connection_id: str,
    payload: dict,
) -> None:
    if action.get("state") != "awaiting_approval" or action.get("approved_at") is not None:
        raise ReminderValidationFailure("Reminder action was not waiting for explicit approval.")
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str):
        raise ReminderValidationFailure("Prepared reminder action has no immutable preview.")
    if digest(preview) != preview_hash:
        raise ReminderValidationFailure("Reminder preview hash does not match its preview.")
    if preview.get("version") != 2 or preview.get("provider") != provider:
        raise ReminderValidationFailure("Reminder preview has the wrong version or provider.")
    if preview.get("payload") != payload:
        raise ReminderValidationFailure("Reminder preview changed the approved payload.")
    if preview.get("reminders") != "single_explicit":
        raise ReminderValidationFailure("Reminder preview does not carry the explicit-reminder policy.")
    scope = preview.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("contract_version") != 1
        or scope.get("provider") != provider
        or scope.get("connection_id") != connection_id
        or scope.get("policy", {}).get("reminders") != "single_explicit"
        or not isinstance(scope.get("payload_sha256"), str)
        or len(scope["payload_sha256"]) != 64
    ):
        raise ReminderValidationFailure("Reminder approval scope is incomplete or changed.")


def prove_no_auto_approval(client: httpx.Client, token: str, action: dict) -> None:
    time.sleep(2)
    action_id = str(action["id"])
    current = request_json(
        client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
        "read unapproved reminder action",
    )
    if current.get("state") != "awaiting_approval" or current.get("approved_at") is not None:
        raise ReminderValidationFailure("Reminder action changed before explicit approval.")
    rejected = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=auth(token),
        json={"preview_hash": wrong_hash(str(action["preview_hash"]))},
    )
    if rejected.status_code != 409:
        raise ReminderValidationFailure(
            f"Wrong-hash reminder approval returned HTTP {rejected.status_code}; expected 409."
        )
    after = request_json(
        client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
        "read reminder action after rejected approval",
    )
    if after.get("state") != "awaiting_approval" or after.get("approved_at") is not None:
        raise ReminderValidationFailure("Rejected reminder approval changed action state.")


def wait_terminal(
    client: httpx.Client,
    token: str,
    action_id: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
            "reminder action status",
        )
        if value.get("state") in TERMINAL:
            if value.get("state") != "succeeded":
                raise ReminderValidationFailure(
                    f"Reminder action ended in state {value.get('state')!r}, not succeeded."
                )
            return value
        time.sleep(2)
    raise ReminderValidationFailure("Approved reminder action did not finish before timeout.")


def validate_completion(action: dict, prepared: dict, provider: str) -> None:
    if action.get("preview") != prepared.get("preview") or action.get("preview_hash") != prepared.get("preview_hash"):
        raise ReminderValidationFailure("Approved reminder preview mutated during execution.")
    audit = [item.get("action") for item in action.get("audit", []) if isinstance(item, dict)]
    for name in ("action.prepared", "action.approved", "action.execution_started", "action.succeeded"):
        if audit.count(name) != 1:
            raise ReminderValidationFailure(f"Reminder audit expected exactly one {name}.")
    receipt = action.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("provider") != provider
        or receipt.get("status") != "event_created"
        or not isinstance(receipt.get("provider_id"), str)
        or not receipt["provider_id"]
    ):
        raise ReminderValidationFailure("Reminder provider receipt is missing or unexpected.")
    try:
        datetime.fromisoformat(str(receipt["confirmed_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise ReminderValidationFailure("Reminder receipt timestamp is invalid.") from None


def merge_evidence(base_evidence: Path | None, update: dict) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ReminderValidationFailure("Base staging evidence must be a JSON object.")
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate one live, explicitly approved calendar reminder in controlled staging."
    )
    parser.add_argument("--provider", choices=("google", "microsoft"), default="google")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled or not settings.action_reminders_enabled:
        raise SystemExit("SHUDDHO_ACTIONS_ENABLED and SHUDDHO_ACTION_REMINDERS_ENABLED must be true.")
    if args.provider == "microsoft" and not settings.microsoft_actions_enabled:
        raise SystemExit("SHUDDHO_MICROSOFT_ACTIONS_ENABLED must be true for Microsoft validation.")

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    recipient_name = (
        "SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT"
        if args.provider == "google"
        else "SHUDDHO_STAGING_MICROSOFT_TEST_RECIPIENT"
    )
    try:
        attendee = address(env_secret(recipient_name))
    except ValueError as error:
        raise SystemExit(f"Invalid {recipient_name}: {error}") from None

    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            connections_value = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list staging connections",
            )
            if connections_value.get("reminders_enabled") is not True:
                raise ReminderValidationFailure("Deployed reminder capability is not enabled.")
            connection = connection_for(connections_value.get("connections", []), args.provider)
            marker = uuid.uuid4().hex[:10]
            start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
            payload = {
                "kind": "calendar_create_with_reminder",
                "title": f"Shuddho reminder staging test {marker}",
                "description": "Synthetic controlled-staging event. No customer data.",
                "location": "Controlled staging",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(minutes=30)).isoformat(),
                "time_zone": "UTC",
                "attendees": [attendee],
                "reminder_minutes_before_start": 15,
            }
            prepared = request_json(
                client.post(
                    "/api/v1/actions",
                    headers=auth(token) | {"Idempotency-Key": "live-reminder-" + uuid.uuid4().hex},
                    json={
                        "connection_id": connection["id"],
                        "attachment_ids": [],
                        "payload": payload,
                    },
                ),
                "prepare reminder action",
                expected=201,
            )
            validate_prepared(prepared, args.provider, str(connection["id"]), payload)
            prove_no_auto_approval(client, token, prepared)
            approved = request_json(
                client.post(
                    f"/api/v1/actions/{prepared['id']}/approve",
                    headers=auth(token),
                    json={"preview_hash": prepared["preview_hash"]},
                ),
                "approve exact reminder action",
                expected=202,
            )
            if approved.get("preview_hash") != prepared["preview_hash"]:
                raise ReminderValidationFailure("Exact approval returned a different preview hash.")
            completed = wait_terminal(client, token, str(prepared["id"]), args.timeout)
            validate_completion(completed, prepared, args.provider)

        key = f"action_reminders_{args.provider}"
        evidence = merge_evidence(
            args.base_evidence,
            {
                key: passed(
                    f"live {args.provider} calendar reminder passed exact 15-minute payload binding, "
                    "wrong-hash rejection, explicit approval, single execution audit and exact provider receipt validation"
                )
            },
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": "passed",
            "provider": args.provider,
            "action_id": completed["id"],
            "cleanup": "Delete the synthetic staging event after retaining approved evidence.",
        }, indent=2))
    except (ReminderValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
