from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.travel_booking_provider_qualification import (
    canonical_sha256 as tx19_sha256,
    validate_travel_booking_provider_qualification,
)
from scripts.travel_booking_registration_proposal import (
    TravelBookingRegistrationProposalError,
    compile_travel_registration_proposal,
)
from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
)


REVISION = "a" * 40
PROBE_SHA = "b" * 64


def utcnow():
    return datetime.now(timezone.utc)


def tx19_source():
    now = utcnow()
    traveler_boundary = {
        "required_fields": ["legal_name", "date_of_birth", "email"],
        "shuddho_transmitted_fields": ["legal_name", "email"],
        "provider_hosted_fields": ["date_of_birth"],
        "document_images_to_shuddho": False,
        "payment_instrument_to_shuddho": False,
        "optional_fields_default_off": True,
    }
    normalized_boundary = {
        **traveler_boundary,
        "required_fields": sorted(traveler_boundary["required_fields"]),
        "shuddho_transmitted_fields": sorted(
            traveler_boundary["shuddho_transmitted_fields"]
        ),
        "provider_hosted_fields": sorted(
            traveler_boundary["provider_hosted_fields"]
        ),
    }
    return {
        "schema_version": 1,
        "provider": "travelco",
        "adapter_revision": REVISION,
        "booking_origin": "https://booking.travelco.example",
        "supported_travel_kinds": ["flight"],
        "credential_boundary": {
            "storage": "credential_broker",
            "server_side_only": True,
            "least_privilege": True,
            "scopes": ["booking.create", "booking.read"],
            "raw_payment_credentials": False,
        },
        "traveler_data_boundary": traveler_boundary,
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
            "verified_at": (now - timedelta(minutes=5)).isoformat(),
            "source_revision": REVISION,
            "booking_origin": "https://booking.travelco.example",
            "travel_kind": "flight",
            "traveler_data_boundary_sha256": tx19_sha256(normalized_boundary),
            "traveler_minimization_passed": True,
            "idempotency_passed": True,
            "reconciliation_passed": True,
            "receipt_match_passed": True,
            "privacy_passed": True,
            "payment_boundary_passed": True,
            "evidence_sha256": PROBE_SHA,
        },
    }


def qualification():
    return validate_travel_booking_provider_qualification(
        tx19_source(),
        now=utcnow(),
    )


def review(q=None, **changes):
    q = q or qualification()
    value = {
        "schema_version": 1,
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "booking_origin": q["booking_origin"],
        "travel_kind": q["supported_travel_kinds"][0],
        "traveler_data_boundary_sha256": q["live_probe"][
            "traveler_data_boundary_sha256"
        ],
        "qualification_sha256": q["qualification_sha256"],
        "action_contract_version": 1,
        "change_reference": "TX20-reviewed-change",
        "reviewed_at": utcnow().isoformat(),
        "reviewer_reference": "security-reviewer",
    }
    value.update(changes)
    return value


def test_tx20_compiles_exact_inert_registration_proposal():
    q = qualification()
    now = utcnow()
    result = compile_travel_registration_proposal(
        q,
        review(q, reviewed_at=now.isoformat()),
        now=now,
    )

    assert result["status"] == "eligible_for_provider_implementation_review"
    assert result["provider"] == "travelco"
    assert result["operation"] == "travelco:travel_booking_create"
    assert result["travel_kind"] == "flight"
    assert result["qualification_sha256"] == q["qualification_sha256"]
    assert result["traveler_data_boundary_sha256"] == q["live_probe"][
        "traveler_data_boundary_sha256"
    ]
    assert result["action_contract"] == {
        "kind": "travel_booking_create",
        "version": 1,
        "source": "TX-18",
    }
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["registration_proposal_sha256"]) == 64

    with pytest.raises(Exception):
        action_spec("travel_booking_create")
    assert all(
        "travel_booking_create" not in item
        for item in registered_transaction_operations()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other"),
        ("operation", "travelco:other"),
        ("adapter_revision", "c" * 40),
        ("booking_origin", "https://other.example"),
        ("travel_kind", "lodging"),
        ("traveler_data_boundary_sha256", "d" * 64),
        ("qualification_sha256", "e" * 64),
    ],
)
def test_tx20_rejects_registration_review_drift(field, value):
    q = qualification()
    item = review(q)
    item[field] = value
    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(q, item, now=utcnow())


def test_tx20_rejects_tampered_tx19_qualification_even_with_original_hash():
    q = qualification()
    tampered = deepcopy(q)
    tampered["traveler_data_boundary"]["shuddho_transmitted_fields"].append("phone")
    with pytest.raises(TravelBookingRegistrationProposalError) as error:
        compile_travel_registration_proposal(
            tampered,
            review(q),
            now=utcnow(),
        )
    assert "digest" in str(error.value).lower() or "traveler" in str(error.value).lower()


def test_tx20_rejects_tx19_evidence_claiming_runtime_authority():
    q = qualification()
    q["identity_authority"] = True
    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(
            q,
            review(qualification()),
            now=utcnow(),
        )


def test_tx20_rejects_wrong_contract_version():
    q = qualification()
    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(
            q,
            review(q, action_contract_version=2),
            now=utcnow(),
        )


def test_tx20_rejects_stale_or_future_registration_review():
    q = qualification()
    now = utcnow()

    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(
            q,
            review(q, reviewed_at=(now - timedelta(days=8)).isoformat()),
            now=now,
        )

    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(
            q,
            review(q, reviewed_at=(now + timedelta(minutes=5)).isoformat()),
            now=now,
        )


def test_tx20_rejects_stale_tx19_qualification():
    source = tx19_source()
    now = utcnow()
    source["live_probe"]["verified_at"] = (
        now - timedelta(hours=25)
    ).isoformat()

    with pytest.raises(Exception):
        validate_travel_booking_provider_qualification(source, now=now)


def test_tx20_rejects_traveler_boundary_changed_after_probe():
    q = qualification()
    tampered = deepcopy(q)
    tampered["traveler_data_boundary"]["provider_hosted_fields"].append("phone")
    tampered["traveler_data_boundary"]["required_fields"].append("phone")

    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(
            tampered,
            review(q),
            now=utcnow(),
        )


def test_tx20_rejects_unexpected_review_schema():
    q = qualification()
    item = review(q)
    item["unexpected"] = True
    with pytest.raises(TravelBookingRegistrationProposalError):
        compile_travel_registration_proposal(q, item, now=utcnow())
