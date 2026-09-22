from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_schemas import address
from services.coworker.action_repository import digest
from services.coworker.config import Settings


TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}


class GoogleActionValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS", "").lower() != "true":
        raise GoogleActionValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise GoogleActionValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise GoogleActionValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise GoogleActionValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def connection_for(connections: list[dict], capability: str) -> dict:
    matches = [
        item for item in connections
        if isinstance(item, dict)
        and item.get("provider") == "google"
        and item.get("capability") == capability
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise GoogleActionValidationFailure(
            f"Expected exactly one active Google {capability} staging connection; found {len(matches)}."
        )
    value = matches[0]
    if not isinstance(value.get("id"), str) or not isinstance(value.get("email"), str):
        raise GoogleActionValidationFailure(f"Google {capability} connection metadata is incomplete.")
    return value


def wrong_hash(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise GoogleActionValidationFailure("Prepared action preview hash is invalid.")
    first = "0" if value[0] != "0" else "1"
    return first + value[1:]


def prepare_action(
    client: httpx.Client,
    token: str,
    connection_id: str,
    payload: dict,
    key_prefix: str,
) -> dict:
    action = request_json(
        client.post(
            "/api/v1/actions",
            headers=auth(token) | {"Idempotency-Key": key_prefix + "-" + uuid.uuid4().hex},
            json={"connection_id": connection_id, "payload": payload},
        ),
        "prepare Google action",
        expected=201,
    )
    if action.get("state") != "awaiting_approval":
        raise GoogleActionValidationFailure("A newly prepared action was not awaiting explicit approval.")
    if action.get("approved_at") is not None or action.get("receipt") is not None:
        raise GoogleActionValidationFailure("A newly prepared action already contained approval or receipt data.")
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str):
        raise GoogleActionValidationFailure("Prepared action is missing immutable preview data.")
    if digest(preview) != preview_hash:
        raise GoogleActionValidationFailure("Prepared action preview hash does not match the returned preview.")
    if preview.get("payload") != payload:
        raise GoogleActionValidationFailure("Prepared action preview payload differs from the submitted synthetic payload.")
    return action


def prove_no_auto_approval(client: httpx.Client, token: str, action: dict) -> None:
    action_id = str(action["id"])
    preview_hash = str(action["preview_hash"])
    time.sleep(2)
    current = request_json(
        client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
        "read unapproved action",
    )
    if current.get("state") != "awaiting_approval" or current.get("approved_at") is not None:
        raise GoogleActionValidationFailure("Action changed state before explicit approval.")

    rejected = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=auth(token),
        json={"preview_hash": wrong_hash(preview_hash)},
    )
    if rejected.status_code != 409:
        raise GoogleActionValidationFailure(
            f"Approval with a wrong preview hash returned HTTP {rejected.status_code}; expected 409."
        )
    after = request_json(
        client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
        "read action after rejected approval",
    )
    if after.get("state") != "awaiting_approval" or after.get("approved_at") is not None:
        raise GoogleActionValidationFailure("Rejected approval changed the action state.")
    audit = [item.get("action") for item in after.get("audit", []) if isinstance(item, dict)]
    if "action.approved" in audit or "action.execution_started" in audit:
        raise GoogleActionValidationFailure("Audit history shows approval/execution before exact user approval.")


def approve_exact(client: httpx.Client, token: str, action: dict) -> dict:
    value = request_json(
        client.post(
            f"/api/v1/actions/{action['id']}/approve",
            headers=auth(token),
            json={"preview_hash": action["preview_hash"]},
        ),
        "approve exact Google action",
        expected=202,
    )
    if value.get("approved_at") is None:
        raise GoogleActionValidationFailure("Exact approval did not record an approval timestamp.")
    if value.get("preview_hash") != action["preview_hash"] or value.get("preview") != action["preview"]:
        raise GoogleActionValidationFailure("Preview changed during approval.")
    if value.get("state") not in {"queued", "executing", "succeeded"}:
        raise GoogleActionValidationFailure(
            f"Exact approval entered unexpected state {value.get('state')!r}."
        )
    return value


def wait_terminal(
    client: httpx.Client,
    token: str,
    action_id: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    value = {}
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
            "Google action status",
        )
        if value.get("state") in TERMINAL:
            break
        time.sleep(2)
    else:
        raise GoogleActionValidationFailure("Approved Google action did not reach a terminal state before timeout.")
    if value.get("state") != "succeeded":
        raise GoogleActionValidationFailure(
            f"Approved Google action ended in state {value.get('state')!r}, not succeeded."
        )
    return value


def validate_audit(action: dict) -> None:
    audit = [item.get("action") for item in action.get("audit", []) if isinstance(item, dict)]
    required_once = (
        "action.prepared",
        "action.approved",
        "action.execution_started",
        "action.succeeded",
    )
    for item in required_once:
        if audit.count(item) != 1:
            raise GoogleActionValidationFailure(
                f"Google action audit expected exactly one {item}; found {audit.count(item)}."
            )


