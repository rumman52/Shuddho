from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.shopping_checkout_provider_qualification import (
    validate_checkout_provider_qualification,
)
from scripts.shopping_checkout_registration_proposal import (
    ShoppingCheckoutRegistrationProposalError,
    compile_registration_proposal,
)
from services.coworker.action_registry import action_spec, registered_transaction_operations


REVISION = "a" * 40
PROBE_SHA = "b" * 64


def utcnow():
    return datetime.now(timezone.utc)


def tx14_source():
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
            "evidence_sha256": PROBE_SHA,
        },
    }


def qualification():
    return validate_checkout_provider_qualification(tx14_source(), now=utcnow())


def review(q=None, **changes):
    q = q or qualification()
    value = {
        "schema_version": 1,
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "checkout_origin": q["checkout_origin"],
        "qualification_sha256": q["qualification_sha256"],
        "action_contract_version": 1,
        "change_reference": "TX15-reviewed-change",
        "reviewed_at": utcnow().isoformat(),
        "reviewer_reference": "security-reviewer",
    }
    value.update(changes)
    return value


def test_tx15_compiles_exact_inert_registration_proposal():
    q = qualification()
    result = compile_registration_proposal(q, review(q), now=utcnow())

    assert result["status"] == "eligible_for_provider_implementation_review"
    assert result["provider"] == q["provider"]
    assert result["operation"] == "merchantx:shopping_checkout_create"
    assert result["adapter_revision"] == q["adapter_revision"]
    assert result["checkout_origin"] == q["checkout_origin"]
    assert result["qualification_sha256"] == q["qualification_sha256"]
    assert result["action_contract"] == {
        "kind": "shopping_checkout_create",
        "version": 1,
        "source": "TX-13",
    }
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["payment_authority"] is False
    assert len(result["registration_proposal_sha256"]) == 64

    with pytest.raises(Exception):
        action_spec("shopping_checkout_create")
    assert all(
        "shopping_checkout_create" not in item
        for item in registered_transaction_operations()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other"),
        ("operation", "merchantx:other"),
        ("adapter_revision", "c" * 40),
        ("checkout_origin", "https://other.example"),
        ("qualification_sha256", "d" * 64),
    ],
)
def test_tx15_rejects_registration_review_drift(field, value):
    q = qualification()
    item = review(q)
    item[field] = value
    with pytest.raises(ShoppingCheckoutRegistrationProposalError):
        compile_registration_proposal(q, item, now=utcnow())


def test_tx15_rejects_tampered_tx14_qualification_even_with_original_hash():
    q = qualification()
    tampered = deepcopy(q)
    tampered["credential_boundary"]["scopes"] = ["checkout.admin"]
    with pytest.raises(ShoppingCheckoutRegistrationProposalError) as error:
        compile_registration_proposal(tampered, review(q), now=utcnow())
    assert "digest" in str(error.value).lower()


def test_tx15_rejects_tx14_evidence_that_claims_runtime_authority():
    q = qualification()
    q["registration_authority"] = True
    with pytest.raises(ShoppingCheckoutRegistrationProposalError):
        compile_registration_proposal(q, review(qualification()), now=utcnow())


def test_tx15_rejects_wrong_contract_version():
    q = qualification()
    with pytest.raises(ShoppingCheckoutRegistrationProposalError):
        compile_registration_proposal(
            q,
            review(q, action_contract_version=2),
            now=utcnow(),
        )


def test_tx15_rejects_stale_or_future_review():
    q = qualification()
    with pytest.raises(ShoppingCheckoutRegistrationProposalError):
        compile_registration_proposal(
            q,
            review(q, reviewed_at=(utcnow() - timedelta(days=8)).isoformat()),
            now=utcnow(),
        )

    with pytest.raises(ShoppingCheckoutRegistrationProposalError):
        compile_registration_proposal(
            q,
            review(q, reviewed_at=(utcnow() + timedelta(minutes=5)).isoformat()),
            now=utcnow(),
        )


def test_tx15_rejects_unexpected_review_schema():
    q = qualification()
    item = review(q)
    item["unexpected"] = True
    with pytest.raises(ShoppingCheckoutRegistrationProposalError):
        compile_registration_proposal(q, item, now=utcnow())


def test_tx15_proposal_hash_is_canonical_for_qualified_scope_ordering():
    source = tx14_source()
    reordered = deepcopy(source)
    reordered["credential_boundary"]["scopes"] = list(
        reversed(reordered["credential_boundary"]["scopes"])
    )
    reordered["reconciliation"]["lookup_keys"] = list(
        reversed(reordered["reconciliation"]["lookup_keys"])
    )
    reordered["receipt"]["exact_fields"] = list(
        reversed(reordered["receipt"]["exact_fields"])
    )

    now = utcnow()
    q1 = validate_checkout_provider_qualification(source, now=now)
    q2 = validate_checkout_provider_qualification(reordered, now=now)
    assert q1["qualification_sha256"] == q2["qualification_sha256"]

    reviewed_at = now.isoformat()
    r1 = review(q1, reviewed_at=reviewed_at)
    r2 = review(q2, reviewed_at=reviewed_at)
    p1 = compile_registration_proposal(q1, r1, now=now)
    p2 = compile_registration_proposal(q2, r2, now=now)
    assert p1["registration_proposal_sha256"] == p2["registration_proposal_sha256"]
