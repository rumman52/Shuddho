from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = 1
ACTION_KIND = "travel_booking_create"
CONTRACT_VERSION = 1
FORBIDDEN_PROVIDERS = {"internal", "simulated", "example", "test"}
REQUIRED_RECEIPT_FIELDS = {
    "provider_booking_id",
    "provider_quote_id",
    "travel_kind",
    "currency",
    "total_minor",
    "status",
    "confirmed_at",
}
ALLOWED_TRAVELER_FIELDS = {
    "legal_name",
    "date_of_birth",
    "gender_marker",
    "nationality",
    "email",
    "phone",
    "passport_number",
    "passport_country",
    "passport_expiry",
    "known_traveler_number",
    "redress_number",
    "loyalty_program",
    "loyalty_number",
}


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


def _clean_https_origin(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TravelBookingRegistrationProposalError(
            f"{label} must be a clean HTTPS origin."
        )
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
        raise TravelBookingRegistrationProposalError(
            f"{label} must be a clean HTTPS origin."
        )
    return clean


def _canonical_unique_strings(
    value: object,
    label: str,
    *,
    min_items: int = 0,
    max_items: int = 100,
) -> list[str]:
    if (
        not isinstance(value, list)
        or not min_items <= len(value) <= max_items
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
        or value != sorted(value)
    ):
        raise TravelBookingRegistrationProposalError(
            f"{label} must be a canonical sorted list of unique strings."
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

    adapter_revision = _revision(
        qualification["adapter_revision"],
        "TX-19 adapter_revision",
    )
    booking_origin = _clean_https_origin(
        qualification["booking_origin"],
        "TX-19 booking_origin",
    )

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

    credentials = _exact_dict(
        qualification["credential_boundary"],
        {
            "storage",
            "server_side_only",
            "least_privilege",
            "scopes",
            "raw_payment_credentials",
        },
        "TX-19 credential_boundary",
    )
    scopes = _canonical_unique_strings(
        credentials["scopes"],
        "TX-19 credential scopes",
        min_items=1,
        max_items=20,
    )
    if (
        credentials["storage"] != "credential_broker"
        or credentials["server_side_only"] is not True
        or credentials["least_privilege"] is not True
        or credentials["raw_payment_credentials"] is not False
        or any(len(item) > 120 for item in scopes)
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 credential boundary is not brokered, server-side and least-privilege."
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
    required = _canonical_unique_strings(
        traveler["required_fields"],
        "TX-19 required traveler fields",
        min_items=1,
    )
    shuddho = _canonical_unique_strings(
        traveler["shuddho_transmitted_fields"],
        "TX-19 Shuddho traveler fields",
    )
    hosted = _canonical_unique_strings(
        traveler["provider_hosted_fields"],
        "TX-19 provider-hosted traveler fields",
    )
    declared = set(required) | set(shuddho) | set(hosted)
    if (
        "legal_name" not in required
        or not declared <= ALLOWED_TRAVELER_FIELDS
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

    idempotency = _exact_dict(
        qualification["idempotency"],
        {"supported", "key_scope", "duplicate_result"},
        "TX-19 idempotency",
    )
    if (
        idempotency["supported"] is not True
        or idempotency["key_scope"] != "booking_binding"
        or idempotency["duplicate_result"] != "same_booking_or_lookup"
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 idempotency contract is not binding-scoped and deterministic."
        )

    reconciliation = _exact_dict(
        qualification["reconciliation"],
        {
            "supported",
            "lookup_keys",
            "outcome_unknown_policy",
            "blind_retry",
        },
        "TX-19 reconciliation",
    )
    lookup_keys = _canonical_unique_strings(
        reconciliation["lookup_keys"],
        "TX-19 reconciliation lookup keys",
        min_items=2,
    )
    if (
        reconciliation["supported"] is not True
        or set(lookup_keys) != {"idempotency_key", "provider_booking_id"}
        or reconciliation["outcome_unknown_policy"] != "lookup_before_retry"
        or reconciliation["blind_retry"] is not False
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 reconciliation contract does not require lookup-before-retry."
        )

    receipt = _exact_dict(
        qualification["receipt"],
        {"readback_supported", "exact_fields", "confirmed_status"},
        "TX-19 receipt",
    )
    receipt_fields = _canonical_unique_strings(
        receipt["exact_fields"],
        "TX-19 receipt fields",
        min_items=len(REQUIRED_RECEIPT_FIELDS),
        max_items=len(REQUIRED_RECEIPT_FIELDS),
    )
    if (
        receipt["readback_supported"] is not True
        or set(receipt_fields) != REQUIRED_RECEIPT_FIELDS
        or receipt["confirmed_status"] != "confirmed"
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 qualification does not prove the exact TX-18 receipt contract."
        )

    privacy = _exact_dict(
        qualification["privacy"],
        {
            "sends_only_required_fields",
            "secrets_in_logs",
            "retains_traveler_data_in_logs",
            "provider_hosted_collection_supported",
        },
        "TX-19 privacy",
    )
    if (
        privacy["sends_only_required_fields"] is not True
        or privacy["secrets_in_logs"] is not False
        or privacy["retains_traveler_data_in_logs"] is not False
        or privacy["provider_hosted_collection_supported"] is not True
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 privacy boundary is not compatible with bounded travel booking."
        )

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

    probe = _exact_dict(
        qualification["live_probe"],
        {
            "status",
            "environment",
            "verified_at",
            "source_revision",
            "booking_origin",
            "travel_kind",
            "traveler_data_boundary_sha256",
            "traveler_minimization_passed",
            "idempotency_passed",
            "reconciliation_passed",
            "receipt_match_passed",
            "privacy_passed",
            "payment_boundary_passed",
            "evidence_sha256",
        },
        "TX-19 live_probe",
    )
    if (
        probe["status"] != "passed"
        or probe["environment"] != "staging"
        or probe["source_revision"] != adapter_revision
        or _clean_https_origin(
            probe["booking_origin"],
            "TX-19 live_probe.booking_origin",
        ) != booking_origin
        or probe["travel_kind"] != travel_kind
        or probe["traveler_minimization_passed"] is not True
        or probe["idempotency_passed"] is not True
        or probe["reconciliation_passed"] is not True
        or probe["receipt_match_passed"] is not True
        or probe["privacy_passed"] is not True
        or probe["payment_boundary_passed"] is not True
    ):
        raise TravelBookingRegistrationProposalError(
            "TX-19 live probe is not a passing staging qualification for this exact adapter and origin."
        )
    _sha256(probe["evidence_sha256"], "TX-19 live_probe.evidence_sha256")
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
