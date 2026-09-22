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


TERMINAL = {
    "succeeded",
    "failed",
    "cancelled",
    "expired",
    "outcome_unknown",
}


class MicrosoftActionValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_guard() -> None:
    if (
        os.environ.get(
            "SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS",
            "",
        ).lower()
        != "true"
    ):
        raise MicrosoftActionValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS=true "
            "only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(
    response: httpx.Response,
    label: str,
    expected: int = 200,
) -> dict:
    if response.status_code != expected:
        raise MicrosoftActionValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise MicrosoftActionValidationFailure(
            f"{label} did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise MicrosoftActionValidationFailure(
            f"{label} returned an unexpected JSON shape."
        )
    return value


def connection_for(connections: list[dict], capability: str) -> dict:
    matches = [
        item
        for item in connections
        if isinstance(item, dict)
        and item.get("provider") == "microsoft"
        and item.get("capability") == capability
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise MicrosoftActionValidationFailure(
            "Expected exactly one active Microsoft "
            f"{capability} staging connection; found {len(matches)}."
        )
    value = matches[0]
    if (
        not isinstance(value.get("id"), str)
        or not isinstance(value.get("email"), str)
    ):
        raise MicrosoftActionValidationFailure(
            f"Microsoft {capability} connection metadata is incomplete."
        )
    return value


def wrong_hash(value: str) -> str:
    if (
        len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise MicrosoftActionValidationFailure(
            "Prepared action preview hash is invalid."
        )
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
            headers=auth(token)
            | {
                "Idempotency-Key":
                key_prefix + "-" + uuid.uuid4().hex
            },
            json={
                "connection_id": connection_id,
                "payload": payload,
            },
        ),
        "prepare Microsoft action",
        expected=201,
    )
    if action.get("state") != "awaiting_approval":
        raise MicrosoftActionValidationFailure(
            "A newly prepared Microsoft action was not awaiting approval."
        )
    if (
        action.get("approved_at") is not None
        or action.get("receipt") is not None
    ):
        raise MicrosoftActionValidationFailure(
            "A newly prepared Microsoft action already had approval/receipt data."
        )
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if (
        not isinstance(preview, dict)
        or not isinstance(preview_hash, str)
    ):
        raise MicrosoftActionValidationFailure(
            "Prepared Microsoft action is missing immutable preview data."
        )
    if digest(preview) != preview_hash:
        raise MicrosoftActionValidationFailure(
            "Prepared Microsoft preview hash does not match the preview."
        )
    if preview.get("version") != 2:
        raise MicrosoftActionValidationFailure(
            "Microsoft staging requires v2 approval-scope previews."
        )
    if preview.get("provider") != "microsoft":
        raise MicrosoftActionValidationFailure(
            "Prepared action is not bound to Microsoft."
        )
    if preview.get("payload") != payload:
        raise MicrosoftActionValidationFailure(
            "Prepared Microsoft preview payload differs from submitted payload."
        )
    scope = preview.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("provider") != "microsoft"
        or scope.get("connection_id") != connection_id
        or scope.get("payload_sha256") is None
    ):
        raise MicrosoftActionValidationFailure(
            "Prepared action is missing its Microsoft approval scope."
        )
    return action


def prove_no_auto_approval(
    client: httpx.Client,
    token: str,
    action: dict,
) -> None:
    action_id = str(action["id"])
    preview_hash = str(action["preview_hash"])
    time.sleep(2)
    current = request_json(
        client.get(
            f"/api/v1/actions/{action_id}",
            headers=auth(token),
        ),
        "read unapproved Microsoft action",
    )
    if (
        current.get("state") != "awaiting_approval"
        or current.get("approved_at") is not None
    ):
        raise MicrosoftActionValidationFailure(
            "Microsoft action changed state before explicit approval."
        )

    rejected = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=auth(token),
        json={"preview_hash": wrong_hash(preview_hash)},
    )
    if rejected.status_code != 409:
        raise MicrosoftActionValidationFailure(
            "Microsoft approval with the wrong preview hash returned "
            f"HTTP {rejected.status_code}; expected 409."
        )
    after = request_json(
        client.get(
            f"/api/v1/actions/{action_id}",
            headers=auth(token),
        ),
        "read Microsoft action after rejected approval",
    )
    if (
        after.get("state") != "awaiting_approval"
        or after.get("approved_at") is not None
    ):
        raise MicrosoftActionValidationFailure(
            "Rejected Microsoft approval changed action state."
        )
    audit = [
        item.get("action")
        for item in after.get("audit", [])
        if isinstance(item, dict)
    ]
    if (
        "action.approved" in audit
        or "action.execution_started" in audit
    ):
        raise MicrosoftActionValidationFailure(
            "Microsoft action audit shows execution before exact approval."
        )


