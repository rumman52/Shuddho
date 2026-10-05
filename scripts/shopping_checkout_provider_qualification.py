from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = 1
OPERATION_KIND = "shopping_checkout_create"
REQUIRED_RECEIPT_FIELDS = {
    "provider_order_id",
    "merchant_cart_id",
    "currency",
    "total_minor",
    "status",
    "confirmed_at",
}
FORBIDDEN_PROVIDERS = {"internal", "simulated", "example", "test"}


class ShoppingCheckoutQualificationError(RuntimeError):
    pass


def canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ShoppingCheckoutQualificationError(f"{label} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShoppingCheckoutQualificationError(f"{label} must be an ISO-8601 timestamp.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShoppingCheckoutQualificationError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def clean_https_origin(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ShoppingCheckoutQualificationError(f"{label} must be a clean HTTPS origin.")
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ShoppingCheckoutQualificationError(f"{label} must be a clean HTTPS origin.")
    return clean


def _require_exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ShoppingCheckoutQualificationError(f"{label} has an unexpected schema.")
    return value


def _sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutQualificationError(f"{label} must be a lowercase SHA-256.")
    return value


def _revision(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutQualificationError(
            "adapter_revision must be a full lowercase Git SHA-1."
        )
    return value


def validate_checkout_provider_qualification(
    value: dict,
    *,
    now: datetime | None = None,
    max_probe_age_hours: int = 24,
) -> dict:
    root = _require_exact_keys(
        value,
        {
            "schema_version",
            "provider",
            "adapter_revision",
            "checkout_origin",
            "credential_boundary",
            "idempotency",
            "reconciliation",
            "receipt",
            "privacy",
            "payment_boundary",
            "live_probe",
        },
        "Checkout-provider qualification",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise ShoppingCheckoutQualificationError("Unsupported qualification schema version.")

    provider = root["provider"]
    if (
        not isinstance(provider, str)
        or not re.fullmatch(r"[a-z0-9_]{2,40}", provider)
        or provider in FORBIDDEN_PROVIDERS
    ):
        raise ShoppingCheckoutQualificationError(
            "provider must be a specific production provider identifier."
        )
    adapter_revision = _revision(root["adapter_revision"])
    checkout_origin = clean_https_origin(root["checkout_origin"], "checkout_origin")

    credentials = _require_exact_keys(
        root["credential_boundary"],
        {
            "storage",
            "server_side_only",
            "least_privilege",
            "scopes",
            "raw_payment_credentials",
        },
        "credential_boundary",
    )
    scopes = credentials["scopes"]
    if (
        credentials["storage"] != "credential_broker"
        or credentials["server_side_only"] is not True
        or credentials["least_privilege"] is not True
        or credentials["raw_payment_credentials"] is not False
        or not isinstance(scopes, list)
        or not 1 <= len(scopes) <= 20
        or any(not isinstance(item, str) or not item.strip() or len(item) > 120 for item in scopes)
        or len(scopes) != len(set(scopes))
    ):
        raise ShoppingCheckoutQualificationError(
            "Credential boundary is not least-privilege, brokered, server-side, and payment-secret free."
        )

    idempotency = _require_exact_keys(
        root["idempotency"],
        {"supported", "key_scope", "duplicate_result"},
        "idempotency",
    )
    if (
        idempotency["supported"] is not True
        or idempotency["key_scope"] != "checkout_binding"
        or idempotency["duplicate_result"] != "same_order_or_lookup"
    ):
        raise ShoppingCheckoutQualificationError(
            "Provider checkout must support binding-scoped idempotency with deterministic duplicate handling."
        )

    reconciliation = _require_exact_keys(
        root["reconciliation"],
        {
            "supported",
            "lookup_keys",
            "outcome_unknown_policy",
            "blind_retry",
        },
        "reconciliation",
    )
    lookup_keys = reconciliation["lookup_keys"]
    if (
        reconciliation["supported"] is not True
        or not isinstance(lookup_keys, list)
        or "idempotency_key" not in lookup_keys
        or "provider_order_id" not in lookup_keys
        or len(lookup_keys) != len(set(lookup_keys))
        or reconciliation["outcome_unknown_policy"] != "lookup_before_retry"
        or reconciliation["blind_retry"] is not False
    ):
        raise ShoppingCheckoutQualificationError(
            "Provider checkout must support lookup-based reconciliation and forbid blind retry."
        )

    receipt = _require_exact_keys(
        root["receipt"],
        {"readback_supported", "exact_fields", "confirmed_status"},
        "receipt",
    )
    exact_fields = receipt["exact_fields"]
    if (
        receipt["readback_supported"] is not True
        or not isinstance(exact_fields, list)
        or set(exact_fields) != REQUIRED_RECEIPT_FIELDS
        or len(exact_fields) != len(REQUIRED_RECEIPT_FIELDS)
        or receipt["confirmed_status"] != "confirmed"
    ):
        raise ShoppingCheckoutQualificationError(
            "Provider receipt readback does not exactly satisfy the TX-13 receipt contract."
        )

    privacy = _require_exact_keys(
        root["privacy"],
        {
            "sends_only_required_fields",
            "secrets_in_logs",
            "payment_instrument_to_shuddho",
            "identity_model",
        },
        "privacy",
    )
    if (
        privacy["sends_only_required_fields"] is not True
        or privacy["secrets_in_logs"] is not False
        or privacy["payment_instrument_to_shuddho"] is not False
        or privacy["identity_model"] not in {
            "merchant_account",
            "merchant_hosted_user_present",
        }
    ):
        raise ShoppingCheckoutQualificationError(
            "Provider privacy boundary is not compatible with bounded checkout."
        )

    payment = _require_exact_keys(
        root["payment_boundary"],
        {
            "mode",
            "shuddho_charges",
            "stores_payment_instrument",
            "requires_user_present",
        },
        "payment_boundary",
    )
    if (
        payment["mode"] != "merchant_hosted_user_present"
        or payment["shuddho_charges"] is not False
        or payment["stores_payment_instrument"] is not False
        or payment["requires_user_present"] is not True
    ):
        raise ShoppingCheckoutQualificationError(
            "TX-14 requires merchant-hosted, user-present payment with no Shuddho payment authority."
        )

    probe = _require_exact_keys(
        root["live_probe"],
        {
            "status",
            "environment",
            "verified_at",
            "source_revision",
            "checkout_origin",
            "idempotency_passed",
            "reconciliation_passed",
            "receipt_match_passed",
            "privacy_passed",
            "payment_boundary_passed",
            "evidence_sha256",
        },
        "live_probe",
    )
    if probe["status"] != "passed" or probe["environment"] != "staging":
        raise ShoppingCheckoutQualificationError(
            "A passed staging live probe is required."
        )
    if probe["source_revision"] != adapter_revision:
        raise ShoppingCheckoutQualificationError(
            "Live probe revision does not match the reviewed adapter revision."
        )
    if clean_https_origin(probe["checkout_origin"], "live_probe.checkout_origin") != checkout_origin:
        raise ShoppingCheckoutQualificationError(
            "Live probe checkout origin does not match the reviewed provider origin."
        )
    for key in (
        "idempotency_passed",
        "reconciliation_passed",
        "receipt_match_passed",
        "privacy_passed",
        "payment_boundary_passed",
    ):
        if probe[key] is not True:
            raise ShoppingCheckoutQualificationError(
                f"Live probe did not pass {key}."
            )
    evidence_sha256 = _sha(probe["evidence_sha256"], "live_probe.evidence_sha256")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    verified_at = parse_time(probe["verified_at"], "live_probe.verified_at")
    age = current - verified_at
    if age < -timedelta(minutes=1):
        raise ShoppingCheckoutQualificationError("Live probe timestamp is from the future.")
    if age > timedelta(hours=max(1, max_probe_age_hours)):
        raise ShoppingCheckoutQualificationError("Live probe evidence is stale.")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "operation": f"{provider}:{OPERATION_KIND}",
        "adapter_revision": adapter_revision,
        "checkout_origin": checkout_origin,
        "credential_boundary": {
            **credentials,
            "scopes": sorted(scopes),
        },
        "idempotency": idempotency,
        "reconciliation": {
            **reconciliation,
            "lookup_keys": sorted(lookup_keys),
        },
        "receipt": {
            **receipt,
            "exact_fields": sorted(exact_fields),
        },
        "privacy": privacy,
        "payment_boundary": payment,
        "live_probe": {
            **probe,
            "evidence_sha256": evidence_sha256,
            "verified_at": verified_at.isoformat(),
            "checkout_origin": checkout_origin,
        },
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "payment_authority": False,
    }
    normalized["qualification_sha256"] = canonical_sha256(normalized)
    return normalized


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ShoppingCheckoutQualificationError(
            f"Could not read qualification evidence: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ShoppingCheckoutQualificationError(
            "Qualification evidence must contain a JSON object."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate TX-14 shopping checkout provider qualification evidence. "
            "This never registers or enables the checkout action."
        )
    )
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--max-probe-age-hours", type=int, default=24)
    args = parser.parse_args()
    try:
        result = validate_checkout_provider_qualification(
            load_json(args.evidence),
            max_probe_age_hours=args.max_probe_age_hours,
        )
    except ShoppingCheckoutQualificationError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    print(json.dumps({"status": "qualified_contract_only", **result}, indent=2))


if __name__ == "__main__":
    main()
