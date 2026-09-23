from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.config import Settings


class RecipientValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_RECIPIENTS", "").lower() != "true":
        raise RecipientValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_ACTION_RECIPIENTS=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise RecipientValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise RecipientValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise RecipientValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def validate_directory(value: dict, *, enabled: bool = True) -> list[dict]:
    if value.get("enabled") is not enabled:
        raise RecipientValidationFailure("Deployed saved-recipient capability does not match the staging exercise.")
    rows = value.get("recipients")
    if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
        raise RecipientValidationFailure("Saved-recipient directory returned an unexpected shape.")
    return rows


def validate_recipient(value: dict, *, name: str, email: str) -> str:
    recipient_id = value.get("id")
    if (
        not isinstance(recipient_id, str)
        or len(recipient_id) != 36
        or value.get("name") != name
        or value.get("email") != email
        or not isinstance(value.get("created_at"), str)
        or not isinstance(value.get("updated_at"), str)
    ):
        raise RecipientValidationFailure("Saved recipient did not preserve the exact reviewed name/email pair.")
    return recipient_id


def require_absent(rows: list[dict], *, recipient_id: str, emails: set[str]) -> None:
    for item in rows:
        if item.get("id") == recipient_id or item.get("email") in emails:
            raise RecipientValidationFailure("Saved recipient leaked across owners or remained after cleanup.")


def merge_evidence(base_evidence: Path | None, update: dict) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RecipientValidationFailure("Base staging evidence must be a JSON object.")
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate owner-scoped saved action recipients in controlled staging."
    )
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled or not settings.action_recipients_enabled:
        raise SystemExit("SHUDDHO_ACTIONS_ENABLED and SHUDDHO_ACTION_RECIPIENTS_ENABLED must be true.")

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token_a = env_secret("SHUDDHO_STAGING_TOKEN_A")
    token_b = env_secret("SHUDDHO_STAGING_TOKEN_B")
    if token_a == token_b:
        raise SystemExit("The two staging account tokens must be different.")

    marker = uuid.uuid4().hex[:12]
    first_name = f"Shuddho staging recipient {marker}"
    first_email = f"recipient-{marker}@example.test"
    second_name = f"Shuddho staging updated {marker}"
    second_email = f"updated-{marker}@example.test"
    created_id = None

    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            before_a = validate_directory(request_json(
                client.get("/api/v1/action-recipients", headers=auth(token_a)),
                "list owner A recipients",
            ))
            before_b = validate_directory(request_json(
                client.get("/api/v1/action-recipients", headers=auth(token_b)),
                "list owner B recipients",
            ))
            require_absent(before_a, recipient_id="synthetic-not-created", emails={first_email, second_email})
            require_absent(before_b, recipient_id="synthetic-not-created", emails={first_email, second_email})

            created = request_json(
                client.post(
                    "/api/v1/action-recipients",
                    headers=auth(token_a),
                    json={"name": first_name, "email": first_email},
                ),
                "create owner A recipient",
                expected=201,
            )
            created_id = validate_recipient(created, name=first_name, email=first_email)

            owner_a = validate_directory(request_json(
                client.get("/api/v1/action-recipients", headers=auth(token_a)),
                "read owner A recipients after create",
            ))
            if sum(item.get("id") == created_id for item in owner_a) != 1:
                raise RecipientValidationFailure("Owner A could not read exactly one created recipient.")

            owner_b = validate_directory(request_json(
                client.get("/api/v1/action-recipients", headers=auth(token_b)),
                "read owner B recipients after owner A create",
            ))
            require_absent(owner_b, recipient_id=created_id, emails={first_email, second_email})

            other_update = client.put(
                f"/api/v1/action-recipients/{created_id}",
                headers=auth(token_b),
                json={"name": "Cross-owner mutation", "email": f"wrong-{marker}@example.test"},
            )
            if other_update.status_code != 404:
                raise RecipientValidationFailure(
                    f"Cross-owner recipient update returned HTTP {other_update.status_code}; expected 404."
                )
            other_delete = client.delete(
                f"/api/v1/action-recipients/{created_id}",
                headers=auth(token_b),
            )
            if other_delete.status_code != 404:
                raise RecipientValidationFailure(
                    f"Cross-owner recipient delete returned HTTP {other_delete.status_code}; expected 404."
                )

            updated = request_json(
                client.put(
                    f"/api/v1/action-recipients/{created_id}",
                    headers=auth(token_a),
                    json={"name": second_name, "email": second_email},
                ),
                "update owner A recipient",
            )
            validate_recipient(updated, name=second_name, email=second_email)

            deleted = request_json(
                client.delete(
                    f"/api/v1/action-recipients/{created_id}",
                    headers=auth(token_a),
                ),
                "delete owner A recipient",
            )
            if deleted != {"deleted": True, "id": created_id}:
                raise RecipientValidationFailure("Recipient deletion returned an unexpected receipt.")
            created_id = None

            final_a = validate_directory(request_json(
                client.get("/api/v1/action-recipients", headers=auth(token_a)),
                "read owner A recipients after cleanup",
            ))
            final_b = validate_directory(request_json(
                client.get("/api/v1/action-recipients", headers=auth(token_b)),
                "read owner B recipients after cleanup",
            ))
            require_absent(final_a, recipient_id=updated["id"], emails={first_email, second_email})
            require_absent(final_b, recipient_id=updated["id"], emails={first_email, second_email})

        evidence = merge_evidence(args.base_evidence, {
            "action_recipients": passed(
                "live saved-recipient CRUD passed exact name/email preservation, owner isolation, "
                "cross-owner 404 mutation denial, update validation, deletion and cleanup"
            )
        })
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": "passed",
            "feature": "action_recipients",
            "cleanup": "synthetic recipient removed",
        }, indent=2))
    except (RecipientValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        if created_id:
            try:
                with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as cleanup:
                    cleanup.delete(f"/api/v1/action-recipients/{created_id}", headers=auth(token_a))
            except Exception:
                pass
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