def approve_exact(
    client: httpx.Client,
    token: str,
    action: dict,
) -> dict:
    value = request_json(
        client.post(
            f"/api/v1/actions/{action['id']}/approve",
            headers=auth(token),
            json={"preview_hash": action["preview_hash"]},
        ),
        "approve exact Microsoft action",
        expected=202,
    )
    if value.get("approved_at") is None:
        raise MicrosoftActionValidationFailure(
            "Exact Microsoft approval did not record an approval timestamp."
        )
    if (
        value.get("preview_hash") != action["preview_hash"]
        or value.get("preview") != action["preview"]
    ):
        raise MicrosoftActionValidationFailure(
            "Microsoft preview changed during approval."
        )
    if value.get("state") not in {
        "queued",
        "executing",
        "succeeded",
    }:
        raise MicrosoftActionValidationFailure(
            "Exact Microsoft approval entered unexpected state "
            f"{value.get('state')!r}."
        )
    return value


def wait_terminal(
    client: httpx.Client,
    token: str,
    action_id: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    value: dict = {}
    while time.monotonic() < deadline:
        value = request_json(
            client.get(
                f"/api/v1/actions/{action_id}",
                headers=auth(token),
            ),
            "Microsoft action status",
        )
        if value.get("state") in TERMINAL:
            break
        time.sleep(2)
    else:
        raise MicrosoftActionValidationFailure(
            "Approved Microsoft action did not reach a terminal state."
        )
    if value.get("state") != "succeeded":
        raise MicrosoftActionValidationFailure(
            "Approved Microsoft action ended in state "
            f"{value.get('state')!r}, not succeeded."
        )
    return value


def validate_audit(action: dict) -> None:
    audit = [
        item.get("action")
        for item in action.get("audit", [])
        if isinstance(item, dict)
    ]
    for item in (
        "action.prepared",
        "action.approved",
        "action.execution_started",
        "action.succeeded",
    ):
        if audit.count(item) != 1:
            raise MicrosoftActionValidationFailure(
                f"Microsoft action audit expected exactly one {item}; "
                f"found {audit.count(item)}."
            )


def validate_email_receipt(action: dict) -> None:
    receipt = action.get("receipt")
    if not isinstance(receipt, dict):
        raise MicrosoftActionValidationFailure(
            "Microsoft email action did not return a provider receipt."
        )
    if (
        receipt.get("provider") != "microsoft"
        or receipt.get("status") != "accepted_by_microsoft_graph"
    ):
        raise MicrosoftActionValidationFailure(
            "Microsoft email receipt has unexpected provider/status."
        )
    try:
        datetime.fromisoformat(
            str(receipt["confirmed_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        raise MicrosoftActionValidationFailure(
            "Microsoft email receipt confirmation timestamp is invalid."
        ) from None


def validate_calendar_receipt(action: dict) -> None:
    receipt = action.get("receipt")
    if not isinstance(receipt, dict):
        raise MicrosoftActionValidationFailure(
            "Microsoft calendar action did not return a provider receipt."
        )
    if (
        receipt.get("provider") != "microsoft"
        or receipt.get("status") != "event_created"
        or receipt.get("calendar") != "primary"
    ):
        raise MicrosoftActionValidationFailure(
            "Microsoft calendar receipt has unexpected provider/status/calendar."
        )
    provider_id = receipt.get("provider_id")
    transaction_id = receipt.get("transaction_id")
    if not isinstance(provider_id, str) or not provider_id:
        raise MicrosoftActionValidationFailure(
            "Microsoft calendar receipt is missing provider id."
        )
    if (
        not isinstance(transaction_id, str)
        or not transaction_id.startswith("shuddho-")
    ):
        raise MicrosoftActionValidationFailure(
            "Microsoft calendar receipt is missing Shuddho transaction binding."
        )
    try:
        datetime.fromisoformat(
            str(receipt["confirmed_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        raise MicrosoftActionValidationFailure(
            "Microsoft calendar receipt confirmation timestamp is invalid."
        ) from None


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
    completed = wait_terminal(
        client,
        token,
        str(prepared["id"]),
        timeout_seconds,
    )
    if (
        completed.get("preview_hash") != prepared["preview_hash"]
        or completed.get("preview") != prepared["preview"]
    ):
        raise MicrosoftActionValidationFailure(
            "Approved Microsoft preview mutated before provider completion."
        )
    validate_audit(completed)
    receipt_validator(completed)
    return {
        "action_id": completed["id"],
        "kind": completed["kind"],
        "provider_status": completed["receipt"]["status"],
    }


def merge_evidence(
    base_evidence: Path | None,
    update: dict,
) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(
            base_evidence.read_text(encoding="utf-8")
        )
        if not isinstance(value, dict):
            raise MicrosoftActionValidationFailure(
                "Base staging evidence must be a JSON object."
            )
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate live Microsoft Graph approved email/calendar "
            "actions in controlled Shuddho staging."
        )
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled:
        raise SystemExit(
            "SHUDDHO_ACTIONS_ENABLED must be true in controlled staging."
        )
    if not settings.microsoft_actions_enabled:
        raise SystemExit(
            "SHUDDHO_MICROSOFT_ACTIONS_ENABLED must be true in controlled staging."
        )

    base_url = require_https_base(
        env_secret("SHUDDHO_STAGING_API_BASE_URL")
    )
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        recipient = address(
            env_secret("SHUDDHO_STAGING_MICROSOFT_TEST_RECIPIENT")
        )
    except ValueError as error:
        raise SystemExit(
            "Invalid SHUDDHO_STAGING_MICROSOFT_TEST_RECIPIENT: "
            f"{error}"
        ) from None

    marker = uuid.uuid4().hex[:10]
    start = datetime.now(timezone.utc) + timedelta(minutes=15)
    end = start + timedelta(minutes=30)

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=20,
            follow_redirects=False,
        ) as client:
            connections_value = request_json(
                client.get(
                    "/api/v1/connections",
                    headers=auth(token),
                ),
                "list Microsoft staging connections",
            )
            if connections_value.get("enabled") is not True:
                raise MicrosoftActionValidationFailure(
                    "Deployed action capability is not enabled."
                )
            connections = connections_value.get("connections")
            if not isinstance(connections, list):
                raise MicrosoftActionValidationFailure(
                    "Connection list has an unexpected shape."
                )
            email_connection = connection_for(
                connections,
                "email",
            )
            calendar_connection = connection_for(
                connections,
                "calendar",
            )

            sender = address(str(email_connection["email"]))
            if sender.casefold() == recipient.casefold():
                raise MicrosoftActionValidationFailure(
                    "Use a separate authorized test recipient."
                )

            email_payload = {
                "kind": "email_send",
                "to": [sender],
                "cc": [],
                "bcc": [recipient],
                "subject": (
                    f"Shuddho Microsoft staging test {marker} — বাংলা"
                ),
                "body": (
                    "Synthetic Shuddho Microsoft staging email.\n"
                    "This verifies exact approval, Unicode content, "
                    "single execution, and provider receipt capture."
                ),
            }
            email_result = run_action(
                client,
                token,
                email_connection,
                email_payload,
                "live-microsoft-email",
                args.timeout,
                validate_email_receipt,
            )

            calendar_payload = {
                "kind": "calendar_create",
                "title": (
                    f"Shuddho Microsoft staging test {marker}"
                ),
                "description": (
                    "Synthetic Shuddho Microsoft staging calendar event. "
                    "Safe to delete after validation."
                ),
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
                "live-microsoft-calendar",
                args.timeout,
                validate_calendar_receipt,
            )

        evidence = merge_evidence(
            args.base_evidence,
            {
                "microsoft_actions": passed(
                    "live Microsoft Graph email + calendar actions passed "
                    "provider-bound v2 approval scope, no-auto-approval, "
                    "wrong-hash rejection, immutable preview, single execution "
                    "audit, and Microsoft receipt validation"
                )
            },
        )
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "written": str(args.output),
            "checks": {"microsoft_actions": "passed"},
            "email": email_result,
            "calendar": calendar_result,
            "cleanup": (
                "Delete the synthetic Microsoft calendar event and staging "
                "email after retaining provider receipt evidence."
            ),
        }, indent=2))
    except (
        MicrosoftActionValidationFailure,
        httpx.HTTPError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps({
            "status": "failed",
            "error": str(error),
        }, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
