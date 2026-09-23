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
ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
}


class DocumentSharingValidationFailure(RuntimeError):
    pass


def digest(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_DOCUMENT_SHARING", "").lower() != "true":
        raise DocumentSharingValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_DOCUMENT_SHARING=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise DocumentSharingValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise DocumentSharingValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise DocumentSharingValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def connection_for(connections: list[dict]) -> dict:
    matches = [
        item for item in connections
        if isinstance(item, dict)
        and item.get("provider") == "google"
        and item.get("capability") == "drive"
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise DocumentSharingValidationFailure(
            f"Expected exactly one active Google Drive staging connection; found {len(matches)}."
        )
    return matches[0]


def artifact_for(value: dict, artifact_id: str) -> dict:
    if value.get("document_sharing_enabled") is not True:
        raise DocumentSharingValidationFailure("Deployed document sharing is not enabled.")
    rows = value.get("artifacts")
    if not isinstance(rows, list):
        raise DocumentSharingValidationFailure("Artifact list has an unexpected shape.")
    matches = [item for item in rows if isinstance(item, dict) and item.get("id") == artifact_id]
    if len(matches) != 1:
        raise DocumentSharingValidationFailure(
            "The configured synthetic staging artifact was not found exactly once."
        )
    artifact = matches[0]
    content_type = str(artifact.get("content_type") or "").split(";", 1)[0].lower()
    if content_type not in ALLOWED_TYPES:
        raise DocumentSharingValidationFailure("Unsupported synthetic artifact type.")
    size = artifact.get("byte_size")
    sha = artifact.get("sha256")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or not 1 <= size <= 8 * 1024 * 1024
        or not isinstance(sha, str)
        or len(sha) != 64
        or any(char not in "0123456789abcdef" for char in sha)
    ):
        raise DocumentSharingValidationFailure("Synthetic artifact metadata is invalid.")
    return artifact


def wrong_hash(value: str) -> str:
    if len(value) != 64:
        raise DocumentSharingValidationFailure("Prepared preview hash is invalid.")
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_prepared(action: dict, artifact: dict, recipient: str) -> None:
    if action.get("state") != "awaiting_approval":
        raise DocumentSharingValidationFailure("Prepared share is not awaiting approval.")
    if action.get("approved_at") is not None or action.get("receipt") is not None:
        raise DocumentSharingValidationFailure("Prepared share already contains execution state.")
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str):
        raise DocumentSharingValidationFailure("Prepared share is missing immutable preview data.")
    if digest(preview) != preview_hash:
        raise DocumentSharingValidationFailure("Prepared preview hash does not match.")
    if preview.get("payload") != {
        "kind": "document_share",
        "recipients": [recipient],
    }:
        raise DocumentSharingValidationFailure("Prepared recipient differs from the submitted recipient.")
    shared = preview.get("shared_artifact")
    if not isinstance(shared, dict):
        raise DocumentSharingValidationFailure("Prepared share is missing artifact metadata.")
    for key in ("id", "filename", "byte_size", "sha256"):
        if shared.get(key) != artifact.get(key):
            raise DocumentSharingValidationFailure(
                f"Prepared artifact {key} differs from the owned artifact."
            )
    if preview.get("document_sharing") != {
        "source": "owned_shuddho_artifact",
        "access": "reader",
        "notifications": "recipient",
    }:
        raise DocumentSharingValidationFailure("Prepared policy is not exact reader-only access.")


def wait_terminal(client: httpx.Client, token: str, action_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
            "document-sharing status",
        )
        if value.get("state") in TERMINAL:
            if value.get("state") != "succeeded":
                raise DocumentSharingValidationFailure(
                    f"Document sharing ended in {value.get('state')!r}; expected succeeded."
                )
            return value
        time.sleep(2)
    raise DocumentSharingValidationFailure("Document sharing did not finish before timeout.")


