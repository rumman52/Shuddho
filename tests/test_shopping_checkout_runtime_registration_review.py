from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.shopping_checkout_runtime_registration_review import (
    ShoppingCheckoutRuntimeRegistrationReviewError,
    compile_runtime_registration_review,
)
from tests.test_shopping_checkout_adapter_conformance import (
    StagingCheckoutAdapter,
    qualification,
    proposal,
    preview,
)
from services.coworker.shopping_checkout_adapter_conformance import (
    exercise_shopping_checkout_adapter,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def conformance(now: datetime, proposal_value: dict, q: dict) -> dict:
    return asyncio.run(
        exercise_shopping_checkout_adapter(
            proposal_value,
            q,
            StagingCheckoutAdapter(now),
            preview_value=preview(now),
            allow_provider_test_io=True,
            now=now,
        )
    )


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
    c = conformance(now, p, q)

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
    c = conformance(now, p, q)
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
    c = conformance(now, p, q)
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
    c = conformance(now, p, q)

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
    c = conformance(now, p, q)

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
    c = conformance(now, p, q)
    bad = deepcopy(c)
    bad["runtime_enabled"] = True
    unsigned = dict(bad)
    unsigned.pop("conformance_sha256")
    from services.coworker.action_registry import stable_digest
    bad["conformance_sha256"] = stable_digest(unsigned)

    with pytest.raises(ShoppingCheckoutRuntimeRegistrationReviewError):
        compile_runtime_registration_review(
            p,
            bad,
            review(now, p, c),
            now=now + timedelta(seconds=2),
        )
