from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts import staging_live_restaurant_reservations as live


def test_wrong_hash_changes_valid_digest():
    value = "a" * 64
    changed = live.wrong_hash(value)
    assert changed != value
    assert len(changed) == 64


def test_validate_authority_requires_exact_bounded_restaurant_scope():
    live.validate_authority({
        "schema_version": 2,
        "source_revision": "a" * 40,
        "personal_transactions_enabled": True,
        "restaurant_reservations_enabled": True,
        "shopping_checkout_enabled": False,
        "travel_booking_enabled": False,
        "operations": [live.OPERATION],
    })
    with pytest.raises(live.RestaurantReservationProbeError):
        live.validate_authority({
            "schema_version": 2,
            "source_revision": "a" * 40,
            "personal_transactions_enabled": True,
            "restaurant_reservations_enabled": True,
            "shopping_checkout_enabled": True,
            "travel_booking_enabled": False,
            "operations": [live.OPERATION],
        })


def test_validate_review_surface_enforces_zero_payment():
    value = {
        "transaction": {
            "transaction_kind": "restaurant_reservation",
            "provider": "opentable",
            "state": "terms_ready",
            "currency": "XXX",
        },
        "terms": {"currency": "XXX", "total_minor": 0},
        "reservation": {
            "availability_sha256": "b" * 64,
            "availability": {"payment_required": False},
        },
    }
    live.validate_review_surface(value)
    value["reservation"]["availability"]["payment_required"] = True
    with pytest.raises(live.RestaurantReservationProbeError):
        live.validate_review_surface(value)


def test_receipt_evidence_requires_provider_confirmation_and_no_payment():
    value = {
        "state": "succeeded",
        "receipt": {
            "provider": "opentable",
            "status": "reservation_confirmed",
            "payment_required": False,
            "confirmation_number": 12345,
        },
    }
    digest = live.receipt_evidence(value)
    assert len(digest) == 64

    value["receipt"]["payment_required"] = True
    with pytest.raises(live.RestaurantReservationProbeError):
        live.receipt_evidence(value)
