from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.travel_booking_runtime_registration_review import (
    TravelBookingRuntimeRegistrationReviewError,
    compile_runtime_registration_review,
)
from services.coworker.action_registry import stable_digest
from services.coworker.travel_booking_adapter import canonical_sha256


REVISION = "a" * 40
ORIGIN = "https://booking.travelco.example"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def proposal(now: datetime) -> dict:
    traveler = {
        "required_fields": ["date_of_birth", "email", "legal_name"],
        "shuddho_transmitted_fields": ["email", "legal_name"],
        "provider_hosted_fields": ["date_of_birth"],
        "document_images_to_shuddho": False,
        "payment_instrument_to_shuddho": False,
        "optional_fields_default_off": True,
    }
    value = {
        "schema_version": 1,
        "status": "eligible_for_provider_implementation_review",
        "provider": "travelco",
        "operation": "travelco:travel_booking_create",
        "adapter_revision": REVISION,
        "booking_origin": ORIGIN,
        "travel_kind": "flight",
        "qualification_sha256": "b" * 64,
        "action_contract": {
            "kind": "travel_booking_create",
            "version": 1,
            "source": "TX-18",
        },
        "credential_scopes": ["booking.create", "booking.read"],
        "traveler_data_boundary": traveler,
        "traveler_data_boundary_sha256": canonical_sha256(traveler),
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
                "confirmed_at",
                "currency",
                "provider_booking_id",
                "provider_quote_id",
                "status",
                "total_minor",
                "travel_kind",
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
        "change_reference": "TX25-proposal-review",
        "reviewed_at": now.isoformat(),
        "reviewer_reference": "security-reviewer",
        "registry_change_required": True,
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    value["registration_proposal_sha256"] = canonical_sha256(value)
    return value


def conformance(now: datetime, p: dict) -> dict:
    value = {
        "schema_version": 2,
        "status": "provider_handoff_conformance_passed",
        "provider": p["provider"],
        "operation": p["operation"],
        "adapter_revision": p["adapter_revision"],
        "travel_kind": p["travel_kind"],
        "qualification_sha256": p["qualification_sha256"],
        "registration_proposal_sha256": p["registration_proposal_sha256"],
        "adapter_admission_sha256": "c" * 64,
        "preview_sha256": "d" * 64,
        "handoff_sha256": "e" * 64,
        "idempotency_key_sha256": "f" * 64,
        "sandbox_provider_io": True,
        "provider_called": True,
        "handoff_attempts": 2,
        "receipt_lookup_attempts": 2,
        "completion_receipt_observed": False,
        "traveler_fields_sent": ["email", "legal_name"],
        "evaluated_at": now.isoformat(),
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    value["conformance_sha256"] = stable_digest(value)
    return value


def review(now: datetime, p: dict, c: dict, **changes) -> dict:
    value = {
        "schema_version": 1,
        "provider": p["provider"],
        "operation": p["operation"],
        "adapter_revision": p["adapter_revision"],
        "travel_kind": p["travel_kind"],
        "registration_proposal_sha256": p["registration_proposal_sha256"],
        "conformance_sha256": c["conformance_sha256"],
        "decision": "approved_for_runtime_registration_review",
        "change_reference": "TX25-reviewed-change",
        "reviewer_reference": "security-reviewer",
        "reviewed_at": (now + timedelta(seconds=1)).isoformat(),
    }
    value.update(changes)
    return value


def test_tx25_compiles_inert_runtime_registration_review():
    now = utcnow()
    p = proposal(now)
    c = conformance(now, p)
    result = compile_runtime_registration_review(
        p, c, review(now, p, c), now=now + timedelta(seconds=2)
    )
    assert result["status"] == "eligible_for_runtime_registration_review"
    assert result["travel_kind"] == "flight"
    assert result["traveler_fields_sent"] == ["email", "legal_name"]
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["runtime_registration_review_sha256"]) == 64


def test_tx25_rejects_tampered_conformance():
    now = utcnow()
    p = proposal(now)
    c = conformance(now, p)
    bad = deepcopy(c)
    bad["handoff_sha256"] = "0" * 64
    with pytest.raises(TravelBookingRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p, bad, review(now, p, c), now=now + timedelta(seconds=2)
        )


def test_tx25_rejects_proposal_hash_drift():
    now = utcnow()
    p = proposal(now)
    c = conformance(now, p)
    bad = deepcopy(c)
    bad["registration_proposal_sha256"] = "0" * 64
    unsigned = dict(bad)
    unsigned.pop("conformance_sha256")
    bad["conformance_sha256"] = stable_digest(unsigned)
    with pytest.raises(TravelBookingRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p, bad, review(now, p, c), now=now + timedelta(seconds=2)
        )


def test_tx25_rejects_unreviewed_traveler_field_drift():
    now = utcnow()
    p = proposal(now)
    c = conformance(now, p)
    bad = deepcopy(c)
    bad["traveler_fields_sent"] = ["email", "legal_name", "passport_number"]
    unsigned = dict(bad)
    unsigned.pop("conformance_sha256")
    bad["conformance_sha256"] = stable_digest(unsigned)
    with pytest.raises(TravelBookingRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p, bad, review(now, p, c), now=now + timedelta(seconds=2)
        )


def test_tx25_rejects_review_before_conformance():
    now = utcnow()
    p = proposal(now)
    c = conformance(now, p)
    with pytest.raises(TravelBookingRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p,
            c,
            review(
                now,
                p,
                c,
                reviewed_at=(now - timedelta(seconds=1)).isoformat(),
            ),
            now=now + timedelta(seconds=2),
        )


def test_tx25_rejects_runtime_authority_in_conformance():
    now = utcnow()
    p = proposal(now)
    c = conformance(now, p)
    bad = deepcopy(c)
    bad["runtime_enabled"] = True
    unsigned = dict(bad)
    unsigned.pop("conformance_sha256")
    bad["conformance_sha256"] = stable_digest(unsigned)
    with pytest.raises(TravelBookingRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p, bad, review(now, p, c), now=now + timedelta(seconds=2)
        )