def validate_completed(action: dict, prepared: dict, artifact: dict, recipient: str) -> None:
    if action.get("preview_hash") != prepared.get("preview_hash") or action.get("preview") != prepared.get("preview"):
        raise DocumentSharingValidationFailure("Approved preview mutated before provider completion.")
    audit = [item.get("action") for item in action.get("audit", []) if isinstance(item, dict)]
    for item in ("action.prepared", "action.approved", "action.execution_started", "action.succeeded"):
        if audit.count(item) != 1:
            raise DocumentSharingValidationFailure(
                f"Expected exactly one {item}; found {audit.count(item)}."
            )
    receipt = action.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("provider") != "google"
        or receipt.get("status") != "document_shared"
        or receipt.get("recipient") != recipient
        or receipt.get("access") != "reader"
        or receipt.get("artifact_sha256") != artifact.get("sha256")
        or not isinstance(receipt.get("provider_id"), str)
        or not receipt["provider_id"]
    ):
        raise DocumentSharingValidationFailure(
            "Google Drive receipt does not exactly match the approved artifact, recipient and reader access."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate approval-bound Google Drive document sharing in controlled staging."
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if (
        not settings.actions_enabled
        or not settings.artifact_services_enabled
        or not settings.action_document_sharing_enabled
    ):
        raise SystemExit(
            "Actions, artifact services and document sharing must all be enabled in controlled staging."
        )
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    artifact_id = env_secret("SHUDDHO_STAGING_DOCUMENT_SHARE_ARTIFACT_ID")
    try:
        recipient = address(env_secret("SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT"))
    except ValueError as error:
        raise SystemExit(f"Invalid staging recipient: {error}") from None

    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            connections = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list staging connections",
            ).get("connections")
            if not isinstance(connections, list):
                raise DocumentSharingValidationFailure("Connection list has an unexpected shape.")
            connection = connection_for(connections)
            artifact = artifact_for(
                request_json(
                    client.get("/api/v1/artifacts", headers=auth(token)),
                    "list staging artifacts",
                ),
                artifact_id,
            )
            prepared = request_json(
                client.post(
                    "/api/v1/actions",
                    headers=auth(token) | {"Idempotency-Key": "live-drive-" + uuid.uuid4().hex},
                    json={
                        "connection_id": connection["id"],
                        "artifact_ids": [artifact_id],
                        "payload": {
                            "kind": "document_share",
                            "recipients": [recipient],
                        },
                    },
                ),
                "prepare Google Drive document sharing",
                expected=201,
            )
            validate_prepared(prepared, artifact, recipient)

            time.sleep(2)
            unchanged = request_json(
                client.get(f"/api/v1/actions/{prepared['id']}", headers=auth(token)),
                "read unapproved document sharing",
            )
            if unchanged.get("state") != "awaiting_approval":
                raise DocumentSharingValidationFailure("Document sharing auto-approved or executed.")

            rejected = client.post(
                f"/api/v1/actions/{prepared['id']}/approve",
                headers=auth(token),
                json={"preview_hash": wrong_hash(prepared["preview_hash"])},
            )
            if rejected.status_code != 409:
                raise DocumentSharingValidationFailure(
                    f"Wrong-hash approval returned HTTP {rejected.status_code}; expected 409."
                )

            approved = request_json(
                client.post(
                    f"/api/v1/actions/{prepared['id']}/approve",
                    headers=auth(token),
                    json={"preview_hash": prepared["preview_hash"]},
                ),
                "approve exact document sharing",
                expected=202,
            )
            if approved.get("preview_hash") != prepared["preview_hash"]:
                raise DocumentSharingValidationFailure("Approval changed the immutable preview hash.")
            completed = wait_terminal(client, token, str(prepared["id"]), args.timeout)
            validate_completed(completed, prepared, artifact, recipient)

        evidence = {}
        if args.base_evidence:
            loaded = json.loads(args.base_evidence.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise DocumentSharingValidationFailure("Base evidence must be a JSON object.")
            evidence.update(loaded)
        evidence["action_document_sharing"] = passed(
            "live Google Drive sharing passed exact owned-artifact hash binding, wrong-hash approval denial, explicit approval, single execution audit, exact reader permission and provider receipt validation"
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": "passed",
            "feature": "action_document_sharing",
            "action_id": completed["id"],
            "provider_id": completed["receipt"]["provider_id"],
        }, indent=2))
    except (DocumentSharingValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
