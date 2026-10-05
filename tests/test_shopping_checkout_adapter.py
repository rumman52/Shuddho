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
from services.coworker.action_registry import action_spec, registered_transaction_operations
from services.coworker.shopping_checkout_adapter import (
    ShoppingCheckoutAdapterAdmissionError,
    admit_checkout_adapter,
)


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
            "checkout_origin": "https://checkout.merchantx.example",
            "idempotency_passed": True,
            "reconciliation_passed": True,
            "receipt_match_passed": True,
            "privacy_passed": True,
            "payment_boundary_passed": True,
            "evidence_sha256": PROBE_SHA,
        },
    }


def proposal():
    now = utcnow()
    qualification = validate_checkout_provider_qualification(
        tx14_source(),
        now=now,
    )
    review = {
        "schema_version": 1,
        "provider": qualification["provider"],
        "operation": qualification["operation"],
        "adapter_revision": qualification["adapter_revision"],
        "checkout_origin": qualification["checkout_origin"],
        "qualification_sha256": qualification["qualification_sha256"],
        "action_contract_version": 1,
        "change_reference": "TX16-reviewed-change",
        "reviewed_at": now.isoformat(),
        "reviewer_reference": "security-reviewer",
    }
    return compile_registration_proposal(
        qualification,
        review,
        now=now,
    )


class QualifiedAdapter:
    provider_name = "merchantx"
    adapter_revision = REVISION
    checkout_origin = "https://checkout.merchantx.example"
    credential_scopes = frozenset({"checkout.create", "checkout.read", "orders.read"})
    action_kind = "shopping_checkout_create"
    contract_version = 1
    supports_idempotency = True
    supports_lookup_by_idempotency_key = True
    supports_lookup_by_provider_order_id = True
    payment_mode = "merchant_hosted_user_present"
    receives_payment_instrument = False

    def __init__(self):
        self.create_calls = []
        self.lookup_calls = []

    async def create_checkout(self, *, preview: dict, idempotency_key: str) -> dict:
        self.create_calls.append((preview, idempotency_key))
        raise AssertionError("TX-16 admission must not call the provider")

    async def lookup_checkout(
        self,
        *,
        idempotency_key: str | None = None,
        provider_order_id: str | None = None,
    ) -> dict | None:
        self.lookup_calls.append((idempotency_key, provider_order_id))
        raise AssertionError("TX-16 admission must not call the provider")


def test_tx16_admits_exact_adapter_for_implementation_tests_only():
    adapter = QualifiedAdapter()
    result = admit_checkout_adapter(
        proposal(),
        adapter,
        now=utcnow(),
    )

    assert result["status"] == "admitted_for_provider_implementation_tests"
    assert result["provider"] == "merchantx"
    assert result["operation"] == "merchantx:shopping_checkout_create"
    assert result["provider_called"] is False
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["payment_authority"] is False
    assert len(result["adapter_admission_sha256"]) == 64
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []

    with pytest.raises(Exception):
        action_spec("shopping_checkout_create")
    assert all(
        "shopping_checkout_create" not in item
        for item in registered_transaction_operations()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_name", "other"),
        ("adapter_revision", "c" * 40),
        ("checkout_origin", "https://other.example"),
        ("action_kind", "other_action"),
        ("contract_version", 2),
        ("supports_idempotency", False),
        ("supports_lookup_by_idempotency_key", False),
        ("supports_lookup_by_provider_order_id", False),
        ("payment_mode", "shuddho_direct"),
        ("receives_payment_instrument", True),
    ],
)
def test_tx16_rejects_adapter_metadata_drift(field, value):
    adapter = QualifiedAdapter()
    setattr(adapter, field, value)
    with pytest.raises(ShoppingCheckoutAdapterAdmissionError):
        admit_checkout_adapter(
            proposal(),
            adapter,
            now=utcnow(),
        )


def test_tx16_rejects_scope_drift():
    adapter = QualifiedAdapter()
    adapter.credential_scopes = frozenset({"checkout.create", "checkout.admin"})
    with pytest.raises(ShoppingCheckoutAdapterAdmissionError):
        admit_checkout_adapter(
            proposal(),
            adapter,
            now=utcnow(),
        )


def test_tx16_rejects_tampered_registration_proposal():
    value = proposal()
    value["adapter_revision"] = "c" * 40
    with pytest.raises(ShoppingCheckoutAdapterAdmissionError) as error:
        admit_checkout_adapter(value, QualifiedAdapter(), now=utcnow())
    assert "digest" in str(error.value).lower() or "match" in str(error.value).lower()


def test_tx16_rejects_registration_proposal_claiming_runtime_authority():
    value = proposal()
    value["runtime_enabled"] = True
    with pytest.raises(ShoppingCheckoutAdapterAdmissionError):
        admit_checkout_adapter(value, QualifiedAdapter(), now=utcnow())


def test_tx16_rejects_non_async_adapter_methods():
    class SyncAdapter(QualifiedAdapter):
        def create_checkout(self, *, preview: dict, idempotency_key: str) -> dict:
            return {}

    with pytest.raises(ShoppingCheckoutAdapterAdmissionError):
        admit_checkout_adapter(
            proposal(),
            SyncAdapter(),
            now=utcnow(),
        )


def test_tx16_rejects_stale_registration_review():
    value = proposal()
    reviewed = datetime.fromisoformat(value["reviewed_at"])
    value["reviewed_at"] = (reviewed - timedelta(days=15)).isoformat()

    unsigned = deepcopy(value)
    unsigned.pop("registration_proposal_sha256")
    from services.coworker.shopping_checkout_adapter import canonical_sha256
    value["registration_proposal_sha256"] = canonical_sha256(unsigned)

    with pytest.raises(ShoppingCheckoutAdapterAdmissionError):
        admit_checkout_adapter(
            value,
            QualifiedAdapter(),
            now=utcnow(),
        )
