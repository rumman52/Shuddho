"""TX-13 provider-neutral shopping checkout contract foundation."""
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
from services.coworker.shopping_checkout_contract import (
    build_checkout_preview,
    validate_checkout_receipt,
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
        "cart_sha256": "2" * 64,
        "verification_snapshot_sha256": "3" * 64,
        "provider": "example_merchant",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 7000,
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
        "cart_sha256": "2" * 64,
        "verification_id": verification_id,
        "verification_snapshot_sha256": "3" * 64,
        "provider": "example_merchant",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 7000,
        "expires_at": expires_at.isoformat(),
        "authority": "binding_only_no_execution",
    }
    value["approval_scope_sha256"] = stable_digest(scope)
    value.update(changes)
    return value


def test_tx13_builds_exact_non_executable_preview():
    binding = binding_payload()
    value = build_checkout_preview(binding)
    preview = value["preview"]

    assert value["execution_available"] is False
    assert preview["kind"] == "shopping_checkout_create"
    assert preview["checkout_binding_id"] == binding["id"]
    assert preview["terms_sha256"] == binding["terms_sha256"]
    assert preview["verification_snapshot_sha256"] == binding["verification_snapshot_sha256"]
    assert preview["currency"] == "USD"
    assert preview["total_minor"] == 7000
    assert preview["execution_authority"] == "not_registered"
    assert preview["payment_authority"] == "not_authorized"
    assert preview["identity_authority"] == "not_bound"
    assert value["preview_hash"] == stable_digest(preview)

    forbidden = {
        "shipping_address",
        "billing_address",
        "email",
        "phone",
        "payment_method",
        "card",
        "bank_account",
    }
    assert forbidden.isdisjoint(preview)


def test_tx13_rejects_tampered_binding_scope():
    binding = binding_payload(total_minor=7100)
    with pytest.raises(CoworkerError) as error:
        build_checkout_preview(binding)
    assert error.value.code == "shopping_checkout_binding_integrity"


def test_tx13_rejects_expired_binding():
    now = utcnow()
    binding = binding_payload(
        expires_at=(now - timedelta(seconds=1)).isoformat(),
    )
    # Recompute the scope so this test reaches expiry rather than integrity rejection.
    scope = {
        "schema_version": 1,
        "transaction_id": binding["transaction_id"],
        "transaction_revision": binding["transaction_revision"],
        "terms_revision": binding["terms_revision"],
        "terms_sha256": binding["terms_sha256"],
        "cart_sha256": binding["cart_sha256"],
        "verification_id": binding["verification_id"],
        "verification_snapshot_sha256": binding["verification_snapshot_sha256"],
        "provider": binding["provider"],
        "merchant_cart_id": binding["merchant_cart_id"],
        "currency": binding["currency"],
        "total_minor": binding["total_minor"],
        "expires_at": binding["expires_at"],
        "authority": "binding_only_no_execution",
    }
    binding["approval_scope_sha256"] = stable_digest(scope)

    with pytest.raises(CoworkerError) as error:
        build_checkout_preview(binding, now=now)
    assert error.value.code == "shopping_checkout_binding_expired"


def test_tx13_validates_exact_future_provider_receipt():
    built = build_checkout_preview(binding_payload())
    now = utcnow()
    receipt = {
        "provider": "example_merchant",
        "provider_order_id": "order-456",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 7000,
        "status": "confirmed",
        "confirmed_at": now.isoformat(),
    }
    result = validate_checkout_receipt(
        built["preview"],
        receipt,
        now=now,
    )
    assert result["matched"] is True
    assert result["receipt"]["provider_order_id"] == "order-456"
    assert result["receipt_sha256"] == stable_digest(result["receipt"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other_merchant"),
        ("merchant_cart_id", "other-cart"),
        ("currency", "EUR"),
        ("total_minor", 7001),
    ],
)
def test_tx13_rejects_receipt_drift(field, value):
    built = build_checkout_preview(binding_payload())
    now = utcnow()
    receipt = {
        "provider": "example_merchant",
        "provider_order_id": "order-456",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 7000,
        "status": "confirmed",
        "confirmed_at": now.isoformat(),
    }
    receipt[field] = value

    with pytest.raises(CoworkerError) as error:
        validate_checkout_receipt(built["preview"], receipt, now=now)
    assert error.value.code == "shopping_checkout_receipt_mismatch"


def test_tx13_rejects_receipt_confirmed_after_checkout_expiry():
    now = utcnow()
    binding = binding_payload()
    binding["expires_at"] = (now + timedelta(minutes=2)).isoformat()
    scope = {
        "schema_version": 1,
        "transaction_id": binding["transaction_id"],
        "transaction_revision": binding["transaction_revision"],
        "terms_revision": binding["terms_revision"],
        "terms_sha256": binding["terms_sha256"],
        "cart_sha256": binding["cart_sha256"],
        "verification_id": binding["verification_id"],
        "verification_snapshot_sha256": binding["verification_snapshot_sha256"],
        "provider": binding["provider"],
        "merchant_cart_id": binding["merchant_cart_id"],
        "currency": binding["currency"],
        "total_minor": binding["total_minor"],
        "expires_at": binding["expires_at"],
        "authority": "binding_only_no_execution",
    }
    binding["approval_scope_sha256"] = stable_digest(scope)
    built = build_checkout_preview(binding, now=now)
    receipt = {
        "provider": "example_merchant",
        "provider_order_id": "order-456",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 7000,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=3)).isoformat(),
    }

    with pytest.raises(CoworkerError) as error:
        validate_checkout_receipt(
            built["preview"],
            receipt,
            now=now + timedelta(minutes=4),
        )
    assert error.value.code == "shopping_checkout_receipt_invalid"


def test_tx13_checkout_action_remains_unregistered_and_unallowlisted():
    with pytest.raises(CoworkerError) as error:
        action_spec("shopping_checkout_create")
    assert error.value.code == "action_not_registered"
    assert all(
        "shopping_checkout" not in operation
        for operation in registered_transaction_operations()
    )
