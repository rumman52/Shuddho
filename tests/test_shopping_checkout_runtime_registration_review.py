from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.shopping_checkout_provider_qualification import (
    validate_checkout_provider_qualification,
)
from scripts.shopping_checkout_registration_proposal import (
    compile_registration_proposal,
)
from scripts.shopping_checkout_runtime_registration_review import (
    ShoppingCheckoutRuntimeRegistrationReviewError,
    compile_runtime_registration_review,
)
from services.coworker.action_registry import stable_digest


REVISION = "a" * 40
PROBE_SHA = "b" * 64
ORIGIN = "https://checkout.merchantx.example"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def qualification(now: datetime) -> dict:
    source = {
        "schema_version": 1,
        "provider": "merchantx",
        "adapter_revision": REVISION,
        "checkout_origin": ORIGIN,
        "credential_boundary": {
            "storage": "credential_broker",
            "server_side_only": True,
            "least_privilege": True,
            "scopes": ["checkout.create", "checkout.read", "orders.read"],
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
            "verified_at": (now - timedelta(minutes=5)).isoformat(),
            "source_revision": REVISION,
            "checkout_origin": ORIGIN,
            "idempotency_passed": True,
            "reconciliation_passed": True,
            "receipt_match_passed": True,
            "privacy_passed": True,
            "payment_boundary_passed": True,
            "evidence_sha256": PROBE_SHA,
        },
    }
    return validate_checkout_provider_qualification(source, now=now)


def proposal(now: datetime, q: dict) -> dict:
    review = {
        "schema_version": 1,
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "checkout_origin": q["checkout_origin"],
        "qualification_sha256": q["qualification_sha256"],
        "action_contract_version": 1,
        "change_reference": "TX24-proposal-review",
        "reviewed_at": now.isoformat(),
        "reviewer_reference": "security-reviewer",
    }
    return compile_registration_proposal(q, review, now=now)


def conformance(now: datetime, p: dict) -> dict:
    value = {
        "schema_version": 1,
        "status": "provider_implementation_conformance_passed",
        "provider": p["provider"],
        "operation": p["operation"],
        "adapter_revision": p["adapter_revision"],
        "checkout_origin": p["checkout_origin"],
        "qualification_sha256": p["qualification_sha256"],
        "registration_proposal_sha256": p["registration_proposal_sha256"],
        "live_probe_evidence_sha256": PROBE_SHA,
        "adapter_admission_sha256": "c" * 64,
        "preview_sha256": "d" * 64,
        "receipt_sha256": "e" * 64,
        "idempotency_key_sha256": "f" * 64,
        "provider_test_environment": "staging",
        "staging_provider_io": True,
        "provider_called": True,
        "create_attempts": 2,
        "lookup_attempts": 3,
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
        "registration_proposal_sha256": p["registration_proposal_sha256"],
        "conformance_sha256": c["conformance_sha256"],
        "decision": "approved_for_runtime_registration_review",
        "change_reference": "TX24-reviewed-change",
        "reviewer_reference": "security-reviewer",
        "reviewed_at": (now + timedelta(seconds=1)).isoformat(),
    }
    value.update(changes)
    return value


def test_tx24_compiles_inert_runtime_registration_review():
    now = utcnow()
    q = qualification(now)
    p = proposal(now, q)
    c = conformance(now, p)

    result = compile_runtime_registration_review(
        p,
        c,
        review(now, p, c),
        now=now + timedelta(seconds=2),
    )

    assert result["status"] == "eligible_for_runtime_registration_review"
    assert result["provider"] == p["provider"]
    assert result["operation"] == p["operation"]
    assert result["registration_proposal_sha256"] == p["registration_proposal_sha256"]
    assert result["conformance_sha256"] == c["conformance_sha256"]
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["runtime_registration_review_sha256"]) == 64


def test_tx24_rejects_tampered_conformance():
    now = utcnow()
    q = qualification(now)
    p = proposal(now, q)
    c = conformance(now, p)
    bad = deepcopy(c)
    bad["receipt_sha256"] = "0" * 64

    with pytest.raises(ShoppingCheckoutRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p,
            bad,
            review(now, p, c),
            now=now + timedelta(seconds=2),
        )


def test_tx24_rejects_conformance_from_different_proposal():
    now = utcnow()
    q = qualification(now)
    p = proposal(now, q)
    c = conformance(now, p)
    other = deepcopy(p)
    other["registration_proposal_sha256"] = "f" * 64

    with pytest.raises(ShoppingCheckoutRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            other,
            c,
            review(now, p, c),
            now=now + timedelta(seconds=2),
        )


def test_tx24_rejects_review_before_conformance():
    now = utcnow()
    q = qualification(now)
    p = proposal(now, q)
    c = conformance(now, p)

    with pytest.raises(ShoppingCheckoutRuntimeRegistrationReviewError):
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


def test_tx24_rejects_review_hash_drift():
    now = utcnow()
    q = qualification(now)
    p = proposal(now, q)
    c = conformance(now, p)

    with pytest.raises(ShoppingCheckoutRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p,
            c,
            review(now, p, c, conformance_sha256="e" * 64),
            now=now + timedelta(seconds=2),
        )


def test_tx24_rejects_runtime_authority_in_conformance():
    now = utcnow()
    q = qualification(now)
    p = proposal(now, q)
    c = conformance(now, p)
    bad = deepcopy(c)
    bad["runtime_enabled"] = True
    unsigned = dict(bad)
    unsigned.pop("conformance_sha256")
    bad["conformance_sha256"] = stable_digest(unsigned)

    with pytest.raises(ShoppingCheckoutRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p,
            bad,
            review(now, p, c),
            now=now + timedelta(seconds=2),
        )
