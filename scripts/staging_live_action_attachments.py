from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_repository import ATTACHMENT_CONTENT_TYPES, digest
from services.coworker.action_schemas import address
from services.coworker.config import Settings


TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}


class AttachmentValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_ATTACHMENTS", "").lower() != "true":
        raise AttachmentValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_ACTION_ATTACHMENTS=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise AttachmentValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise AttachmentValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise AttachmentValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def connection_for(connections: list[dict], provider: str) -> dict:
    matches = [
        item for item in connections
        if isinstance(item, dict)
        and item.get("provider") == provider
        and item.get("capability") == "email"
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise AttachmentValidationFailure(
            f"Expected exactly one active {provider} email staging connection; found {len(matches)}."
        )
    return matches[0]


def artifact_for(value: dict, artifact_id: str) -> dict:
    if value.get("attachments_enabled") is not True:
        raise AttachmentValidationFailure("Deployed attachment capability is not enabled.")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise AttachmentValidationFailure("Artifact list has an unexpected shape.")
    matches = [item for item in artifacts if isinstance(item, dict) and item.get("id") == artifact_id]
    if len(matches) != 1:
        raise AttachmentValidationFailure(
            "The explicitly selected synthetic staging artifact was not found in this account."
        )
    artifact = matches[0]
    base_type = str(artifact.get("content_type", "")).split(";", 1)[0].strip().lower()
    extension = ATTACHMENT_CONTENT_TYPES.get(base_type)
    if (
        extension is None
        or not str(artifact.get("filename", "")).lower().endswith(extension)
        or not isinstance(artifact.get("byte_size"), int)
        or not 1 <= artifact["byte_size"] <= 2 * 1024 * 1024
        or not isinstance(artifact.get("sha256"), str)
        or len(artifact["sha256"]) != 64
    ):
        raise AttachmentValidationFailure("Selected staging artifact is not attachment-safe.")
    return {
        "id": artifact_id,
        "filename": artifact["filename"],
        "content_type": base_type,
        "byte_size": artifact["byte_size"],
        "sha256": artifact["sha256"],
    }


def wrong_hash(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise AttachmentValidationFailure("Prepared preview hash is invalid.")
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_prepared(action: dict, provider: str, connection_id: str, payload: dict, artifact: dict) -> None:
    if action.get("state") != "awaiting_approval" or action.get("approved_at") is not None:
        raise AttachmentValidationFailure("Attachment action was not waiting for explicit approval.")
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str):
        raise AttachmentValidationFailure("Prepared attachment action has no immutable preview.")
    if digest(preview) != preview_hash:
        raise AttachmentValidationFailure("Attachment preview hash does not match its preview.")
    if preview.get("version") != 3 or preview.get("provider") != provider:
        raise AttachmentValidationFailure("Attachment preview has the wrong version or provider.")
    if preview.get("payload") != payload or preview.get("attachments") != [artifact]:
        raise AttachmentValidationFailure("Attachment preview changed payload or artifact metadata.")
    scope = preview.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("contract_version") != 2
        or scope.get("provider") != provider
        or scope.get("connection_id") != connection_id
        or scope.get("attachments") != [artifact]
        or scope.get("policy", {}).get("attachments") != "owned_artifacts"
        or not isinstance(scope.get("attachments_sha256"), str)
        or len(scope["attachments_sha256"]) != 64
    ):
        raise AttachmentValidationFailure("Attachment approval scope is incomplete or changed.")


def prove_no_auto_approval(client: httpx.Client, token: str, action: dict) -> None:
    time.sleep(2)
    action_id = str(action["id"])
    current = request_json(
        client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
        "read unapproved attachment action",
    )
    if current.get("state") != "awaiting_approval" or current.get("approved_at") is not None:
        raise AttachmentValidationFailure("Attachment action changed before explicit approval.")
    rejected = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=auth(token),
        json={"preview_hash": wrong_hash(str(action["preview_hash"]))},
    )
    if rejected.status_code != 409:
        raise AttachmentValidationFailure(
            f"Wrong-hash attachment approval returned HTTP {rejected.status_code}; expected 409."
        )


def wait_terminal(client: httpx.Client, token: str, action_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
            "attachment action status",
        )
        if value.get("state") in TERMINAL:
            if value.get("state") != "succeeded":
                raise AttachmentValidationFailure(
                    f"Attachment action ended in state {value.get('state')!r}, not succeeded."
                )
            return value
        time.sleep(2)
    raise AttachmentValidationFailure("Approved attachment action did not finish before timeout.")


