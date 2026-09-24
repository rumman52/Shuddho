from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_schemas import address
from services.coworker.config import Settings


TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}


class EmailThreadingValidationFailure(RuntimeError):
    pass


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_EMAIL_THREADING", "").lower() != "true":
        raise EmailThreadingValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_EMAIL_THREADING=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise EmailThreadingValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise EmailThreadingValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise EmailThreadingValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def connection_for(connections: list[dict]) -> dict:
    matches = [
        item for item in connections
        if isinstance(item, dict)
        and item.get("provider") == "google"
        and item.get("capability") == "email"
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise EmailThreadingValidationFailure(
            f"Expected exactly one active Google email staging connection; found {len(matches)}."
        )
    return matches[0]


def wrong_hash(value: str) -> str:
    if len(value) != 64:
        raise EmailThreadingValidationFailure("Prepared preview hash is invalid.")
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_prepared_parent(action: dict, recipient: str, subject: str, body: str) -> None:
    if action.get("state") != "awaiting_approval" or action.get("approved_at") is not None or action.get("receipt") is not None:
        raise EmailThreadingValidationFailure("Prepared parent email is not a clean approval preview.")
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str) or digest(preview) != preview_hash:
        raise EmailThreadingValidationFailure("Prepared parent preview hash does not match.")
    if preview.get("payload") != {
        "kind": "email_send",
        "to": [recipient],
        "cc": [],
        "bcc": [],
        "subject": subject,
        "body": body,
    }:
        raise EmailThreadingValidationFailure("Prepared parent email differs from the submitted message.")


def validate_prepared_reply(action: dict, parent: dict, body: str) -> None:
    if action.get("state") != "awaiting_approval" or action.get("approved_at") is not None or action.get("receipt") is not None:
        raise EmailThreadingValidationFailure("Prepared thread reply is not a clean approval preview.")
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str) or digest(preview) != preview_hash:
        raise EmailThreadingValidationFailure("Prepared reply preview hash does not match.")
    parent_payload = parent["preview"]["payload"]
    if preview.get("payload") != {
        "kind": "email_thread_reply",
        "parent_action_id": parent["id"],
        "to": parent_payload["to"],
        "cc": parent_payload["cc"],
        "bcc": [],
        "subject": parent_payload["subject"],
        "body": body,
    }:
        raise EmailThreadingValidationFailure("Prepared reply widened or changed the approved parent envelope.")
    threading = preview.get("threading")
    if threading != {
        "source": "owned_confirmed_shuddho_email",
        "provider": "google",
        "recipients": "same_to_cc",
        "bcc": "forbidden",
        "subject": "unchanged",
        "mailbox_read": "none",
    }:
        raise EmailThreadingValidationFailure("Prepared reply policy does not prove the send-only owned-thread boundary.")
    context = preview.get("reply_context")
    receipt = parent.get("receipt")
    if (
        not isinstance(context, dict)
        or not isinstance(receipt, dict)
        or context.get("parent_action_id") != parent["id"]
        or context.get("root_action_id") != parent["id"]
        or context.get("thread_id") != receipt.get("thread_id")
        or context.get("parent_message_id") != receipt.get("message_id")
        or context.get("parent_provider_id") != receipt.get("provider_id")
        or context.get("references") != [receipt.get("message_id")]
    ):
        raise EmailThreadingValidationFailure("Prepared reply context is not exactly bound to the confirmed Shuddho parent.")


def wait_terminal(client: httpx.Client, token: str, action_id: str, timeout_seconds: int, label: str) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        value = request_json(client.get(f"/api/v1/actions/{action_id}", headers=auth(token)), label)
        if value.get("state") in TERMINAL:
            if value.get("state") != "succeeded":
                raise EmailThreadingValidationFailure(
                    f"{label} ended in {value.get('state')!r}; expected succeeded."
                )
            return value
        time.sleep(2)
    raise EmailThreadingValidationFailure(f"{label} did not finish before timeout.")


