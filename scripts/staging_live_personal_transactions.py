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


class PersonalTransactionsValidationFailure(RuntimeError):
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


def passed(
    evidence: str,
    operation: str,
    existing: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    operation_evidence: dict[str, dict[str, str]] = {}
    if isinstance(existing, dict):
        prior = existing.get("operation_evidence")
        if isinstance(prior, dict):
            for key, value in prior.items():
                if (
                    isinstance(key, str)
                    and isinstance(value, dict)
                    and isinstance(value.get("evidence"), str)
                    and value["evidence"].strip()
                    and isinstance(value.get("verified_at"), str)
                ):
                    operation_evidence[key] = {
                        "evidence": value["evidence"],
                        "verified_at": value["verified_at"],
                    }
    operation_evidence[operation] = {
        "evidence": evidence,
        "verified_at": now,
    }
    return {
        "status": "passed",
        "evidence": "qualified transaction operations: "
        + ", ".join(sorted(operation_evidence)),
        "verified_at": now,
        "operation_evidence": {
            key: operation_evidence[key]
            for key in sorted(operation_evidence)
        },
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_PERSONAL_TRANSACTIONS", "").lower() != "true":
        raise PersonalTransactionsValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_PERSONAL_TRANSACTIONS=true only for the dedicated controlled-staging transaction test."
        )


def wrong_hash(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise PersonalTransactionsValidationFailure("Prepared preview hash is invalid.")
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_transaction_authority(value: dict, provider: str) -> None:
    expected = f"{provider}:negotiation_commitment_email"
    if (
        value.get("schema_version") != 1
        or value.get("personal_transactions_enabled") is not True
        or not isinstance(value.get("operations"), list)
        or expected not in value["operations"]
    ):
        raise PersonalTransactionsValidationFailure(
            f"Deployed PA-09 transaction authority does not allow {expected}."
        )


def connection_for(connections: list[dict], provider: str) -> dict:
    matches = [
        item
        for item in connections
        if isinstance(item, dict)
        and item.get("active") is True
        and item.get("provider") == provider
        and item.get("capability") == "email"
    ]
    if len(matches) != 1:
        raise PersonalTransactionsValidationFailure(
            f"Expected exactly one active {provider} email connection for controlled staging."
        )
    return matches[0]


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise PersonalTransactionsValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise PersonalTransactionsValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise PersonalTransactionsValidationFailure(f"{label} returned an unexpected shape.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def expected_payload(counterparty_email: str, marker: str) -> dict:
    return {
        "kind": "negotiation_commitment_email",
        "to": [counterparty_email],
        "cc": [],
        "bcc": [],
        "subject": "Shuddho controlled staging negotiation " + marker,
        "body": (
            "Synthetic controlled-staging commitment only. "
            "No customer data, purchase, payment, booking or real commercial obligation."
        ),
        "counterparty": "Shuddho controlled staging mailbox",
        "commitment_summary": "Synthetic PA-09 negotiation commitment validation.",
        "terms": [
            {"name": "TestReference", "value": marker},
            {"name": "Amount", "value": "USD 0.00 synthetic"},
            {"name": "Effect", "value": "Controlled staging validation only"},
        ],
    }


def validate_prepared(prepared: dict, connection: dict, payload: dict) -> None:
    preview = prepared.get("preview")
    if (
        prepared.get("state") != "awaiting_approval"
        or prepared.get("approved_at") is not None
        or prepared.get("receipt") is not None
        or not isinstance(preview, dict)
        or preview.get("version") != 6
        or preview.get("provider") != connection.get("provider")
        or preview.get("connection_id") != connection.get("id")
        or preview.get("payload") != payload
    ):
        raise PersonalTransactionsValidationFailure(
            "Prepared transaction does not exactly match the requested immutable preview."
        )
    transaction = preview.get("transaction")
    if transaction != {
        "class": "binding_negotiation_commitment",
        "approval": "exact_final_terms",
        "changed_terms": "fresh_preview_required",
        "uncertain_outcome": "do_not_retry",
        "provider_idempotency": "provider_specific_only",
    }:
        raise PersonalTransactionsValidationFailure("Prepared transaction policy is not fail-closed.")
    scope = preview.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("contract") != "shuddho.consequential-action"
        or scope.get("contract_version") != 6
        or scope.get("action_kind") != "negotiation_commitment_email"
        or scope.get("destinations", {}).get("to") != [payload["to"][0]]
        or scope.get("policy", {}).get("transaction") != transaction
    ):
        raise PersonalTransactionsValidationFailure(
            "Prepared transaction approval scope does not bind the exact final terms."
        )
    if prepared.get("preview_hash") != digest(preview):
        raise PersonalTransactionsValidationFailure("Prepared transaction preview hash is invalid.")


def wait_terminal(client: httpx.Client, token: str, action_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
            "read transaction action",
        )
        if value.get("state") in TERMINAL:
            return value
        time.sleep(2)
    raise PersonalTransactionsValidationFailure("Transaction action did not finish before timeout.")


def validate_completion(action: dict, prepared: dict) -> None:
    if action.get("preview_hash") != prepared.get("preview_hash") or action.get("preview") != prepared.get("preview"):
        raise PersonalTransactionsValidationFailure("Approved transaction preview mutated before completion.")
    if action.get("state") != "succeeded":
        raise PersonalTransactionsValidationFailure(
            f"Transaction ended in {action.get('state')!r}; expected succeeded."
        )
    audit = [item.get("action") for item in action.get("audit", []) if isinstance(item, dict)]
    for name in ("action.prepared", "action.approved", "action.execution_started", "action.succeeded"):
        if audit.count(name) != 1:
            raise PersonalTransactionsValidationFailure(
                f"Expected exactly one {name}; found {audit.count(name)}."
            )
    receipt = action.get("receipt")
    provider = action["preview"]["provider"]
    expected_status = "accepted_by_gmail" if provider == "google" else "accepted_by_microsoft_graph"
    if (
        not isinstance(receipt, dict)
        or receipt.get("provider") != provider
        or receipt.get("status") != expected_status
        or not isinstance(receipt.get("confirmed_at"), str)
    ):
        raise PersonalTransactionsValidationFailure(
            "Provider receipt does not confirm acceptance of the exact approved commitment."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate PA-09 negotiation commitments in controlled staging."
    )
    parser.add_argument("--provider", choices=("google", "microsoft"), default="google")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if (
        not settings.actions_enabled
        or not settings.connector_trust_boundary_enabled
        or not settings.personal_transactions_enabled
    ):
        raise SystemExit(
            "Actions, connector trust boundary and personal transactions must all be enabled in controlled staging."
        )
    if args.provider == "microsoft" and not settings.microsoft_actions_enabled:
        raise SystemExit("Microsoft actions must be enabled to run the Microsoft PA-09 staging probe.")

    expected_operation = f"{args.provider}:negotiation_commitment_email"
    if expected_operation not in settings.transaction_operations:
        raise SystemExit(
            "Controlled staging requires the exact transaction operation in "
            "SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS."
        )

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    counterparty = env_secret("SHUDDHO_STAGING_TRANSACTION_COUNTERPARTY_EMAIL")
    marker = uuid.uuid4().hex[:12]
    payload = expected_payload(counterparty, marker)

    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            authority = request_json(
                client.get(
                    "/api/v1/transaction-authority-manifest",
                    headers=auth(token),
                ),
                "read transaction authority manifest",
            )
            validate_transaction_authority(authority, args.provider)

            listed = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list staging connections",
            )
            if listed.get("personal_transactions_enabled") is not True:
                raise PersonalTransactionsValidationFailure(
                    "Deployed PA-09 transaction capability is not enabled."
                )
            connections = listed.get("connections")
            if not isinstance(connections, list):
                raise PersonalTransactionsValidationFailure("Connection list has an unexpected shape.")
            connection = connection_for(connections, args.provider)

            prepared = request_json(
                client.post(
                    "/api/v1/actions",
                    headers=auth(token) | {"Idempotency-Key": "live-pa09-" + uuid.uuid4().hex},
                    json={"connection_id": connection["id"], "payload": payload},
                ),
                "prepare PA-09 transaction",
                expected=201,
            )
            validate_prepared(prepared, connection, payload)

            unchanged = request_json(
                client.get(f"/api/v1/actions/{prepared['id']}", headers=auth(token)),
                "read unapproved PA-09 transaction",
            )
            if unchanged.get("state") != "awaiting_approval":
                raise PersonalTransactionsValidationFailure("PA-09 transaction auto-approved or executed.")

            rejected = client.post(
                f"/api/v1/actions/{prepared['id']}/approve",
                headers=auth(token),
                json={"preview_hash": wrong_hash(prepared["preview_hash"])},
            )
            if rejected.status_code != 409:
                raise PersonalTransactionsValidationFailure("Wrong-hash PA-09 approval was not rejected.")

            request_json(
                client.post(
                    f"/api/v1/actions/{prepared['id']}/approve",
                    headers=auth(token),
                    json={"preview_hash": prepared["preview_hash"]},
                ),
                "approve PA-09 transaction",
                expected=202,
            )
            completed = wait_terminal(client, token, prepared["id"], args.timeout)
            validate_completion(completed, prepared)

        evidence: dict = {}
        if args.base_evidence:
            loaded = json.loads(args.base_evidence.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise PersonalTransactionsValidationFailure("Base evidence must be a JSON object.")
            evidence.update(loaded)
        operation = f"{args.provider}:negotiation_commitment_email"
        evidence["personal_transactions"] = passed(
            f"live {args.provider} negotiation commitment passed exact counterparty/message/final-term binding, "
            "no auto-execution, wrong-hash denial, explicit approval, single execution audit, fixed connector path "
            "and provider acceptance receipt; uncertain-outcome no-retry remains fault-injection tested in CI",
            operation,
            evidence.get("personal_transactions"),
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": "passed",
            "feature": "personal_transactions",
            "provider": args.provider,
            "action_id": completed["id"],
        }, indent=2))
    except (PersonalTransactionsValidationFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
