from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
)
from services.coworker.hosted_transaction_handoff import (
    HostedTransactionHandoffError,
    build_hosted_transaction_handoff,
    validate_hosted_transaction_completion,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def shopping_preview(now: datetime, *, expires_in_minutes: int = 10) -> dict:
    return {
        "schema_version": 1,
        "kind": "shopping_checkout_create",
        "checkout_binding_id": str(uuid4()),
        "transaction_id": str(uuid4()),
        "verification_id": str(uuid4()),
        "transaction_revision": 1,
        "terms_revision": 1,
        "terms_sha256": "1" * 64,
        "cart_sha256": "2" * 64,
        "verification_snapshot_sha256": "3" * 64,
        "provider": "merchantx",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 12500,
        "checkout_binding_scope_sha256": "4" * 64,
        "expires_at": (now + timedelta(minutes=expires_in_minutes)).isoformat(),
        "execution_authority": "not_registered",
        "payment_authority": "not_authorized",
        "identity_authority": "not_bound",
    }


def travel_preview(now: datetime, *, expires_in_minutes: int = 10) -> dict:
    return {
        "schema_version": 1,
        "kind": "travel_booking_create",
        "booking_binding_id": str(uuid4()),
        "transaction_id": str(uuid4()),
        "verification_id": str(uuid4()),
        "transaction_revision": 1,
        "terms_revision": 1,
        "terms_sha256": "5" * 64,
        "quote_sha256": "6" * 64,
        "verification_snapshot_sha256": "7" * 64,
        "travel_kind": "flight",
        "provider": "travelco",
        "provider_quote_id": "quote-123",
        "currency": "USD",
        "total_minor": 25000,
        "booking_binding_scope_sha256": "8" * 64,
        "prepared_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=expires_in_minutes)).isoformat(),
        "execution_authority": "not_registered",
        "identity_authority": "not_bound",
        "payment_authority": "not_authorized",
    }


def test_tx27_builds_non_final_shopping_handoff():
    now = utcnow()
    preview = shopping_preview(now)

    result = build_hosted_transaction_handoff(
        preview,
        handoff_id="checkout-session-123",
        handoff_url="https://checkout.example.test/session/123?token=opaque",
        reviewed_handoff_origin="https://checkout.example.test",
        now=now,
    )

    assert result["status"] == "awaiting_user_completion"
    assert result["action_kind"] == "shopping_checkout_create"
    assert result["provider"] == "merchantx"
    assert result["requires_user_present"] is True
    assert result["final_receipt_required"] is True
    assert result["payment_instrument_to_shuddho"] is False
    assert result["registration_authority"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["handoff_sha256"]) == 64


def test_tx27_builds_non_final_travel_handoff():
    now = utcnow()
    result = build_hosted_transaction_handoff(
        travel_preview(now),
        handoff_id="booking-session-123",
        handoff_url="https://booking.example.test/continue/123",
        reviewed_handoff_origin="https://booking.example.test",
        now=now,
    )

    assert result["status"] == "awaiting_user_completion"
    assert result["action_kind"] == "travel_booking_create"
    assert result["provider"] == "travelco"


def test_tx27_rejects_handoff_origin_drift():
    now = utcnow()
    with pytest.raises(HostedTransactionHandoffError):
        build_hosted_transaction_handoff(
            shopping_preview(now),
            handoff_id="checkout-session-123",
            handoff_url="https://evil.example/session/123",
            reviewed_handoff_origin="https://checkout.example.test",
            now=now,
        )


def test_tx27_rejects_handoff_url_credentials_and_fragment():
    now = utcnow()
    with pytest.raises(HostedTransactionHandoffError):
        build_hosted_transaction_handoff(
            shopping_preview(now),
            handoff_id="checkout-session-123",
            handoff_url="https://user:pass@checkout.example.test/session#secret",
            reviewed_handoff_origin="https://checkout.example.test",
            now=now,
        )


def test_tx27_rejects_expired_preview_before_handoff():
    now = utcnow()
    with pytest.raises(HostedTransactionHandoffError):
        build_hosted_transaction_handoff(
            shopping_preview(now, expires_in_minutes=-1),
            handoff_id="checkout-session-123",
            handoff_url="https://checkout.example.test/session/123",
            reviewed_handoff_origin="https://checkout.example.test",
            now=now,
        )


def test_tx27_confirms_shopping_only_after_later_receipt():
    now = utcnow()
    preview = shopping_preview(now)
    handoff = build_hosted_transaction_handoff(
        preview,
        handoff_id="checkout-session-123",
        handoff_url="https://checkout.example.test/session/123",
        reviewed_handoff_origin="https://checkout.example.test",
        now=now,
    )
    receipt = {
        "provider": "merchantx",
        "provider_order_id": "order-456",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 12500,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=2)).isoformat(),
    }

    result = validate_hosted_transaction_completion(
        handoff,
        preview,
        receipt,
        now=now + timedelta(minutes=3),
    )

    assert result["status"] == "confirmed"
    assert result["user_present_handoff_completed"] is True
    assert result["handoff_sha256"] == handoff["handoff_sha256"]
    assert result["payment_authority"] is False
    assert len(result["completion_sha256"]) == 64


