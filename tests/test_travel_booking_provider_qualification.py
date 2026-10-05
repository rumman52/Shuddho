from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.travel_booking_provider_qualification import (
    TravelBookingQualificationError,
    validate_travel_booking_provider_qualification,
)
from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
)


REVISION = "a" * 40
EVIDENCE_SHA = "b" * 64


def utcnow():
    return datetime.now(timezone.utc)


def evidence():
    now = utcnow()
    return {
        "schema_version": 1,
        "provider": "travelco",
        "adapter_revision": REVISION,
        "booking_origin": "https://booking.travelco.example",
        "supported_travel_kinds": ["flight", "lodging"],
        "credential_boundary": {
            "storage": "credential_broker",
            "server_side_only": True,
            "least_privilege": True,
            "scopes": ["booking.create", "booking.read"],
            "raw_payment_credentials": False,
        },
        "traveler_data_boundary": {
            "required_fields": ["legal_name", "date_of_birth", "email"],
            "shuddho_transmitted_fields": ["legal_name", "email"],
            "provider_hosted_fields": ["date_of_birth"],
            "document_images_to_shuddho": False,
            "payment_instrument_to_shuddho": False,
            "optional_fields_default_off": True,
        },
        "idempotency": {
            "supported": True,
            "key_scope": "booking_binding",
            "duplicate_result": "same_booking_or_lookup",
        },
        "reconciliation": {
            "supported": True,
            "lookup_keys": ["idempotency_key", "provider_booking_id"],
            "outcome_unknown_policy": "lookup_before_retry",
            "blind_retry": False,
        },
        "receipt": {
            "readback_supported": True,
            "exact_fields": [
                "provider_booking_id",
                "provider_quote_id",
                "travel_kind",
                "currency",
                "total_minor",
                "status",
                "confirmed_at",
            ],
            "confirmed_status": "confirmed",
        },
        "privacy": {
            "sends_only_required_fields": True,
            "secrets_in_logs": False,
            "retains_traveler_data_in_logs": False,
            "provider_hosted_collection_supported": True,
        },
        "payment_boundary": {
            "mode": "provider_hosted_user_present",
            "shuddho_charges": False,
            "stores_payment_instrument": False,
            "requires_user_present": True,
        },
        "live_probe": {
            "status": "passed",
            "environment": "staging",
            "verified_at": (now - timedelta(minutes=10)).isoformat(),
            "source_revision": REVISION,
            "booking_origin": "https://booking.travelco.example",
            "traveler_minimization_passed": True,
            "idempotency_passed": True,
            "reconciliation_passed": True,
            "receipt_match_passed": True,
            "privacy_passed": True,
            "payment_boundary_passed": True,
            "evidence_sha256": EVIDENCE_SHA,
        },
    }


def test_tx19_accepts_exact_provider_qualification_but_grants_no_authority():
    now = utcnow()
    result = validate_travel_booking_provider_qualification(
        evidence(),
        now=now,
    )

    assert result["provider"] == "travelco"
    assert result["operation"] == "travelco:travel_booking_create"
    assert result["contract_version"] == 1
    assert result["supported_travel_kinds"] == ["flight", "lodging"]
    assert result["traveler_data_boundary"]["required_fields"] == [
        "date_of_birth",
        "email",
        "legal_name",
    ]
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["qualification_sha256"]) == 64

    with pytest.raises(Exception):
        action_spec("travel_booking_create")
    assert all(
        "travel_booking_create" not in operation
        for operation in registered_transaction_operations()
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("credential_boundary", "raw_payment_credentials", True),
        ("credential_boundary", "server_side_only", False),
        ("traveler_data_boundary", "document_images_to_shuddho", True),
        ("traveler_data_boundary", "payment_instrument_to_shuddho", True),
        ("traveler_data_boundary", "optional_fields_default_off", False),
        ("idempotency", "supported", False),
        ("reconciliation", "blind_retry", True),
        ("receipt", "readback_supported", False),
        ("privacy", "sends_only_required_fields", False),
        ("privacy", "secrets_in_logs", True),
        ("privacy", "retains_traveler_data_in_logs", True),
        ("payment_boundary", "shuddho_charges", True),
        ("payment_boundary", "stores_payment_instrument", True),
        ("payment_boundary", "requires_user_present", False),
        ("live_probe", "traveler_minimization_passed", False),
        ("live_probe", "receipt_match_passed", False),
    ],
)
def test_tx19_fails_closed_on_unsafe_provider_evidence(section, field, value):
    item = evidence()
    item[section][field] = value
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(
            item,
            now=utcnow(),
        )


def test_tx19_rejects_unknown_or_unpartitioned_traveler_fields():
    item = evidence()
    item["traveler_data_boundary"]["required_fields"].append("favorite_color")
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())

    item = evidence()
    item["traveler_data_boundary"]["provider_hosted_fields"] = []
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())

    item = evidence()
    item["traveler_data_boundary"]["shuddho_transmitted_fields"].append("date_of_birth")
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())


def test_tx19_rejects_nonproduction_provider_and_bad_kind():
    item = evidence()
    item["provider"] = "simulated"
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())

    item = evidence()
    item["supported_travel_kinds"] = ["cruise"]
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())


def test_tx19_rejects_revision_or_origin_mismatch():
    item = evidence()
    item["live_probe"]["source_revision"] = "c" * 40
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())

    item = evidence()
    item["live_probe"]["booking_origin"] = "https://other.example"
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())


def test_tx19_rejects_stale_or_future_probe():
    item = evidence()
    item["live_probe"]["verified_at"] = (
        utcnow() - timedelta(hours=25)
    ).isoformat()
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())

    item = evidence()
    item["live_probe"]["verified_at"] = (
        utcnow() + timedelta(minutes=5)
    ).isoformat()
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())


def test_tx19_qualification_hash_is_canonical_for_ordering():
    first = evidence()
    second = deepcopy(first)
    second["supported_travel_kinds"] = list(
        reversed(second["supported_travel_kinds"])
    )
    second["credential_boundary"]["scopes"] = list(
        reversed(second["credential_boundary"]["scopes"])
    )
    second["traveler_data_boundary"]["required_fields"] = list(
        reversed(second["traveler_data_boundary"]["required_fields"])
    )
    second["traveler_data_boundary"]["shuddho_transmitted_fields"] = list(
        reversed(second["traveler_data_boundary"]["shuddho_transmitted_fields"])
    )
    second["reconciliation"]["lookup_keys"] = list(
        reversed(second["reconciliation"]["lookup_keys"])
    )
    second["receipt"]["exact_fields"] = list(
        reversed(second["receipt"]["exact_fields"])
    )

    now = utcnow()
    a = validate_travel_booking_provider_qualification(first, now=now)
    b = validate_travel_booking_provider_qualification(second, now=now)
    assert a["qualification_sha256"] == b["qualification_sha256"]


def test_tx19_rejects_dirty_origin_and_unexpected_schema():
    item = evidence()
    item["booking_origin"] = "https://user:pass@booking.travelco.example"
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())

    item = evidence()
    item["unexpected"] = True
    with pytest.raises(TravelBookingQualificationError):
        validate_travel_booking_provider_qualification(item, now=utcnow())
