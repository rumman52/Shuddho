from __future__ import annotations

import hashlib
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse


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


class TravelBookingAdapterAdmissionError(RuntimeError):
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


def _exact_dict(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise TravelBookingAdapterAdmissionError(
            f"{label} has an unexpected schema."
        )
    return value


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TravelBookingAdapterAdmissionError(
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
        raise TravelBookingAdapterAdmissionError(
            f"{label} must be a full lowercase Git SHA-1."
        )
    return value


def _clean_https_origin(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TravelBookingAdapterAdmissionError(
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
        raise TravelBookingAdapterAdmissionError(
            f"{label} must be a clean HTTPS origin."
        )
    return clean


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise TravelBookingAdapterAdmissionError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TravelBookingAdapterAdmissionError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TravelBookingAdapterAdmissionError(
            f"{label} must include a timezone."
        )
    return parsed.astimezone(timezone.utc)


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
        raise TravelBookingAdapterAdmissionError(
            f"{label} must be a canonical sorted list of unique strings."
        )
    return value


def _require_exact_async_signature(
    method: object,
    *,
    label: str,
    required: tuple[str, ...],
    optional_none: tuple[str, ...] = (),
) -> None:
    if not inspect.iscoroutinefunction(method):
        raise TravelBookingAdapterAdmissionError(
            f"{label} must be asynchronous."
        )

    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    expected_names = list(required) + list(optional_none)

    if [item.name for item in parameters] != expected_names:
        raise TravelBookingAdapterAdmissionError(
            f"{label} must declare exactly: {', '.join(expected_names)}."
        )

    for item in parameters:
        if item.kind is not inspect.Parameter.KEYWORD_ONLY:
            raise TravelBookingAdapterAdmissionError(
                f"{label} parameters must be keyword-only."
            )
        if item.name in required and item.default is not inspect.Parameter.empty:
            raise TravelBookingAdapterAdmissionError(
                f"{label} required parameters cannot define defaults."
            )
        if item.name in optional_none and item.default is not None:
            raise TravelBookingAdapterAdmissionError(
                f"{label} optional lookup parameters must default to None."
            )


@runtime_checkable
class TravelBookingProviderAdapter(Protocol):
    """Structural contract for a future real travel-booking adapter.

    The protocol is deliberately not connected to the runtime action registry.
    TX-21 admission proves only that code-owned adapter metadata matches an
    exact TX-20 registration proposal.
    """

    provider_name: str
    adapter_revision: str
    booking_origin: str
    travel_kind: str
    credential_scopes: frozenset[str]
    action_kind: str
    contract_version: int
    traveler_data_boundary_sha256: str
    required_traveler_fields: frozenset[str]
    shuddho_transmitted_fields: frozenset[str]
    provider_hosted_fields: frozenset[str]
    supports_idempotency: bool
    supports_lookup_by_idempotency_key: bool
    supports_lookup_by_provider_booking_id: bool
    supports_provider_hosted_collection: bool
    payment_mode: str
    receives_payment_instrument: bool
    receives_document_images: bool
    retains_traveler_data_in_logs: bool

    async def create_booking(
        self,
        *,
        preview: dict,
        traveler_data: dict,
        idempotency_key: str,
    ) -> dict:
        ...

    async def lookup_booking(
        self,
        *,
        idempotency_key: str | None = None,
        provider_booking_id: str | None = None,
    ) -> dict | None:
        ...


def validate_registration_proposal(
    value: dict,
    *,
    now: datetime | None = None,
    max_review_age_days: int = 7,
) -> dict:
    proposal = _exact_dict(
        value,
        {
            "schema_version",
            "status",
            "provider",
            "operation",
            "adapter_revision",
            "booking_origin",
            "travel_kind",
            "qualification_sha256",
            "action_contract",
            "credential_scopes",
            "traveler_data_boundary",
            "traveler_data_boundary_sha256",
            "idempotency",
            "reconciliation",
            "receipt",
            "privacy",
            "payment_boundary",
            "change_reference",
            "reviewed_at",
            "reviewer_reference",
            "registry_change_required",
            "registration_authority",
            "operation_allowlisted",
            "external_action_registered",
            "runtime_enabled",
            "identity_authority",
            "payment_authority",
            "registration_proposal_sha256",
        },
        "TX-20 registration proposal",
    )

    if proposal["schema_version"] != 1:
        raise TravelBookingAdapterAdmissionError(
            "TX-20 registration proposal schema version is unsupported."
        )
    if proposal["status"] != "eligible_for_provider_implementation_review":
        raise TravelBookingAdapterAdmissionError(
            "TX-20 proposal is not eligible for implementation review."
        )

    provider = proposal["provider"]
    if (
        not isinstance(provider, str)
        or not re.fullmatch(r"[a-z0-9_]{2,40}", provider)
        or provider in FORBIDDEN_PROVIDERS
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 provider identifier is not a concrete provider."
        )
    if proposal["operation"] != f"{provider}:{ACTION_KIND}":
        raise TravelBookingAdapterAdmissionError(
            "TX-20 operation does not match the provider travel-booking action."
        )

    _revision(proposal["adapter_revision"], "TX-20 adapter_revision")
    proposal["booking_origin"] = _clean_https_origin(
        proposal["booking_origin"],
        "TX-20 booking_origin",
    )
    _sha256(proposal["qualification_sha256"], "TX-20 qualification_sha256")

    if proposal["travel_kind"] not in {"flight", "lodging"}:
        raise TravelBookingAdapterAdmissionError(
            "TX-20 proposal must bind exactly one supported travel kind."
        )

    action_contract = _exact_dict(
        proposal["action_contract"],
        {"kind", "version", "source"},
        "TX-20 action_contract",
    )
    if action_contract != {
        "kind": ACTION_KIND,
        "version": CONTRACT_VERSION,
        "source": "TX-18",
    }:
        raise TravelBookingAdapterAdmissionError(
            "TX-20 action contract is not the supported TX-18 contract."
        )

    scopes = _canonical_unique_strings(
        proposal["credential_scopes"],
        "TX-20 credential scopes",
        min_items=1,
        max_items=20,
    )
    if any(len(item) > 120 for item in scopes):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 credential scope is too long."
        )

    traveler = _exact_dict(
        proposal["traveler_data_boundary"],
        {
            "required_fields",
            "shuddho_transmitted_fields",
            "provider_hosted_fields",
            "document_images_to_shuddho",
            "payment_instrument_to_shuddho",
            "optional_fields_default_off",
        },
        "TX-20 traveler_data_boundary",
    )
    required = _canonical_unique_strings(
        traveler["required_fields"],
        "TX-20 required traveler fields",
        min_items=1,
    )
    shuddho = _canonical_unique_strings(
        traveler["shuddho_transmitted_fields"],
        "TX-20 Shuddho traveler fields",
    )
    hosted = _canonical_unique_strings(
        traveler["provider_hosted_fields"],
        "TX-20 provider-hosted traveler fields",
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
        raise TravelBookingAdapterAdmissionError(
            "TX-20 traveler-data boundary is not the minimized reviewed partition."
        )

    normalized_traveler = {
        **traveler,
        "required_fields": list(required),
        "shuddho_transmitted_fields": list(shuddho),
        "provider_hosted_fields": list(hosted),
    }
    traveler_digest = _sha256(
        proposal["traveler_data_boundary_sha256"],
        "TX-20 traveler_data_boundary_sha256",
    )
    if traveler_digest != canonical_sha256(normalized_traveler):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 traveler-data boundary digest does not match its contents."
        )

    idempotency = _exact_dict(
        proposal["idempotency"],
        {"supported", "key_scope", "duplicate_result"},
        "TX-20 idempotency",
    )
    if (
        idempotency["supported"] is not True
        or idempotency["key_scope"] != "booking_binding"
        or idempotency["duplicate_result"] != "same_booking_or_lookup"
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 does not bind the required travel-booking idempotency contract."
        )

    reconciliation = _exact_dict(
        proposal["reconciliation"],
        {"supported", "lookup_keys", "outcome_unknown_policy", "blind_retry"},
        "TX-20 reconciliation",
    )
    lookup_keys = _canonical_unique_strings(
        reconciliation["lookup_keys"],
        "TX-20 reconciliation lookup keys",
        min_items=2,
        max_items=2,
    )
    if (
        reconciliation["supported"] is not True
        or set(lookup_keys) != {"idempotency_key", "provider_booking_id"}
        or reconciliation["outcome_unknown_policy"] != "lookup_before_retry"
        or reconciliation["blind_retry"] is not False
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 does not bind the required lookup-before-retry contract."
        )

    receipt = _exact_dict(
        proposal["receipt"],
        {"readback_supported", "exact_fields", "confirmed_status"},
        "TX-20 receipt",
    )
    receipt_fields = _canonical_unique_strings(
        receipt["exact_fields"],
        "TX-20 receipt fields",
        min_items=len(REQUIRED_RECEIPT_FIELDS),
        max_items=len(REQUIRED_RECEIPT_FIELDS),
    )
    if (
        receipt["readback_supported"] is not True
        or set(receipt_fields) != REQUIRED_RECEIPT_FIELDS
        or receipt["confirmed_status"] != "confirmed"
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 receipt contract does not match TX-18."
        )

    privacy = _exact_dict(
        proposal["privacy"],
        {
            "sends_only_required_fields",
            "secrets_in_logs",
            "retains_traveler_data_in_logs",
            "provider_hosted_collection_supported",
        },
        "TX-20 privacy",
    )
    if (
        privacy["sends_only_required_fields"] is not True
        or privacy["secrets_in_logs"] is not False
        or privacy["retains_traveler_data_in_logs"] is not False
        or privacy["provider_hosted_collection_supported"] is not True
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 privacy boundary is not compatible with bounded travel booking."
        )

    payment = _exact_dict(
        proposal["payment_boundary"],
        {
            "mode",
            "shuddho_charges",
            "stores_payment_instrument",
            "requires_user_present",
        },
        "TX-20 payment_boundary",
    )
    if (
        payment["mode"] != "provider_hosted_user_present"
        or payment["shuddho_charges"] is not False
        or payment["stores_payment_instrument"] is not False
        or payment["requires_user_present"] is not True
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 payment boundary is not provider-hosted and user-present."
        )

    if (
        proposal["registry_change_required"] is not True
        or proposal["registration_authority"] is not False
        or proposal["operation_allowlisted"] is not False
        or proposal["external_action_registered"] is not False
        or proposal["runtime_enabled"] is not False
        or proposal["identity_authority"] is not False
        or proposal["payment_authority"] is not False
    ):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 proposal unexpectedly grants runtime travel-booking authority."
        )

    for field in ("change_reference", "reviewer_reference"):
        item = proposal[field]
        if (
            not isinstance(item, str)
            or not item.strip()
            or len(item) > 300
            or any(ord(char) < 32 for char in item)
        ):
            raise TravelBookingAdapterAdmissionError(
                f"TX-20 {field} is invalid."
            )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reviewed_at = _parse_time(proposal["reviewed_at"], "TX-20 reviewed_at")
    age = current - reviewed_at
    if age < -timedelta(minutes=1):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 registration review is from the future."
        )
    if age > timedelta(days=max(1, max_review_age_days)):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 registration review is stale."
        )

    stored_digest = _sha256(
        proposal["registration_proposal_sha256"],
        "TX-20 registration_proposal_sha256",
    )
    unsigned = dict(proposal)
    unsigned.pop("registration_proposal_sha256")
    if stored_digest != canonical_sha256(unsigned):
        raise TravelBookingAdapterAdmissionError(
            "TX-20 registration proposal digest does not match its contents."
        )
    return proposal