def test_tx27_confirms_travel_only_after_later_receipt():
    now = utcnow()
    preview = travel_preview(now)
    handoff = build_hosted_transaction_handoff(
        preview,
        handoff_id="booking-session-123",
        handoff_url="https://booking.example.test/continue/123",
        reviewed_handoff_origin="https://booking.example.test",
        now=now,
    )
    receipt = {
        "provider": "travelco",
        "provider_booking_id": "booking-456",
        "provider_quote_id": "quote-123",
        "travel_kind": "flight",
        "currency": "USD",
        "total_minor": 25000,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=2)).isoformat(),
    }

    result = validate_hosted_transaction_completion(
        handoff,
        preview,
        receipt,
        now=now + timedelta(minutes=3),
    )

    assert result["status"] == "confirmed"
    assert result["action_kind"] == "travel_booking_create"


def test_tx27_rejects_confirmation_after_approval_expiry():
    now = utcnow()
    preview = shopping_preview(now, expires_in_minutes=2)
    handoff = build_hosted_transaction_handoff(
        preview,
        handoff_id="checkout-session-123",
        handoff_url="https://checkout.example.test/session/123",
        reviewed_handoff_origin="https://checkout.example.test",
        now=now,
    )
    receipt = {
        "provider": "merchantx",
        "provider_order_id": "order-456",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 12500,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=3)).isoformat(),
    }

    with pytest.raises(HostedTransactionHandoffError):
        validate_hosted_transaction_completion(
            handoff,
            preview,
            receipt,
            now=now + timedelta(minutes=4),
        )


def test_tx27_rejects_tampered_handoff_digest():
    now = utcnow()
    preview = shopping_preview(now)
    handoff = build_hosted_transaction_handoff(
        preview,
        handoff_id="checkout-session-123",
        handoff_url="https://checkout.example.test/session/123",
        reviewed_handoff_origin="https://checkout.example.test",
        now=now,
    )
    tampered = deepcopy(handoff)
    tampered["total_minor"] += 1

    receipt = {
        "provider": "merchantx",
        "provider_order_id": "order-456",
        "merchant_cart_id": "cart-123",
        "currency": "USD",
        "total_minor": 12500,
        "status": "confirmed",
        "confirmed_at": (now + timedelta(minutes=1)).isoformat(),
    }
    with pytest.raises(HostedTransactionHandoffError):
        validate_hosted_transaction_completion(
            tampered,
            preview,
            receipt,
            now=now + timedelta(minutes=2),
        )


def test_tx27_does_not_register_transaction_actions():
    for kind in ("shopping_checkout_create", "travel_booking_create"):
        with pytest.raises(Exception):
            action_spec(kind)
    assert all(
        "shopping_checkout_create" not in operation
        and "travel_booking_create" not in operation
        for operation in registered_transaction_operations()
    )
