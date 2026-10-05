from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
ACTION_KIND = "shopping_checkout_create"


class ShoppingCheckoutRegistrationProposalError(RuntimeError):
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
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} must include a timezone."
        )
    return parsed.astimezone(timezone.utc)


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} must be a lowercase SHA-256."
        )
    return value


def _revision(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} must be a full lowercase Git SHA-1."
        )
    return value


def _exact_dict(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} has an unexpected schema."
        )
    return value


def validate_tx14_qualification(value: dict) -> dict:
    expected = {
        "schema_version",
        "provider",
        "operation",
        "adapter_revision",
        "checkout_origin",
        "credential_boundary",
        "idempotency",
        "reconciliation",
        "receipt",
        "privacy",
        "payment_boundary",
        "live_probe",
        "registration_authority",
        "operation_allowlisted",
        "external_action_registered",
        "payment_authority",
        "qualification_sha256",
    }
    qualification = _exact_dict(value, expected, "TX-14 qualification")
    if qualification["schema_version"] != 1:
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 qualification schema version is unsupported."
        )

    provider = qualification["provider"]
    if (
        not isinstance(provider, str)
        or not re.fullmatch(r"[a-z0-9_]{2,40}", provider)
    ):
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 provider identifier is invalid."
        )
    expected_operation = f"{provider}:{ACTION_KIND}"
    if qualification["operation"] != expected_operation:
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 operation does not match the provider checkout operation."
        )

    _revision(qualification["adapter_revision"], "TX-14 adapter_revision")
    if (
        qualification["registration_authority"] is not False
        or qualification["operation_allowlisted"] is not False
        or qualification["external_action_registered"] is not False
        or qualification["payment_authority"] is not False
    ):
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 evidence unexpectedly grants runtime authority."
        )

    payment = qualification["payment_boundary"]
    if (
        not isinstance(payment, dict)
        or payment.get("mode") != "merchant_hosted_user_present"
        or payment.get("shuddho_charges") is not False
        or payment.get("stores_payment_instrument") is not False
        or payment.get("requires_user_present") is not True
    ):
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 payment boundary is not the required merchant-hosted user-present model."
        )

    receipt = qualification["receipt"]
    if not isinstance(receipt, dict) or receipt.get("readback_supported") is not True:
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 qualification does not prove provider receipt readback."
        )

    stored_digest = _sha256(
        qualification["qualification_sha256"],
        "TX-14 qualification_sha256",
    )
    unsigned = dict(qualification)
    unsigned.pop("qualification_sha256")
    recomputed = canonical_sha256(unsigned)
    if stored_digest != recomputed:
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-14 qualification digest does not match its normalized evidence."
        )
    return qualification


def compile_registration_proposal(
    qualification: dict,
    review: dict,
    *,
    now: datetime | None = None,
    max_review_age_days: int = 7,
) -> dict:
    q = validate_tx14_qualification(qualification)
    reviewed = _exact_dict(
        review,
        {
            "schema_version",
            "provider",
            "operation",
            "adapter_revision",
            "checkout_origin",
            "qualification_sha256",
            "action_contract_version",
            "change_reference",
            "reviewed_at",
            "reviewer_reference",
        },
        "Checkout registration review",
    )
    if reviewed["schema_version"] != SCHEMA_VERSION:
        raise ShoppingCheckoutRegistrationProposalError(
            "Unsupported registration-review schema version."
        )

    exact_matches = {
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "checkout_origin": q["checkout_origin"],
        "qualification_sha256": q["qualification_sha256"],
    }
    for field, expected in exact_matches.items():
        if reviewed[field] != expected:
            raise ShoppingCheckoutRegistrationProposalError(
                f"Registration review {field} does not match TX-14 qualification."
            )

    if reviewed["action_contract_version"] != 1:
        raise ShoppingCheckoutRegistrationProposalError(
            "TX-13 checkout contract version must remain 1 for this proposal."
        )
    for field in ("change_reference", "reviewer_reference"):
        value = reviewed[field]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 300
            or any(ord(char) < 32 for char in value)
        ):
            raise ShoppingCheckoutRegistrationProposalError(
                f"Registration review {field} is invalid."
            )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reviewed_at = parse_time(reviewed["reviewed_at"], "reviewed_at")
    age = current - reviewed_at
    if age < -timedelta(minutes=1):
        raise ShoppingCheckoutRegistrationProposalError(
            "Registration review timestamp is from the future."
        )
    if age > timedelta(days=max(1, max_review_age_days)):
        raise ShoppingCheckoutRegistrationProposalError(
            "Registration review is stale."
        )

    proposal = {
        "schema_version": SCHEMA_VERSION,
        "status": "eligible_for_provider_implementation_review",
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "checkout_origin": q["checkout_origin"],
        "qualification_sha256": q["qualification_sha256"],
        "action_contract": {
            "kind": ACTION_KIND,
            "version": 1,
            "source": "TX-13",
        },
        "credential_scopes": sorted(q["credential_boundary"]["scopes"]),
        "idempotency": q["idempotency"],
        "reconciliation": q["reconciliation"],
        "receipt": q["receipt"],
        "privacy": q["privacy"],
        "payment_boundary": q["payment_boundary"],
        "change_reference": reviewed["change_reference"].strip(),
        "reviewed_at": reviewed_at.isoformat(),
        "reviewer_reference": reviewed["reviewer_reference"].strip(),
        "registry_change_required": True,
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "payment_authority": False,
    }
    proposal["registration_proposal_sha256"] = canonical_sha256(proposal)
    return proposal


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ShoppingCheckoutRegistrationProposalError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ShoppingCheckoutRegistrationProposalError(
            f"{label} must contain a JSON object."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile an inert TX-15 checkout registration proposal from exact "
            "TX-14 qualification evidence. This never changes runtime authority."
        )
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--max-review-age-days", type=int, default=7)
    args = parser.parse_args()

    try:
        proposal = compile_registration_proposal(
            load_json(args.qualification, "TX-14 qualification"),
            load_json(args.review, "checkout registration review"),
            max_review_age_days=args.max_review_age_days,
        )
    except ShoppingCheckoutRegistrationProposalError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None

    print(json.dumps(proposal, indent=2))


if __name__ == "__main__":
    main()