def admit_travel_booking_adapter(
    proposal_value: dict,
    adapter: object,
    *,
    now: datetime | None = None,
) -> dict:
    """Admit a concrete travel adapter for isolated implementation tests only.

    Admission performs no provider I/O and grants no runtime registration,
    identity collection authority, or payment authority.
    """

    proposal = validate_registration_proposal(proposal_value, now=now)

    if not isinstance(adapter, TravelBookingProviderAdapter):
        raise TravelBookingAdapterAdmissionError(
            "Travel booking adapter does not implement the required structural protocol."
        )
    _require_exact_async_signature(
        adapter.create_booking,
        label="Travel booking adapter create_booking",
        required=("preview", "traveler_data", "idempotency_key"),
    )
    _require_exact_async_signature(
        adapter.lookup_booking,
        label="Travel booking adapter lookup_booking",
        required=(),
        optional_none=("idempotency_key", "provider_booking_id"),
    )

    expected_metadata = {
        "provider_name": proposal["provider"],
        "adapter_revision": proposal["adapter_revision"],
        "booking_origin": proposal["booking_origin"],
        "travel_kind": proposal["travel_kind"],
        "action_kind": ACTION_KIND,
        "contract_version": CONTRACT_VERSION,
        "traveler_data_boundary_sha256": proposal["traveler_data_boundary_sha256"],
        "supports_idempotency": True,
        "supports_lookup_by_idempotency_key": True,
        "supports_lookup_by_provider_booking_id": True,
        "supports_provider_hosted_collection": True,
        "payment_mode": "provider_hosted_user_present",
        "receives_payment_instrument": False,
        "receives_document_images": False,
        "retains_traveler_data_in_logs": False,
    }
    for field, expected in expected_metadata.items():
        actual = getattr(adapter, field, None)
        if field == "booking_origin":
            actual = _clean_https_origin(actual, "adapter booking_origin")
        if actual != expected:
            raise TravelBookingAdapterAdmissionError(
                f"Travel booking adapter {field} does not match TX-20."
            )

    expected_sets = {
        "credential_scopes": set(proposal["credential_scopes"]),
        "required_traveler_fields": set(
            proposal["traveler_data_boundary"]["required_fields"]
        ),
        "shuddho_transmitted_fields": set(
            proposal["traveler_data_boundary"]["shuddho_transmitted_fields"]
        ),
        "provider_hosted_fields": set(
            proposal["traveler_data_boundary"]["provider_hosted_fields"]
        ),
    }
    for field, expected in expected_sets.items():
        actual = getattr(adapter, field, None)
        if not isinstance(actual, frozenset) or set(actual) != expected:
            raise TravelBookingAdapterAdmissionError(
                f"Travel booking adapter {field} does not exactly match TX-20."
            )

    admission = {
        "schema_version": 1,
        "status": "admitted_for_provider_implementation_tests",
        "provider": proposal["provider"],
        "operation": proposal["operation"],
        "adapter_revision": proposal["adapter_revision"],
        "booking_origin": proposal["booking_origin"],
        "travel_kind": proposal["travel_kind"],
        "qualification_sha256": proposal["qualification_sha256"],
        "registration_proposal_sha256": proposal[
            "registration_proposal_sha256"
        ],
        "action_contract": proposal["action_contract"],
        "credential_scopes": list(proposal["credential_scopes"]),
        "traveler_data_boundary": proposal["traveler_data_boundary"],
        "traveler_data_boundary_sha256": proposal[
            "traveler_data_boundary_sha256"
        ],
        "idempotency": proposal["idempotency"],
        "reconciliation": proposal["reconciliation"],
        "receipt": proposal["receipt"],
        "privacy": proposal["privacy"],
        "payment_boundary": proposal["payment_boundary"],
        "provider_called": False,
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    admission["adapter_admission_sha256"] = canonical_sha256(admission)
    return admission
