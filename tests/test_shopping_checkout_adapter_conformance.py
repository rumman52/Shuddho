from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from scripts.shopping_checkout_provider_qualification import (
    validate_checkout_provider_qualification,
)
from scripts.shopping_checkout_registration_proposal import (
    compile_registration_proposal,
)
from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
)
from services.coworker.shopping_checkout_adapter_conformance import (
    ShoppingCheckoutAdapterConformanceError,
    exercise_shopping_checkout_adapter,
)


REVISION = "a" * 40
PROBE_SHA = "b" * 64
ORIGIN = "https://checkout.merchantx.example"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def tx14_source(now: datetime) -> dict:
    return {
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


def qualification(now: datetime) -> dict:
    return validate_checkout_provider_qualification(
        tx14_source(now),
        now=now,
    )


def proposal(now: datetime, q: dict) -> dict:
    review = {
        "schema_version": 1,
        "provider": q["provider"],
        "operation": q["operation"],
        "adapter_revision": q["adapter_revision"],
        "checkout_origin": q["checkout_origin"],
        "qualification_sha256": q["qualification_sha256"],
        "action_contract_version": 1,
        "change_reference": "TX23-reviewed-change",
        "reviewed_at": now.isoformat(),
        "reviewer_reference": "security-reviewer",
    }
    return compile_registration_proposal(q, review, now=now)


def preview(now: datetime, *, expires_in_minutes: int = 10) -> dict:
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


class StagingCheckoutAdapter:
    provider_name = "merchantx"
    adapter_revision = REVISION
    checkout_origin = ORIGIN
    credential_scopes = frozenset({"checkout.create", "checkout.read", "orders.read"})
    action_kind = "shopping_checkout_create"
    contract_version = 1
    supports_idempotency = True
    supports_lookup_by_idempotency_key = True
    supports_lookup_by_provider_order_id = True
    payment_mode = "merchant_hosted_user_present"
    receives_payment_instrument = False

    implementation_test_only = True
    implementation_test_environment = "staging"
    implementation_test_origin = ORIGIN

    def __init__(self, now: datetime):
        self.now = now
        self.create_calls: list[tuple[dict, str]] = []
        self.lookup_calls: list[tuple[str | None, str | None]] = []
        self.by_key: dict[str, dict] = {}

    async def create_checkout_handoff(
        self,
        *,
        preview: dict,
        idempotency_key: str,
    ) -> dict:
        self.create_calls.append((preview, idempotency_key))
        existing = self.by_key.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        handoff = {
            "handoff_id": "checkout-session-123",
            "handoff_url": ORIGIN + "/session/123?token=opaque",
        }
        self.by_key[idempotency_key] = dict(handoff)
        return handoff

    async def lookup_checkout_receipt(
        self,
        *,
        idempotency_key: str | None = None,
        provider_order_id: str | None = None,
    ) -> dict | None:
        self.lookup_calls.append((idempotency_key, provider_order_id))
        return None

def run(adapter: StagingCheckoutAdapter, now: datetime, **overrides):
    q = overrides.pop("qualification_value", qualification(now))
    proposal_value = overrides.pop("proposal_value", None)
    if proposal_value is None:
        proposal_value = proposal(now, q)
    kwargs = {
        "preview_value": preview(now),
        "allow_provider_test_io": True,
        "now": now,
    }
    kwargs.update(overrides)
    return asyncio.run(
        exercise_shopping_checkout_adapter(
            proposal_value,
            q,
            adapter,
            **kwargs,
        )
    )


def test_tx23_exercises_hosted_staging_adapter_and_keeps_runtime_closed():
    now = utcnow()
    adapter = StagingCheckoutAdapter(now)

    result = run(adapter, now)

    assert result["schema_version"] == 2
    assert result["status"] == "provider_handoff_conformance_passed"
    assert result["staging_provider_io"] is True
    assert result["provider_called"] is True
    assert result["provider_test_environment"] == "staging"
    assert result["handoff_attempts"] == 2
    assert result["receipt_lookup_attempts"] == 2
    assert result["completion_receipt_observed"] is False
    assert len(result["handoff_sha256"]) == 64
    assert result["registration_proposal_sha256"]
    assert result["evaluated_at"] == now.isoformat()
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(adapter.create_calls) == 2
    assert len(adapter.lookup_calls) == 2
    assert adapter.create_calls[0][1] == adapter.create_calls[1][1]

    with pytest.raises(Exception):
        action_spec("shopping_checkout_create")
    assert all(
        "shopping_checkout_create" not in item
        for item in registered_transaction_operations()
    )


def test_tx23_requires_explicit_provider_io_opt_in_before_calls():
    now = utcnow()
    adapter = StagingCheckoutAdapter(now)
    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(adapter, now, allow_provider_test_io=False)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx23_rejects_non_staging_adapter_before_calls():
    now = utcnow()
    adapter = StagingCheckoutAdapter(now)
    adapter.implementation_test_environment = "production"
    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(adapter, now)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx23_rejects_unreviewed_origin_before_calls():
    now = utcnow()
    adapter = StagingCheckoutAdapter(now)
    adapter.implementation_test_origin = "https://different.example"
    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(adapter, now)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx23_rejects_tampered_tx14_qualification_before_calls():
    now = utcnow()
    adapter = StagingCheckoutAdapter(now)
    reviewed = qualification(now)
    proposal_value = proposal(now, reviewed)
    tampered = {
        **reviewed,
        "live_probe": {
            **reviewed["live_probe"],
            "checkout_origin": "https://different.example",
        },
    }
    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(
            adapter,
            now,
            qualification_value=tampered,
            proposal_value=proposal_value,
        )
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx23_rejects_expired_preview_before_calls():
    now = utcnow()
    adapter = StagingCheckoutAdapter(now)
    value = preview(now, expires_in_minutes=-1)
    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(adapter, now, preview_value=value)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx23_rejects_non_idempotent_handoff():
    now = utcnow()

    class NonIdempotentAdapter(StagingCheckoutAdapter):
        async def create_checkout_handoff(
            self,
            *,
            preview: dict,
            idempotency_key: str,
        ) -> dict:
            value = await super().create_checkout_handoff(
                preview=preview,
                idempotency_key=idempotency_key,
            )
            if len(self.create_calls) > 1:
                return {
                    "handoff_id": "checkout-session-different",
                    "handoff_url": ORIGIN + "/session/different",
                }
            return value

    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(NonIdempotentAdapter(now), now)


def test_tx23_rejects_immediate_confirmed_receipt_before_user_completion():
    now = utcnow()

    class PrematureReceiptAdapter(StagingCheckoutAdapter):
        async def lookup_checkout_receipt(
            self,
            *,
            idempotency_key: str | None = None,
            provider_order_id: str | None = None,
        ) -> dict | None:
            self.lookup_calls.append((idempotency_key, provider_order_id))
            if self.create_calls:
                return {
                    "provider": "merchantx",
                    "provider_order_id": "order-123",
                    "merchant_cart_id": "cart-123",
                    "currency": "USD",
                    "total_minor": 12500,
                    "status": "confirmed",
                    "confirmed_at": now.isoformat(),
                }
            return None

    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(PrematureReceiptAdapter(now), now)


def test_tx23_rejects_invalid_handoff_url():
    now = utcnow()

    class BadHandoffAdapter(StagingCheckoutAdapter):
        async def create_checkout_handoff(
            self,
            *,
            preview: dict,
            idempotency_key: str,
        ) -> dict:
            self.create_calls.append((preview, idempotency_key))
            return {
                "handoff_id": "checkout-session-123",
                "handoff_url": "https://evil.example/session/123",
            }

    with pytest.raises(ShoppingCheckoutAdapterConformanceError):
        run(BadHandoffAdapter(now), now)
