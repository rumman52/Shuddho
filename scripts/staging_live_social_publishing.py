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
from services.coworker.config import Settings


TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}


class SocialPublishingValidationFailure(RuntimeError):
    pass


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get(
        "SHUDDHO_STAGING_ALLOW_LIVE_SOCIAL_PUBLISHING", ""
    ).lower() != "true":
        raise SocialPublishingValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_SOCIAL_PUBLISHING=true only "
            "for the controlled LinkedIn staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(
    response: httpx.Response,
    label: str,
    expected: int = 200,
) -> dict:
    if response.status_code != expected:
        raise SocialPublishingValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise SocialPublishingValidationFailure(
            f"{label} did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise SocialPublishingValidationFailure(
            f"{label} returned an unexpected JSON shape."
        )
    return value


def connection_for(connections: list[dict]) -> dict:
    matches = [
        item
        for item in connections
        if isinstance(item, dict)
        and item.get("provider") == "linkedin"
        and item.get("capability") == "social"
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise SocialPublishingValidationFailure(
            "Expected exactly one active LinkedIn social staging connection; "
            f"found {len(matches)}."
        )
    return matches[0]


def wrong_hash(value: str) -> str:
    if len(value) != 64:
        raise SocialPublishingValidationFailure(
            "Prepared preview hash is invalid."
        )
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_prepared(action: dict, connection: dict, text: str) -> None:
    if (
        action.get("state") != "awaiting_approval"
        or action.get("approved_at") is not None
        or action.get("receipt") is not None
    ):
        raise SocialPublishingValidationFailure(
            "Prepared LinkedIn post is not a clean approval preview."
        )
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if (
        not isinstance(preview, dict)
        or not isinstance(preview_hash, str)
        or digest(preview) != preview_hash
    ):
        raise SocialPublishingValidationFailure(
            "Prepared LinkedIn preview hash does not match."
        )
    if preview.get("provider") != "linkedin":
        raise SocialPublishingValidationFailure(
            "Prepared social action is not bound to LinkedIn."
        )
    if preview.get("connection_id") != connection.get("id"):
        raise SocialPublishingValidationFailure(
            "Prepared social action changed the selected connection."
        )
    account = preview.get("account")
    if (
        not isinstance(account, str)
        or not account.startswith("urn:li:person:")
    ):
        raise SocialPublishingValidationFailure(
            "Prepared social action is not bound to a personal LinkedIn member."
        )
    if preview.get("payload") != {
        "kind": "social_publish_linkedin",
        "text": text,
    }:
        raise SocialPublishingValidationFailure(
            "Prepared LinkedIn post differs from the submitted text."
        )
    if preview.get("social_publishing") != {
        "provider": "linkedin",
        "author": "connected_personal_member",
        "visibility": "public",
        "media": "none",
        "scheduling": "none",
        "social_read": "none",
        "agent_authority": "none",
    }:
        raise SocialPublishingValidationFailure(
            "Prepared social policy does not prove the bounded v1 authority."
        )
    scope = preview.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("contract") != "shuddho.consequential-action"
        or scope.get("contract_version") != 5
        or scope.get("provider") != "linkedin"
        or scope.get("capability") != "social"
        or scope.get("account") != account
        or scope.get("destinations") != {}
        or scope.get("policy", {}).get("social_publishing")
        != preview["social_publishing"]
    ):
        raise SocialPublishingValidationFailure(
            "LinkedIn approval scope does not exactly bind the social action."
        )


