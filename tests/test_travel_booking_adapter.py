from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.coworker.action_registry import (
    action_spec,
    registered_transaction_operations,
)
from services.coworker.travel_booking_adapter import (
    TravelBookingAdapterAdmissionError,
    admit_travel_booking_adapter,
    canonical_sha256,
)


def utcnow():
    return datetime.now(timezone.utc)


def proposal():
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
        "change_reference": "TX21-reviewed-change",
        "reviewed_at": utcnow().isoformat(),
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


class QualifiedTravelAdapter:
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

    def __init__(self):
        self.create_calls = []
        self.lookup_calls = []

    async def create_booking(
        self,
        *,
        preview: dict,
        traveler_data: dict,
        idempotency_key: str,
    ) -> dict:
        self.create_calls.append((preview, traveler_data, idempotency_key))
        raise AssertionError("TX-21 admission must not call provider mutation")

    async def lookup_booking(
        self,
        *,
        idempotency_key: str | None = None,
        provider_booking_id: str | None = None,
    ) -> dict | None:
        self.lookup_calls.append((idempotency_key, provider_booking_id))
        raise AssertionError("TX-21 admission must not call provider lookup")


def test_tx21_admits_exact_adapter_for_implementation_tests_only():
    adapter = QualifiedTravelAdapter()
    result = admit_travel_booking_adapter(
        proposal(),
        adapter,
        now=utcnow(),
    )

    assert result["status"] == "admitted_for_provider_implementation_tests"
    assert result["provider"] == "travelco"
    assert result["operation"] == "travelco:travel_booking_create"
    assert result["travel_kind"] == "flight"
    assert result["provider_called"] is False
    assert result["registration_authority"] is False
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["adapter_admission_sha256"]) == 64
    assert adapter.create_calls == []
    assert adapter.lookup_calls == []

    with pytest.raises(Exception):
        action_spec("travel_booking_create")
    assert all(
        "travel_booking_create" not in item
        for item in registered_transaction_operations()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_name", "other"),
        ("adapter_revision", "c" * 40),
        ("booking_origin", "https://other.example"),
        ("travel_kind", "lodging"),
        ("action_kind", "other_action"),
        ("contract_version", 2),
        ("traveler_data_boundary_sha256", "d" * 64),
        ("supports_idempotency", False),
        ("supports_lookup_by_idempotency_key", False),
        ("supports_lookup_by_provider_booking_id", False),
        ("supports_provider_hosted_collection", False),
        ("payment_mode", "shuddho_direct"),
        ("receives_payment_instrument", True),
        ("receives_document_images", True),
        ("retains_traveler_data_in_logs", True),
    ],
)
def test_tx21_rejects_adapter_metadata_drift(field, value):
    adapter = QualifiedTravelAdapter()
    setattr(adapter, field, value)
    with pytest.raises(TravelBookingAdapterAdmissionError):
        admit_travel_booking_adapter(proposal(), adapter, now=utcnow())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("credential_scopes", frozenset({"booking.admin"})),
        ("required_traveler_fields", frozenset({"legal_name", "email"})),
        ("shuddho_transmitted_fields", frozenset({"legal_name"})),
        ("provider_hosted_fields", frozenset({"email", "date_of_birth"})),
    ],
)
def test_tx21_rejects_adapter_set_drift(field, value):
    adapter = QualifiedTravelAdapter()
    setattr(adapter, field, value)
    with pytest.raises(TravelBookingAdapterAdmissionError):
        admit_travel_booking_adapter(proposal(), adapter, now=utcnow())


def test_tx21_rejects_tampered_registration_proposal():
    value = proposal()
    value["traveler_data_boundary"]["shuddho_transmitted_fields"] = ["legal_name"]

    with pytest.raises(TravelBookingAdapterAdmissionError):
        admit_travel_booking_adapter(
            value,
            QualifiedTravelAdapter(),
            now=utcnow(),
        )


def test_tx21_rejects_registration_proposal_claiming_runtime_authority():
    value = proposal()
    value["runtime_enabled"] = True
    value["registration_proposal_sha256"] = canonical_sha256(
        {k: v for k, v in value.items() if k != "registration_proposal_sha256"}
    )

    with pytest.raises(TravelBookingAdapterAdmissionError):
        admit_travel_booking_adapter(
            value,
            QualifiedTravelAdapter(),
            now=utcnow(),
        )


def test_tx21_rejects_sync_adapter_methods():
    class SyncAdapter(QualifiedTravelAdapter):
        def create_booking(
            self,
            *,
            preview: dict,
            traveler_data: dict,
            idempotency_key: str,
        ) -> dict:
            return {}

    with pytest.raises(TravelBookingAdapterAdmissionError):
        admit_travel_booking_adapter(
            proposal(),
            SyncAdapter(),
            now=utcnow(),
        )
