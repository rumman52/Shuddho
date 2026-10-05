from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from services.coworker.models import utcnow
from services.coworker.action_registry import action_spec, registered_transaction_operations
from scripts.shopping_checkout_provider_qualification import (
    ShoppingCheckoutQualificationError,
    validate_checkout_provider_qualification,
)


REVISION = "a" * 40
EVIDENCE_SHA = "b" * 64


def evidence():
    now = utcnow()
    return {
        "schema_version": 1,
        "provider": "merchantx",
        "adapter_revision": REVISION,
        "checkout_origin": "https://checkout.merchantx.example",
        "credential_boundary": {
            "storage": "credential_broker",
            "server_side_only": True,
            "least_privilege": True,
            "scopes": ["checkout.read", "checkout.create", "orders.read"],
            "raw_payment_credentials": False,
        },
        "idempotency": {
            "supported": True,
            "key_scope": "checkout_binding",
            "duplicate_result": "same_order_or_lookup",
        },
        "reconciliation": {
            "supported": True,
            "lookup_keys": ["idempotency_key", "provider_order_id"],
            "outcome_unknown_policy": "lookup_before_retry",
            "blind_retry": False,
        },
        "receipt": {
            "readback_supported": True,
            "exact_fields": [
                "provider_order_id",
                "merchant_cart_id",
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
            "payment_instrument_to_shuddho": False,
            "identity_model": "merchant_hosted_user_present",
        },
        "payment_boundary": {
            "mode": "merchant_hosted_user_present",
            "shuddho_charges": False,
            "stores_payment_instrument": False,
            "requires_user_present": True,
        },
        "live_probe": {
            "status": "passed",
            "environment": "staging",
            "verified_at": (now - timedelta(minutes=10)).isoformat(),
            "source_revision": REVISION,
            "checkout_origin": "https://checkout.merchantx.example",
            "idempotency_passed": True,
            "reconciliation_passed": True,
            "receipt_match_passed": True,
            "privacy_passed": True,
            "payment_boundary_passed": True,
            "evidence_sha256": EVIDENCE_SHA,
        },
    }


def test_tx14_accepts_exact_provider_qualification_but_grants_no_authority():
    now = utcnow()
    result = validate_checkout_provider_qualification(evidence(), now=now)

    assert result["provider"] == "merchantx"
    assert result["operation"] == "merchantx:shopping_checkout_create"
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["payment_authority"] is False
    assert len(result["qualification_sha256"]) == 64

    with pytest.raises(Exception):
        action_spec("shopping_checkout_create")
    assert all(
        "shopping_checkout_create" not in item
        for item in registered_transaction_operations()
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("credential_boundary", "raw_payment_credentials"), True),
        (("credential_boundary", "server_side_only"), False),
        (("idempotency", "supported"), False),
        (("reconciliation", "blind_retry"), True),
        (("receipt", "readback_supported"), False),
        (("privacy", "payment_instrument_to_shuddho"), True),
        (("privacy", "secrets_in_logs"), True),
        (("payment_boundary", "shuddho_charges"), True),
        (("payment_boundary", "stores_payment_instrument"), True),
        (("payment_boundary", "requires_user_present"), False),
        (("live_probe", "receipt_match_passed"), False),
    ],
)
def test_tx14_fails_closed_on_unsafe_provider_evidence(path, value):
    item = evidence()
    item[path[0]][path[1]] = value
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())


def test_tx14_rejects_nonproduction_placeholder_provider():
    item = evidence()
    item["provider"] = "simulated"
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())


def test_tx14_rejects_revision_or_origin_mismatch():
    item = evidence()
    item["live_probe"]["source_revision"] = "c" * 40
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())

    item = evidence()
    item["live_probe"]["checkout_origin"] = "https://other.example"
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())


def test_tx14_rejects_stale_or_future_probe():
    item = evidence()
    item["live_probe"]["verified_at"] = (utcnow() - timedelta(hours=25)).isoformat()
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())

    item = evidence()
    item["live_probe"]["verified_at"] = (utcnow() + timedelta(minutes=5)).isoformat()
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())


def test_tx14_qualification_hash_is_canonical_for_scope_ordering():
    first = evidence()
    second = deepcopy(first)
    second["credential_boundary"]["scopes"] = list(reversed(second["credential_boundary"]["scopes"]))
    second["reconciliation"]["lookup_keys"] = list(reversed(second["reconciliation"]["lookup_keys"]))
    second["receipt"]["exact_fields"] = list(reversed(second["receipt"]["exact_fields"]))

    a = validate_checkout_provider_qualification(first, now=utcnow())
    b = validate_checkout_provider_qualification(second, now=utcnow())
    assert a["qualification_sha256"] == b["qualification_sha256"]


def test_tx14_rejects_dirty_origin_and_unexpected_schema():
    item = evidence()
    item["checkout_origin"] = "https://user:pass@checkout.merchantx.example"
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())

    item = evidence()
    item["unexpected"] = True
    with pytest.raises(ShoppingCheckoutQualificationError):
        validate_checkout_provider_qualification(item, now=utcnow())
