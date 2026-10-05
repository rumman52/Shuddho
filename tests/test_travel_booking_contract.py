"""TX-18 provider-neutral travel booking contract foundation."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
    stable_digest,
)
from services.coworker.errors import CoworkerError
from services.coworker.models import utcnow
from services.coworker.travel_booking_contract import (
    build_travel_booking_preview,
    validate_travel_booking_receipt,
)


def binding_payload(**changes):
    now = utcnow()
    transaction_id = str(uuid4())
    verification_id = str(uuid4())
    expires_at = now + timedelta(minutes=4)
    value = {
        "id": str(uuid4()),
        "transaction_id": transaction_id,
        "verification_id": verification_id,
        "transaction_revision": 4,
        "terms_revision": 2,
        "terms_sha256": "1" * 64,
        "quote_sha256": "2" * 64,
        "verification_snapshot_sha256": "3" * 64,
        "travel_kind": "flight",
        "provider": "example_travel",
        "provider_quote_id": "quote-123",
        "currency": "USD",
        "total_minor": 50000,
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
        "execution_available": False,
    }
    scope = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "transaction_revision": 4,
        "terms_revision": 2,
        "terms_sha256": "1" * 64,
        "quote_sha256": "2" * 64,
        "verification_id": verification_id,
        "verification_snapshot_sha256": "3" * 64,
        "travel_kind": "flight",
        "provider": "example_travel",
        "provider_quote_id": "quote-123",
        "currency": "USD",
        "total_minor": 50000,
        "expires_at": expires_at.isoformat(),
        "authority": "binding_only_no_execution",
    }
    value["approval_scope_sha256"] = stable_digest(scope)
    value.update(changes)
    return value


def test_tx18_builds_exact_non_executable_travel_booking_preview():
    binding = binding_payload()
    value = build_travel_booking_preview(binding)
    preview = value["preview"]

    assert value["execution_available"] is False
    assert preview["kind"] == "travel_booking_create"
    assert preview["booking_binding_id"] == binding["id"]
    assert preview["terms_sha256"] == binding["terms_sha256"]
    assert preview["quote_sha256"] == binding["quote_sha256"]
    assert preview["verification_snapshot_sha256"] == binding["verification_snapshot_sha256"]
    assert preview["travel_kind"] == "flight"
    assert preview["provider"] == "example_travel"
    assert preview["provider_quote_id"] == "quote-123"
    assert preview["currency"] == "USD"
    assert preview["total_minor"] == 50000
    assert preview["execution_authority"] == "not_registered"
    assert preview["identity_authority"] == "not_bound"
    assert preview["payment_authority"] == "not_authorized"
    assert "prepared_at" in preview
    assert value["preview_hash"] == stable_digest(preview)

    forbidden = {
        "traveler_legal_name",
        "passport",
        "passport_number",
        "date_of_birth",
        "email",
        "phone",
        "loyalty_number",
        "payment_method",
        "card",
        "bank_account",
    }
    assert forbidden.isdisjoint(preview)


def test_tx18_rejects_tampered_binding_scope():
    binding = binding_payload(total_minor=50001)
    with pytest.raises(CoworkerError) as error:
        build_travel_booking_preview(binding)
    assert error.value.code == "travel_booking_binding_integrity"


def test_tx18_rejects_expired_binding():
    now = utcnow()
    binding = binding_payload(
        expires_at=(now - timedelta(seconds=1)).isoformat(),
    )
    scope = {
        "schema_version": 1,
        "transaction_id": binding["transaction_id"],
        "transaction_revision": binding["transaction_revision"],
        "terms_revision": binding["terms_revision"],
        "terms_sha256": binding["terms_sha256"],
        "quote_sha256": binding["quote_sha256"],
        "verification_id": binding["verification_id"],
        "verification_snapshot_sha256": binding["verification_snapshot_sha256"],
        "travel_kind": binding["travel_kind"],
        "provider": binding["provider"],
        "provider_quote_id": binding["provider_quote_id"],
        "currency": binding["currency"],
        "total_minor": binding["total_minor"],
        "expires_at": binding["expires_at"],
        "authority": "binding_only_no_execution",
    }
    binding["approval_scope_sha256"] = stable_digest(scope)

    with pytest.raises(CoworkerError) as error:
        build_travel_booking_preview(binding, now=now)
    assert error.value.code == "travel_booking_binding_expired"


def test_tx18_validates_exact_future_provider_receipt():
    built = build_travel_booking_preview(binding_payload())
    now = utcnow()
    receipt = {
        "provider": "example_travel",
        "provider_booking_id": "booking-456",
        "provider_quote_id": "quote-123",
        "travel_kind": "flight",
        "currency": "USD",
        "total_minor": 50000,
        "status": "confirmed",
        "confirmed_at": now.isoformat(),
    }
    result = validate_travel_booking_receipt(
        built["preview"],
        receipt,
        now=now,
    )
    assert result["matched"] is True
    assert result["receipt"]["provider_booking_id"] == "booking-456"
    assert result["receipt_sha256"] == stable_digest(result["receipt"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other_travel"),
        ("provider_quote_id", "other-quote"),
        ("travel_kind", "lodging"),
        ("currency", "EUR"),
        ("total_minor", 50001),
    ],
)
def test_tx18_rejects_receipt_drift(field, value):
    built = build_travel_booking_preview(binding_payload())
    now = utcnow()
    receipt = {
        "provider": "example_travel",
        "provider_booking_id": "booking-456",
        "provider_quote_id": "quote-123",
        "travel_kind": "flight",
        "currency": "USD",
        "total_minor": 50000,
        "status": "confirmed",
        "confirmed_at": now.isoformat(),
    }
    receipt[field] = value

    with pytest.raises(CoworkerError) as error:
        validate_travel_booking_receipt(built["preview"], receipt, now=now)
    assert error.value.code == "travel_booking_receipt_mismatch"


def test_tx18_rejects_future_receipt_timestamp():
    built = build_travel_booking_preview(binding_payload())
    now = utcnow()
    receipt = {
        "provider": "example_travel",
        "provider_booking_id": "booking-456",
        "provider_quote_id": "quote-123",
        "travel_kind": "flight",
        "currency": "USD",
        "total_minor": 50000,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=6)).isoformat(),
    }
    with pytest.raises(CoworkerError) as error:
        validate_travel_booking_receipt(built["preview"], receipt, now=now)
    assert error.value.code == "travel_booking_receipt_invalid"




def test_tx18_rejects_receipt_that_predates_preview():
    now = utcnow()
    built = build_travel_booking_preview(binding_payload(), now=now)
    receipt = {
        "provider": "example_travel",
        "provider_booking_id": "booking-456",
        "provider_quote_id": "quote-123",
        "travel_kind": "flight",
        "currency": "USD",
        "total_minor": 50000,
        "status": "confirmed",
        "confirmed_at": (now - timedelta(minutes=6)).isoformat(),
    }
    with pytest.raises(CoworkerError) as error:
        validate_travel_booking_receipt(built["preview"], receipt, now=now)
    assert error.value.code == "travel_booking_receipt_invalid"


def test_tx18_rejects_receipt_after_binding_expiry():
    now = utcnow()
    binding = binding_payload(
        expires_at=(now + timedelta(minutes=1)).isoformat(),
    )
    scope = {
        "schema_version": 1,
        "transaction_id": binding["transaction_id"],
        "transaction_revision": binding["transaction_revision"],
        "terms_revision": binding["terms_revision"],
        "terms_sha256": binding["terms_sha256"],
        "quote_sha256": binding["quote_sha256"],
        "verification_id": binding["verification_id"],
        "verification_snapshot_sha256": binding["verification_snapshot_sha256"],
        "travel_kind": binding["travel_kind"],
        "provider": binding["provider"],
        "provider_quote_id": binding["provider_quote_id"],
        "currency": binding["currency"],
        "total_minor": binding["total_minor"],
        "expires_at": binding["expires_at"],
        "authority": "binding_only_no_execution",
    }
    binding["approval_scope_sha256"] = stable_digest(scope)
    built = build_travel_booking_preview(binding, now=now)
    receipt = {
        "provider": "example_travel",
        "provider_booking_id": "booking-456",
        "provider_quote_id": "quote-123",
        "travel_kind": "flight",
        "currency": "USD",
        "total_minor": 50000,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=2)).isoformat(),
    }
    with pytest.raises(CoworkerError) as error:
        validate_travel_booking_receipt(
            built["preview"],
            receipt,
            now=now + timedelta(minutes=2),
        )
    assert error.value.code == "travel_booking_receipt_invalid"


def test_tx18_travel_booking_action_remains_unregistered_and_unallowlisted():
    with pytest.raises(CoworkerError) as error:
        action_spec("travel_booking_create")
    assert error.value.code == "action_not_registered"
    assert all(
        "travel_booking" not in operation
        for operation in registered_transaction_operations()
    )