def validate_completion(action: dict, prepared: dict, *, expected_thread_id: str | None = None) -> None:
    if action.get("preview_hash") != prepared.get("preview_hash") or action.get("preview") != prepared.get("preview"):
        raise EmailThreadingValidationFailure("Approved preview mutated before Gmail completion.")
    audit = [item.get("action") for item in action.get("audit", []) if isinstance(item, dict)]
    for name in ("action.prepared", "action.approved", "action.execution_started", "action.succeeded"):
        if audit.count(name) != 1:
            raise EmailThreadingValidationFailure(f"Expected exactly one {name}; found {audit.count(name)}.")
    receipt = action.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("provider") != "google"
        or receipt.get("status") != "accepted_by_gmail"
        or not isinstance(receipt.get("provider_id"), str)
        or not receipt["provider_id"]
        or not isinstance(receipt.get("thread_id"), str)
        or not receipt["thread_id"]
        or receipt.get("message_id") != f"<{action['id']}@shuddho.invalid>"
    ):
        raise EmailThreadingValidationFailure("Gmail receipt is missing the provider-bound message/thread identity.")
    if expected_thread_id is not None and receipt["thread_id"] != expected_thread_id:
        raise EmailThreadingValidationFailure("Gmail reply escaped the approved parent thread.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate approval-bound Gmail owned-thread follow-ups in controlled staging.")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled or not settings.action_email_threading_enabled:
        raise SystemExit("Actions and email threading must both be enabled in controlled staging.")
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        recipient = address(env_secret("SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT"))
    except ValueError as error:
        raise SystemExit(f"Invalid staging recipient: {error}") from None

    subject = "Shuddho controlled threading " + uuid.uuid4().hex[:12]
    parent_body = "Synthetic controlled-staging parent message."
    reply_body = "Synthetic controlled-staging follow-up."
    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            listed = request_json(client.get("/api/v1/connections", headers=auth(token)), "list staging connections")
            if listed.get("threading_enabled") is not True:
                raise EmailThreadingValidationFailure("Deployed email threading is not enabled.")
            connections = listed.get("connections")
            if not isinstance(connections, list):
                raise EmailThreadingValidationFailure("Connection list has an unexpected shape.")
            connection = connection_for(connections)

            parent_prepared = request_json(client.post(
                "/api/v1/actions",
                headers=auth(token) | {"Idempotency-Key": "live-thread-parent-" + uuid.uuid4().hex},
                json={"connection_id": connection["id"], "payload": {
                    "kind": "email_send", "to": [recipient], "cc": [], "bcc": [],
                    "subject": subject, "body": parent_body,
                }},
            ), "prepare Gmail parent", expected=201)
            validate_prepared_parent(parent_prepared, recipient, subject, parent_body)
            time.sleep(2)
            unchanged = request_json(client.get(f"/api/v1/actions/{parent_prepared['id']}", headers=auth(token)), "read unapproved parent")
            if unchanged.get("state") != "awaiting_approval":
                raise EmailThreadingValidationFailure("Parent email auto-approved or executed.")
            rejected = client.post(
                f"/api/v1/actions/{parent_prepared['id']}/approve",
                headers=auth(token),
                json={"preview_hash": wrong_hash(parent_prepared["preview_hash"])},
            )
            if rejected.status_code != 409:
                raise EmailThreadingValidationFailure("Wrong-hash parent approval was not rejected.")
            request_json(client.post(
                f"/api/v1/actions/{parent_prepared['id']}/approve",
                headers=auth(token),
                json={"preview_hash": parent_prepared["preview_hash"]},
            ), "approve Gmail parent", expected=202)
            parent = wait_terminal(client, token, parent_prepared["id"], args.timeout, "Gmail parent")
            validate_completion(parent, parent_prepared)
            thread_id = parent["receipt"]["thread_id"]

            reply_prepared = request_json(client.post(
                "/api/v1/actions",
                headers=auth(token) | {"Idempotency-Key": "live-thread-reply-" + uuid.uuid4().hex},
                json={"connection_id": connection["id"], "payload": {
                    "kind": "email_thread_reply",
                    "parent_action_id": parent["id"],
                    "to": [recipient], "cc": [], "bcc": [],
                    "subject": subject, "body": reply_body,
                }},
            ), "prepare Gmail thread reply", expected=201)
            validate_prepared_reply(reply_prepared, parent, reply_body)
            rejected = client.post(
                f"/api/v1/actions/{reply_prepared['id']}/approve",
                headers=auth(token),
                json={"preview_hash": wrong_hash(reply_prepared["preview_hash"])},
            )
            if rejected.status_code != 409:
                raise EmailThreadingValidationFailure("Wrong-hash reply approval was not rejected.")
            request_json(client.post(
                f"/api/v1/actions/{reply_prepared['id']}/approve",
                headers=auth(token),
                json={"preview_hash": reply_prepared["preview_hash"]},
            ), "approve Gmail thread reply", expected=202)
            reply = wait_terminal(client, token, reply_prepared["id"], args.timeout, "Gmail thread reply")
            validate_completion(reply, reply_prepared, expected_thread_id=thread_id)
            if reply["receipt"]["provider_id"] == parent["receipt"]["provider_id"]:
                raise EmailThreadingValidationFailure("Parent and reply unexpectedly share one Gmail message id.")

        evidence = {}
        if args.base_evidence:
            loaded = json.loads(args.base_evidence.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise EmailThreadingValidationFailure("Base evidence must be a JSON object.")
            evidence.update(loaded)
        evidence["action_email_threading"] = passed(
            "live Gmail owned-thread follow-up passed send-only connection discovery, immutable parent/reply previews, wrong-hash denial, explicit approvals, exact To/Cc/subject preservation, no Bcc, approval-bound RFC reply context, single execution audits, distinct provider messages and stable Gmail threadId"
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output), "status": "passed", "feature": "action_email_threading",
            "parent_action_id": parent["id"], "reply_action_id": reply["id"], "thread_id": thread_id,
        }, indent=2))
    except (EmailThreadingValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