def wait_terminal(
    client: httpx.Client,
    token: str,
    action_id: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        value = request_json(
            client.get(
                f"/api/v1/actions/{action_id}",
                headers=auth(token),
            ),
            "read LinkedIn action",
        )
        if value.get("state") in TERMINAL:
            if value.get("state") != "succeeded":
                raise SocialPublishingValidationFailure(
                    "LinkedIn action ended in "
                    f"{value.get('state')!r}; expected succeeded."
                )
            return value
        time.sleep(2)
    raise SocialPublishingValidationFailure(
        "LinkedIn action did not finish before timeout."
    )


def validate_completion(action: dict, prepared: dict) -> None:
    if (
        action.get("preview_hash") != prepared.get("preview_hash")
        or action.get("preview") != prepared.get("preview")
    ):
        raise SocialPublishingValidationFailure(
            "Approved LinkedIn preview mutated before completion."
        )
    audit = [
        item.get("action")
        for item in action.get("audit", [])
        if isinstance(item, dict)
    ]
    for name in (
        "action.prepared",
        "action.approved",
        "action.execution_started",
        "action.succeeded",
    ):
        if audit.count(name) != 1:
            raise SocialPublishingValidationFailure(
                f"Expected exactly one {name}; found {audit.count(name)}."
            )
    receipt = action.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("provider") != "linkedin"
        or receipt.get("status") != "post_published"
        or receipt.get("author") != action["preview"]["account"]
        or receipt.get("visibility") != "PUBLIC"
        or not isinstance(receipt.get("provider_id"), str)
        or not (
            receipt["provider_id"].startswith("urn:li:share:")
            or receipt["provider_id"].startswith("urn:li:ugcPost:")
        )
    ):
        raise SocialPublishingValidationFailure(
            "LinkedIn receipt is missing the approved author/post identity."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate approval-bound LinkedIn personal text publishing "
            "in controlled staging."
        )
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if (
        not settings.actions_enabled
        or not settings.action_social_publishing_enabled
    ):
        raise SystemExit(
            "Actions and social publishing must both be enabled "
            "in controlled staging."
        )

    base_url = require_https_base(
        env_secret("SHUDDHO_STAGING_API_BASE_URL")
    )
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    text = (
        "Shuddho controlled staging social publish "
        + uuid.uuid4().hex[:12]
        + ". Synthetic test post; no customer data."
    )

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=20,
            follow_redirects=False,
        ) as client:
            listed = request_json(
                client.get(
                    "/api/v1/connections",
                    headers=auth(token),
                ),
                "list staging connections",
            )
            if listed.get("social_publishing_enabled") is not True:
                raise SocialPublishingValidationFailure(
                    "Deployed social publishing is not enabled."
                )
            connections = listed.get("connections")
            if not isinstance(connections, list):
                raise SocialPublishingValidationFailure(
                    "Connection list has an unexpected shape."
                )
            connection = connection_for(connections)

            prepared = request_json(
                client.post(
                    "/api/v1/actions",
                    headers=auth(token)
                    | {
                        "Idempotency-Key":
                        "live-linkedin-post-" + uuid.uuid4().hex
                    },
                    json={
                        "connection_id": connection["id"],
                        "payload": {
                            "kind": "social_publish_linkedin",
                            "text": text,
                        },
                    },
                ),
                "prepare LinkedIn post",
                expected=201,
            )
            validate_prepared(prepared, connection, text)

            time.sleep(2)
            unchanged = request_json(
                client.get(
                    f"/api/v1/actions/{prepared['id']}",
                    headers=auth(token),
                ),
                "read unapproved LinkedIn post",
            )
            if unchanged.get("state") != "awaiting_approval":
                raise SocialPublishingValidationFailure(
                    "LinkedIn post auto-approved or executed."
                )

            rejected = client.post(
                f"/api/v1/actions/{prepared['id']}/approve",
                headers=auth(token),
                json={
                    "preview_hash": wrong_hash(
                        prepared["preview_hash"]
                    )
                },
            )
            if rejected.status_code != 409:
                raise SocialPublishingValidationFailure(
                    "Wrong-hash LinkedIn approval was not rejected."
                )

            request_json(
                client.post(
                    f"/api/v1/actions/{prepared['id']}/approve",
                    headers=auth(token),
                    json={
                        "preview_hash": prepared["preview_hash"]
                    },
                ),
                "approve LinkedIn post",
                expected=202,
            )
            completed = wait_terminal(
                client,
                token,
                prepared["id"],
                args.timeout,
            )
            validate_completion(completed, prepared)

        evidence: dict = {}
        if args.base_evidence:
            loaded = json.loads(
                args.base_evidence.read_text(encoding="utf-8")
            )
            if not isinstance(loaded, dict):
                raise SocialPublishingValidationFailure(
                    "Base evidence must be a JSON object."
                )
            evidence.update(loaded)
        evidence["action_social_publishing"] = passed(
            "live LinkedIn personal text publishing passed exact connected-member "
            "and UTF-8 text binding, public/text-only policy, no auto-publish, "
            "wrong-hash denial, explicit approval, single execution audits and "
            "confirmed provider post receipt without social-read authority"
        )
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "written": str(args.output),
                    "status": "passed",
                    "feature": "action_social_publishing",
                    "action_id": completed["id"],
                    "provider_id": completed["receipt"]["provider_id"],
                },
                indent=2,
            )
        )
    except (
        SocialPublishingValidationFailure,
        httpx.HTTPError,
        OSError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {"status": "failed", "error": str(error)},
                indent=2,
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