def validate_email_receipt(action: dict) -> None:
    receipt = action.get("receipt")
    if not isinstance(receipt, dict):
        raise GoogleActionValidationFailure("Gmail action did not return a provider receipt.")
    if receipt.get("provider") != "google" or receipt.get("status") != "accepted_by_gmail":
        raise GoogleActionValidationFailure("Gmail provider receipt has unexpected provider/status.")
    provider_id = receipt.get("provider_id")
    if not isinstance(provider_id, str) or not provider_id:
        raise GoogleActionValidationFailure("Gmail provider receipt is missing a provider id.")
    if receipt.get("message_id") != f"<{action['id']}@shuddho.invalid>":
        raise GoogleActionValidationFailure("Gmail receipt message id does not match the approved action id.")
    try:
        datetime.fromisoformat(str(receipt["confirmed_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise GoogleActionValidationFailure("Gmail receipt confirmation timestamp is invalid.") from None


def validate_calendar_receipt(action: dict) -> None:
    receipt = action.get("receipt")
    if not isinstance(receipt, dict):
        raise GoogleActionValidationFailure("Calendar action did not return a provider receipt.")
    if (
        receipt.get("provider") != "google"
        or receipt.get("status") != "event_created"
        or receipt.get("calendar") != "primary"
    ):
        raise GoogleActionValidationFailure("Calendar provider receipt has unexpected provider/status/calendar.")
    expected_provider_id = "shuddho" + str(action["id"]).replace("-", "")
    if receipt.get("provider_id") != expected_provider_id:
        raise GoogleActionValidationFailure("Calendar provider id is not the stable Shuddho event id.")
    try:
        datetime.fromisoformat(str(receipt["confirmed_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise GoogleActionValidationFailure("Calendar receipt confirmation timestamp is invalid.") from None


def run_action(
    client: httpx.Client,
    token: str,
    connection: dict,
    payload: dict,
    key_prefix: str,
    timeout_seconds: int,
    receipt_validator,
) -> dict:
    prepared = prepare_action(
        client,
        token,
        str(connection["id"]),
        payload,
        key_prefix,
    )
    prove_no_auto_approval(client, token, prepared)
    approve_exact(client, token, prepared)
    completed = wait_terminal(client, token, str(prepared["id"]), timeout_seconds)
    if completed.get("preview_hash") != prepared["preview_hash"] or completed.get("preview") != prepared["preview"]:
        raise GoogleActionValidationFailure("Approved preview mutated before provider completion.")
    validate_audit(completed)
    receipt_validator(completed)
    return {
        "action_id": completed["id"],
        "kind": completed["kind"],
        "provider_status": completed["receipt"]["status"],
    }


def merge_evidence(base_evidence: Path | None, update: dict) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise GoogleActionValidationFailure("Base staging evidence must be a JSON object.")
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate live Google approved email/calendar actions in controlled Shuddho staging."
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled:
        raise SystemExit("SHUDDHO_ACTIONS_ENABLED must be true in controlled staging.")
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        recipient = address(env_secret("SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT"))
    except ValueError as error:
        raise SystemExit(f"Invalid SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT: {error}") from None

    marker = uuid.uuid4().hex[:10]
    start = datetime.now(timezone.utc) + timedelta(minutes=15)
    end = start + timedelta(minutes=30)

    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            connections_value = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list Google staging connections",
            )
            if connections_value.get("enabled") is not True:
                raise GoogleActionValidationFailure("Deployed action capability is not enabled.")
            connections = connections_value.get("connections")
            if not isinstance(connections, list):
                raise GoogleActionValidationFailure("Connection list has an unexpected shape.")
            email_connection = connection_for(connections, "email")
            calendar_connection = connection_for(connections, "calendar")

            sender = address(str(email_connection["email"]))
            if sender.casefold() == recipient.casefold():
                raise GoogleActionValidationFailure(
                    "Use a separate authorized test recipient so Bcc behavior is exercised without duplicate recipients."
                )

            email_payload = {
                "kind": "email_send",
                "to": [sender],
                "cc": [],
                "bcc": [recipient],
                "subject": f"Shuddho staging approval test {marker} — বাংলা",
                "body": (
                    "Synthetic Shuddho staging email.\n"
                    "This message verifies exact approval, Bcc, Unicode content, one provider mutation, and receipt capture."
                ),
            }
            email_result = run_action(
                client,
                token,
                email_connection,
                email_payload,
                "live-google-email",
                args.timeout,
                validate_email_receipt,
            )

            calendar_payload = {
                "kind": "calendar_create",
                "title": f"Shuddho staging approval test {marker}",
                "description": "Synthetic Shuddho staging calendar event. Safe to delete after validation.",
                "location": "Controlled staging",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
                "time_zone": "UTC",
                "attendees": [recipient],
            }
            calendar_result = run_action(
                client,
                token,
                calendar_connection,
                calendar_payload,
                "live-google-calendar",
                args.timeout,
                validate_calendar_receipt,
            )

        evidence = merge_evidence(
            args.base_evidence,
            {
                "actions": passed(
                    "live Google Gmail + primary Calendar actions passed exact-preview approval, no-auto-approval, single execution audit and confirmed provider receipt validation"
                )
            },
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "checks": {"actions": "passed"},
            "email": email_result,
            "calendar": calendar_result,
            "cleanup": "Delete the synthetic calendar event and staging email manually after retaining provider receipt evidence.",
        }, indent=2))
    except (GoogleActionValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
