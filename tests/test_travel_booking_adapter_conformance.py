from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
)
from services.coworker.travel_booking_adapter import canonical_sha256
from services.coworker.travel_booking_adapter_conformance import (
    TravelBookingAdapterConformanceError,
    exercise_travel_booking_adapter,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def proposal(now: datetime) -> dict:
    traveler = {
        "required_fields": ["date_of_birth", "email", "legal_name"],
        "shuddho_transmitted_fields": ["email", "legal_name"],
        "provider_hosted_fields": ["date_of_birth"],
        "document_images_to_shuddho": False,
        "payment_instrument_to_shuddho": False,
        "optional_fields_default_off": True,
    }
    value = {
        "schema_version": 1,
        "status": "eligible_for_provider_implementation_review",
        "provider": "travelco",
        "operation": "travelco:travel_booking_create",
        "adapter_revision": "a" * 40,
        "booking_origin": "https://booking.travelco.example",
        "travel_kind": "flight",
        "qualification_sha256": "b" * 64,
        "action_contract": {
            "kind": "travel_booking_create",
            "version": 1,
            "source": "TX-18",
        },
        "credential_scopes": ["booking.create", "booking.read"],
        "traveler_data_boundary": traveler,
        "traveler_data_boundary_sha256": canonical_sha256(traveler),
        "idempotency": {
            "supported": True,
            "key_scope": "booking_binding",
            "duplicate_result": "same_booking_or_lookup",
        },
        "reconciliation": {
            "supported": True,
            "lookup_keys": ["idempotency_key", "provider_booking_id"],
            "outcome_unknown_policy": "lookup_before_retry",
            "blind_retry": False,
        },
        "receipt": {
            "readback_supported": True,
            "exact_fields": [
                "confirmed_at",
                "currency",
                "provider_booking_id",
                "provider_quote_id",
                "status",
                "total_minor",
                "travel_kind",
            ],
            "confirmed_status": "confirmed",
        },
        "privacy": {
            "sends_only_required_fields": True,
            "secrets_in_logs": False,
            "retains_traveler_data_in_logs": False,
            "provider_hosted_collection_supported": True,
        },
        "payment_boundary": {
            "mode": "provider_hosted_user_present",
            "shuddho_charges": False,
            "stores_payment_instrument": False,
            "requires_user_present": True,
        },
        "change_reference": "TX22-reviewed-change",
        "reviewed_at": now.isoformat(),
        "reviewer_reference": "security-reviewer",
        "registry_change_required": True,
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    value["registration_proposal_sha256"] = canonical_sha256(value)
    return value


def preview(now: datetime) -> dict:
    return {
        "schema_version": 1,
        "kind": "travel_booking_create",
        "booking_binding_id": str(uuid4()),
        "transaction_id": str(uuid4()),
        "verification_id": str(uuid4()),
        "transaction_revision": 1,
        "terms_revision": 1,
        "terms_sha256": "1" * 64,
        "quote_sha256": "2" * 64,
        "verification_snapshot_sha256": "3" * 64,
        "travel_kind": "flight",
        "provider": "travelco",
        "provider_quote_id": "quote-123",
        "currency": "USD",
        "total_minor": 12500,
        "booking_binding_scope_sha256": "4" * 64,
        "prepared_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "execution_authority": "not_registered",
        "identity_authority": "not_bound",
        "payment_authority": "not_authorized",
    }


class SandboxTravelAdapter:
    provider_name = "travelco"
    adapter_revision = "a" * 40
    booking_origin = "https://booking.travelco.example"
    travel_kind = "flight"
    credential_scopes = frozenset({"booking.create", "booking.read"})
    action_kind = "travel_booking_create"
    contract_version = 1
    required_traveler_fields = frozenset({"legal_name", "date_of_birth", "email"})
    shuddho_transmitted_fields = frozenset({"legal_name", "email"})
    provider_hosted_fields = frozenset({"date_of_birth"})
    traveler_data_boundary_sha256 = canonical_sha256(
        {
            "required_fields": ["date_of_birth", "email", "legal_name"],
            "shuddho_transmitted_fields": ["email", "legal_name"],
            "provider_hosted_fields": ["date_of_birth"],
            "document_images_to_shuddho": False,
            "payment_instrument_to_shuddho": False,
            "optional_fields_default_off": True,
        }
    )
    supports_idempotency = True
    supports_lookup_by_idempotency_key = True
    supports_lookup_by_provider_booking_id = True
    supports_provider_hosted_collection = True
    payment_mode = "provider_hosted_user_present"
    receives_payment_instrument = False
    receives_document_images = False
    retains_traveler_data_in_logs = False

    implementation_test_only = True
    implementation_test_environment = "sandbox"
    implementation_test_origin = "https://booking.travelco.example"

    def __init__(self, now: datetime):
        self.now = now
        self.create_calls: list[tuple[dict, dict, str]] = []
        self.lookup_calls: list[tuple[str | None, str | None]] = []
        self.by_key: dict[str, dict] = {}

    async def create_booking_handoff(
        self,
        *,
        preview: dict,
        traveler_data: dict,
        idempotency_key: str,
    ) -> dict:
        self.create_calls.append((preview, traveler_data, idempotency_key))
        existing = self.by_key.get(idempotency_key)
        if existing is not None:
            return dict(existing)
        handoff = {
            "handoff_id": "booking-session-123",
            "handoff_url": self.booking_origin + "/continue/123?token=opaque",
        }
        self.by_key[idempotency_key] = dict(handoff)
        return handoff

    async def lookup_booking_receipt(
        self,
        *,
        idempotency_key: str | None = None,
        provider_booking_id: str | None = None,
    ) -> dict | None:
        self.lookup_calls.append((idempotency_key, provider_booking_id))
        return None

def run(adapter: SandboxTravelAdapter, now: datetime, **overrides):
    kwargs = {
        "preview_value": preview(now),
        "traveler_data": {
            "email": "user@example.com",
            "legal_name": "Test Traveler",
        },
        "allow_provider_test_io": True,
        "now": now,
    }
    kwargs.update(overrides)
    return asyncio.run(
        exercise_travel_booking_adapter(
            proposal(now),
            adapter,
            **kwargs,
        )
    )


def test_tx22_exercises_hosted_sandbox_adapter_and_keeps_runtime_closed():
    now = utcnow()
    adapter = SandboxTravelAdapter(now)

    result = run(adapter, now)

    assert result["schema_version"] == 2
    assert result["status"] == "provider_handoff_conformance_passed"
    assert result["sandbox_provider_io"] is True
    assert result["provider_called"] is True
    assert result["handoff_attempts"] == 2
    assert result["receipt_lookup_attempts"] == 2
    assert result["completion_receipt_observed"] is False
    assert len(result["handoff_sha256"]) == 64
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert result["traveler_fields_sent"] == ["email", "legal_name"]
    assert result["registration_proposal_sha256"]
    assert result["qualification_sha256"]
    assert result["evaluated_at"] == now.isoformat()
    assert len(adapter.create_calls) == 2
    assert len(adapter.lookup_calls) == 2
    assert adapter.create_calls[0][2] == adapter.create_calls[1][2]

    with pytest.raises(Exception):
        action_spec("travel_booking_create")
    assert all(
        "travel_booking_create" not in item
        for item in registered_transaction_operations()
    )


def test_tx22_requires_explicit_provider_io_opt_in_before_calls():
    now = utcnow()
    adapter = SandboxTravelAdapter(now)
    with pytest.raises(TravelBookingAdapterConformanceError):
        run(adapter, now, allow_provider_test_io=False)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx22_rejects_non_sandbox_adapter_before_calls():
    now = utcnow()
    adapter = SandboxTravelAdapter(now)
    adapter.implementation_test_environment = "production"
    with pytest.raises(TravelBookingAdapterConformanceError):
        run(adapter, now)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx22_rejects_unreviewed_sandbox_origin_before_calls():
    now = utcnow()
    adapter = SandboxTravelAdapter(now)
    adapter.implementation_test_origin = "https://different-sandbox.example"
    with pytest.raises(TravelBookingAdapterConformanceError):
        run(adapter, now)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx22_rejects_unreviewed_traveler_fields_before_calls():
    now = utcnow()
    adapter = SandboxTravelAdapter(now)
    with pytest.raises(TravelBookingAdapterConformanceError):
        run(
            adapter,
            now,
            traveler_data={
                "email": "user@example.com",
                "legal_name": "Test Traveler",
                "passport_number": "P1234567",
            },
        )
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx22_rejects_expired_preview_before_calls():
    now = utcnow()
    adapter = SandboxTravelAdapter(now)
    value = preview(now)
    value["expires_at"] = (now - timedelta(seconds=1)).isoformat()
    with pytest.raises(TravelBookingAdapterConformanceError):
        run(adapter, now, preview_value=value)
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []


def test_tx22_rejects_non_idempotent_handoff():
    now = utcnow()

    class NonIdempotentAdapter(SandboxTravelAdapter):
        async def create_booking_handoff(
            self,
            *,
            preview: dict,
            traveler_data: dict,
            idempotency_key: str,
        ) -> dict:
            value = await super().create_booking_handoff(
                preview=preview,
                traveler_data=traveler_data,
                idempotency_key=idempotency_key,
            )
            if len(self.create_calls) > 1:
                return {
                    "handoff_id": "booking-session-different",
                    "handoff_url": self.booking_origin + "/continue/different",
                }
            return value

    with pytest.raises(TravelBookingAdapterConformanceError):
        run(NonIdempotentAdapter(now), now)


def test_tx22_rejects_immediate_confirmed_receipt_before_user_completion():
    now = utcnow()

    class PrematureReceiptAdapter(SandboxTravelAdapter):
        async def lookup_booking_receipt(
            self,
            *,
            idempotency_key: str | None = None,
            provider_booking_id: str | None = None,
        ) -> dict | None:
            self.lookup_calls.append((idempotency_key, provider_booking_id))
            if self.create_calls:
                return {
                    "provider": "travelco",
                    "provider_booking_id": "booking-123",
                    "provider_quote_id": "quote-123",
                    "travel_kind": "flight",
                    "currency": "USD",
                    "total_minor": 12500,
                    "status": "confirmed",
                    "confirmed_at": now.isoformat(),
                }
            return None

    with pytest.raises(TravelBookingAdapterConformanceError):
        run(PrematureReceiptAdapter(now), now)


def test_tx22_rejects_invalid_handoff_url():
    now = utcnow()

    class BadHandoffAdapter(SandboxTravelAdapter):
        async def create_booking_handoff(
            self,
            *,
            preview: dict,
            traveler_data: dict,
            idempotency_key: str,
        ) -> dict:
            self.create_calls.append((preview, traveler_data, idempotency_key))
            return {
                "handoff_id": "booking-session-123",
                "handoff_url": "https://evil.example/continue/123",
            }

    with pytest.raises(TravelBookingAdapterConformanceError):
        run(BadHandoffAdapter(now), now)