def validate_completion(action: dict, prepared: dict, provider: str) -> None:
    if action.get("preview") != prepared.get("preview") or action.get("preview_hash") != prepared.get("preview_hash"):
        raise AttachmentValidationFailure("Approved attachment preview mutated during execution.")
    audit = [item.get("action") for item in action.get("audit", []) if isinstance(item, dict)]
    for name in ("action.prepared", "action.approved", "action.execution_started", "action.succeeded"):
        if audit.count(name) != 1:
            raise AttachmentValidationFailure(f"Attachment audit expected exactly one {name}.")
    receipt = action.get("receipt")
    expected_status = "accepted_by_gmail" if provider == "google" else "accepted_by_microsoft_graph"
    if (
        not isinstance(receipt, dict)
        or receipt.get("provider") != provider
        or receipt.get("status") != expected_status
    ):
        raise AttachmentValidationFailure("Attachment provider receipt is missing or unexpected.")
    try:
        datetime.fromisoformat(str(receipt["confirmed_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise AttachmentValidationFailure("Attachment receipt timestamp is invalid.") from None


def merge_evidence(base_evidence: Path | None, update: dict) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise AttachmentValidationFailure("Base staging evidence must be a JSON object.")
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate one live, explicitly approved Shuddho artifact email attachment in controlled staging."
    )
    parser.add_argument("--provider", choices=("google", "microsoft"), default="google")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled or not settings.action_attachments_enabled:
        raise SystemExit("SHUDDHO_ACTIONS_ENABLED and SHUDDHO_ACTION_ATTACHMENTS_ENABLED must be true.")
    if args.provider == "microsoft" and not settings.microsoft_actions_enabled:
        raise SystemExit("SHUDDHO_MICROSOFT_ACTIONS_ENABLED must be true for Microsoft validation.")

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    artifact_id = env_secret("SHUDDHO_STAGING_ACTION_ATTACHMENT_ARTIFACT_ID")
    recipient_name = (
        "SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT"
        if args.provider == "google"
        else "SHUDDHO_STAGING_MICROSOFT_TEST_RECIPIENT"
    )
    try:
        recipient = address(env_secret(recipient_name))
    except ValueError as error:
        raise SystemExit(f"Invalid {recipient_name}: {error}") from None

    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            connections_value = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list staging connections",
            )
            connection = connection_for(connections_value.get("connections", []), args.provider)
            sender = address(str(connection["email"]))
            if sender.casefold() == recipient.casefold():
                raise AttachmentValidationFailure("Use a separate authorized staging recipient.")
            artifact_value = request_json(
                client.get("/api/v1/artifacts", headers=auth(token)),
                "list staging artifacts",
            )
            artifact = artifact_for(artifact_value, artifact_id)
            marker = uuid.uuid4().hex[:10]
            payload = {
                "kind": "email_send_with_attachments",
                "to": [sender],
                "cc": [],
                "bcc": [recipient],
                "subject": f"Shuddho attachment staging test {marker} — বাংলা",
                "body": (
                    "Synthetic controlled-staging email. The attached file must contain only test data. "
                    "This validates immutable approval-bound artifact delivery."
                ),
            }
            prepared = request_json(
                client.post(
                    "/api/v1/actions",
                    headers=auth(token) | {"Idempotency-Key": "live-attachment-" + uuid.uuid4().hex},
                    json={
                        "connection_id": connection["id"],
                        "attachment_ids": [artifact_id],
                        "payload": payload,
                    },
                ),
                "prepare attachment action",
                expected=201,
            )
            validate_prepared(prepared, args.provider, str(connection["id"]), payload, artifact)
            prove_no_auto_approval(client, token, prepared)
            approved = request_json(
                client.post(
                    f"/api/v1/actions/{prepared['id']}/approve",
                    headers=auth(token),
                    json={"preview_hash": prepared["preview_hash"]},
                ),
                "approve exact attachment action",
                expected=202,
            )
            if approved.get("preview_hash") != prepared["preview_hash"]:
                raise AttachmentValidationFailure("Exact approval returned a different preview hash.")
            completed = wait_terminal(client, token, str(prepared["id"]), args.timeout)
            validate_completion(completed, prepared, args.provider)

        evidence = merge_evidence(
            args.base_evidence,
            {
                "action_attachments": passed(
                    f"live {args.provider} attachment email passed v3 artifact-manifest binding, "
                    "wrong-hash rejection, explicit approval, single execution audit and provider acceptance"
                )
            },
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": "passed",
            "provider": args.provider,
            "action_id": completed["id"],
            "cleanup": "Remove the synthetic staging email after retaining approved evidence.",
        }, indent=2))
    except (AttachmentValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
