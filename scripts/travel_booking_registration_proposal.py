from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
ACTION_KIND = "travel_booking_create"
CONTRACT_VERSION = 1
FORBIDDEN_PROVIDERS = {"internal", "simulated", "example", "test"}


class TravelBookingRegistrationProposalError(RuntimeError):
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
        raise TravelBookingRegistrationProposalError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TravelBookingRegistrationProposalError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TravelBookingRegistrationProposalError(
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
        raise TravelBookingRegistrationProposalError(
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
        raise TravelBookingRegistrationProposalError(
            f"{label} must be a full lowercase Git SHA-1."
        )
    return value


def _exact_dict(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise TravelBookingRegistrationProposalError(
            f"{label} has an unexpected schema."
        )
    return value


def validate_tx19_qualification(
    value: dict,
    *,
    now: datetime | None = None,
    max_qualification_age_hours: int = 24,
) -> dict:
    expected = {
        "schema_version",
        "provider",
        "operation",
        "contract_version",
        "adapter_revision",
        "booking_origin",
        "supported_travel_kinds",
        "credential_boundary",
        "traveler_data_boundary",
        "idempotency",
        "reconciliation",
        "receipt",
        "privacy",
        "payment_boundary",
        "live_probe",
        "registration_authority",
        "operation_allowlisted",
        "external_action_registered",
        "identity_authority",
        "payment_authority",
        "qualification_sha256",
    }
    qualification = _exact_dict(value, expected, "TX-19 qualification")
    if qualification["schema_version"] != 1:
        raise TravelBookingRegistrationProposalError(
            "TX-19 qualification schema version is unsupported."
        )
    if qualification["contract_version"] != CONTRACT_VERSION:
        raise TravelBookingRegistrationProposalError(
            "TX-19 does not target the supported TX-18 travel contract."
        )

    provider = qualification["provider"]
    if (
        not isinstance(provider, str)
        or not re.fullmatch(r"[a-z0-9_]{2,40}", provider)
        or provider in FORBIDDEN_PROVIDERS
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 provider identifier is invalid."
        )
    if qualification["operation"] != f"{provider}:{ACTION_KIND}":
        raise TravelBookingRegistrationProposalError(
            "TX-19 operation does not match the provider travel-booking operation."
        )

    _revision(qualification["adapter_revision"], "TX-19 adapter_revision")

    kinds = qualification["supported_travel_kinds"]
    if (
        not isinstance(kinds, list)
        or len(kinds) != 1
        or kinds[0] not in {"flight", "lodging"}
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 qualification must cover exactly one travel kind."
        )
    travel_kind = kinds[0]

    if (
        qualification["registration_authority"] is not False
        or qualification["operation_allowlisted"] is not False
        or qualification["external_action_registered"] is not False
        or qualification["identity_authority"] is not False
        or qualification["payment_authority"] is not False
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 evidence unexpectedly grants runtime authority."
        )

    traveler = _exact_dict(
        qualification["traveler_data_boundary"],
        {
            "required_fields",
            "shuddho_transmitted_fields",
            "provider_hosted_fields",
            "document_images_to_shuddho",
            "payment_instrument_to_shuddho",
            "optional_fields_default_off",
        },
        "TX-19 traveler_data_boundary",
    )
    required = traveler["required_fields"]
    shuddho = traveler["shuddho_transmitted_fields"]
    hosted = traveler["provider_hosted_fields"]
    if (
        not isinstance(required, list)
        or not isinstance(shuddho, list)
        or not isinstance(hosted, list)
        or "legal_name" not in required
        or set(required) != set(shuddho) | set(hosted)
        or set(shuddho) & set(hosted)
        or traveler["document_images_to_shuddho"] is not False
        or traveler["payment_instrument_to_shuddho"] is not False
        or traveler["optional_fields_default_off"] is not True
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 traveler-data boundary is not the reviewed minimized partition."
        )

    normalized_traveler = {
        **traveler,
        "required_fields": sorted(required),
        "shuddho_transmitted_fields": sorted(shuddho),
        "provider_hosted_fields": sorted(hosted),
    }
    traveler_data_boundary_sha256 = canonical_sha256(normalized_traveler)

    payment = qualification["payment_boundary"]
    if (
        not isinstance(payment, dict)
        or payment.get("mode") != "provider_hosted_user_present"
        or payment.get("shuddho_charges") is not False
        or payment.get("stores_payment_instrument") is not False
        or payment.get("requires_user_present") is not True
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 payment boundary is not provider-hosted and user-present."
        )

    receipt = qualification["receipt"]
    if (
        not isinstance(receipt, dict)
        or receipt.get("readback_supported") is not True
        or receipt.get("confirmed_status") != "confirmed"
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 qualification does not prove provider receipt readback."
        )

    probe = qualification["live_probe"]
    if (
        not isinstance(probe, dict)
        or probe.get("status") != "passed"
        or probe.get("environment") != "staging"
        or probe.get("travel_kind") != travel_kind
        or probe.get("traveler_minimization_passed") is not True
        or probe.get("idempotency_passed") is not True
        or probe.get("reconciliation_passed") is not True
        or probe.get("receipt_match_passed") is not True
        or probe.get("privacy_passed") is not True
        or probe.get("payment_boundary_passed") is not True
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 live probe is not a passing staging qualification."
        )
    if (
        _sha256(
            probe.get("traveler_data_boundary_sha256"),
            "TX-19 live_probe.traveler_data_boundary_sha256",
        )
        != traveler_data_boundary_sha256
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 live probe is not bound to the current traveler-data boundary."
        )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    verified_at = parse_time(
        probe.get("verified_at"),
        "TX-19 live_probe.verified_at",
    )
    age = current - verified_at
    if age < -timedelta(minutes=1):
        raise TravelBookingRegistrationProposalError(
            "TX-19 live probe timestamp is from the future."
        )
    if age > timedelta(hours=max(1, max_qualification_age_hours)):
        raise TravelBookingRegistrationProposalError(
            "TX-19 qualification evidence is stale."
        )

    stored_digest = _sha256(
        qualification["qualification_sha256"],
        "TX-19 qualification_sha256",
    )
    unsigned = dict(qualification)
    unsigned.pop("qualification_sha256")
    if stored_digest != canonical_sha256(unsigned):
        raise TravelBookingRegistrationProposalError(
            "TX-19 qualification digest does not match its normalized evidence."
        )
    return qualification


def compile_travel_registration_proposal(
    qualification: dict,
    review: dict,
    *,
    now: datetime | None = None,
    max_review_age_days: int = 7,
    max_qualification_age_hours: int = 24,
) -> dict:
    q = validate_tx19_qualification(
        qualification,
        now=now,
        max_qualification_age_hours=max_qualification_age_hours,
    )
    reviewed = _exact_dict(
        review,
        {
            "schema_version",
            "provider",
            "operation",
            "adapter_revision",
            "booking_origin",
            "travel_kind",
            "traveler_data_boundary_sha256",
            "qualification_sha256",
            "action_contract_version",
            "change_reference",
            "reviewed_at",
            "reviewer_reference",
        },
        "Travel booking registration review",
    )
    if reviewed["schema_version"] != SCHEMA_VERSION:
        raise TravelBookingRegistrationProposalError(
            "Unsupported registration-review schema version."
        )

    travel_kind = q["supported_travel_kinds"][0]
    traveler_data_boundary_sha256 = q["live_probe"][
        "traveler_data_boundary_sha256"
    ]
    exact_matches = {
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "booking_origin": q["booking_origin"],
        "travel_kind": travel_kind,
        "traveler_data_boundary_sha256": traveler_data_boundary_sha256,
        "qualification_sha256": q["qualification_sha256"],
    }
    for field, expected in exact_matches.items():
        if reviewed[field] != expected:
            raise TravelBookingRegistrationProposalError(
                f"Registration review {field} does not match TX-19 qualification."
            )

    if reviewed["action_contract_version"] != CONTRACT_VERSION:
        raise TravelBookingRegistrationProposalError(
            "TX-18 travel booking contract version must remain 1 for this proposal."
        )

    for field in ("change_reference", "reviewer_reference"):
        value = reviewed[field]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 300
            or any(ord(char) < 32 for char in value)
        ):
            raise TravelBookingRegistrationProposalError(
                f"Registration review {field} is invalid."
            )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reviewed_at = parse_time(reviewed["reviewed_at"], "reviewed_at")
    age = current - reviewed_at
    if age < -timedelta(minutes=1):
        raise TravelBookingRegistrationProposalError(
            "Registration review timestamp is from the future."
        )
    if age > timedelta(days=max(1, max_review_age_days)):
        raise TravelBookingRegistrationProposalError(
            "Registration review is stale."
        )

    proposal = {
        "schema_version": SCHEMA_VERSION,
        "status": "eligible_for_provider_implementation_review",
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "booking_origin": q["booking_origin"],
        "travel_kind": travel_kind,
        "qualification_sha256": q["qualification_sha256"],
        "action_contract": {
            "kind": ACTION_KIND,
            "version": CONTRACT_VERSION,
            "source": "TX-18",
        },
        "credential_scopes": sorted(q["credential_boundary"]["scopes"]),
        "traveler_data_boundary": q["traveler_data_boundary"],
        "traveler_data_boundary_sha256": traveler_data_boundary_sha256,
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
        "identity_authority": False,
        "payment_authority": False,
    }
    proposal["registration_proposal_sha256"] = canonical_sha256(proposal)
    return proposal


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise TravelBookingRegistrationProposalError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise TravelBookingRegistrationProposalError(
            f"{label} must contain a JSON object."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile an inert TX-20 travel booking registration proposal from "
            "exact TX-19 qualification evidence. This never changes runtime authority."
        )
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--max-review-age-days", type=int, default=7)
    parser.add_argument("--max-qualification-age-hours", type=int, default=24)
    args = parser.parse_args()

    try:
        proposal = compile_travel_registration_proposal(
            load_json(args.qualification, "TX-19 qualification"),
            load_json(args.review, "travel booking registration review"),
            max_review_age_days=args.max_review_age_days,
            max_qualification_age_hours=args.max_qualification_age_hours,
        )
    except TravelBookingRegistrationProposalError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None

    print(json.dumps(proposal, indent=2))


if __name__ == "__main__":
    main()
