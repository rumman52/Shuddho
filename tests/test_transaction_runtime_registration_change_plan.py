from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

import scripts.transaction_runtime_registration_change_plan as tx26
from services.coworker.action_registry import stable_digest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def shopping_review(now: datetime) -> dict:
    value = {
        "schema_version": 1,
        "status": "eligible_for_runtime_registration_review",
        "provider": "merchantx",
        "operation": "merchantx:shopping_checkout_create",
        "adapter_revision": "a" * 40,
        "checkout_origin": "https://checkout.merchantx.example",
        "qualification_sha256": "b" * 64,
        "registration_proposal_sha256": "c" * 64,
        "conformance_sha256": "d" * 64,
        "live_probe_evidence_sha256": "e" * 64,
        "receipt_sha256": "f" * 64,
        "change_reference": "TX24-reviewed-change",
        "reviewer_reference": "security-reviewer",
        "reviewed_at": (now - timedelta(minutes=2)).isoformat(),
        "compiled_at": (now - timedelta(minutes=1)).isoformat(),
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    value["runtime_registration_review_sha256"] = stable_digest(value)
    return value


def travel_review(now: datetime) -> dict:
    value = {
        "schema_version": 1,
        "status": "eligible_for_runtime_registration_review",
        "provider": "travelco",
        "operation": "travelco:travel_booking_create",
        "adapter_revision": "1" * 40,
        "booking_origin": "https://booking.travelco.example",
        "travel_kind": "flight",
        "qualification_sha256": "2" * 64,
        "registration_proposal_sha256": "3" * 64,
        "conformance_sha256": "4" * 64,
        "receipt_sha256": "5" * 64,
        "traveler_fields_sent": ["email", "legal_name"],
        "change_reference": "TX25-reviewed-change",
        "reviewer_reference": "security-reviewer",
        "reviewed_at": (now - timedelta(minutes=2)).isoformat(),
        "compiled_at": (now - timedelta(minutes=1)).isoformat(),
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    value["runtime_registration_review_sha256"] = stable_digest(value)
    return value


def test_tx26_compiles_shopping_registration_code_change_plan():
    now = utcnow()
    result = tx26.compile_runtime_registration_change_plan(
        shopping_review(now),
        now=now,
    )

    assert result["status"] == "eligible_for_runtime_registration_code_change_review"
    assert result["action_kind"] == "shopping_checkout_create"
    assert result["transaction_class"] == "shopping_checkout"
    assert result["reviewed_origin"] == "https://checkout.merchantx.example"
    assert result["required_configuration_change"][
        "transaction_operation_to_add_after_code_review"
    ] == "merchantx:shopping_checkout_create"
    assert result["required_configuration_change"]["default_operation_enabled"] is False
    assert result["automatic_apply"] is False
    assert result["registry_mutated"] is False
    assert result["runtime_enabled"] is False
    assert result["identity_authority"] is False
    assert result["payment_authority"] is False
    assert len(result["runtime_registration_change_plan_sha256"]) == 64


def test_tx26_compiles_travel_registration_code_change_plan():
    now = utcnow()
    result = tx26.compile_runtime_registration_change_plan(
        travel_review(now),
        now=now,
    )

    assert result["action_kind"] == "travel_booking_create"
    assert result["transaction_class"] == "travel_booking"
    assert result["privacy_boundary"]["traveler_fields_sent"] == [
        "email",
        "legal_name",
    ]
    assert result["privacy_boundary"]["identity_documents_to_shuddho"] is False
    assert result["required_configuration_change"][
        "transaction_operation_to_add_after_code_review"
    ] == "travelco:travel_booking_create"
    assert result["operation_allowlisted"] is False
    assert result["external_action_registered"] is False


def test_tx26_rejects_tampered_review_digest():
    now = utcnow()
    value = shopping_review(now)
    value["receipt_sha256"] = "0" * 64

    with pytest.raises(tx26.TransactionRuntimeRegistrationPlanError):
        tx26.compile_runtime_registration_change_plan(value, now=now)


def test_tx26_rejects_stale_review():
    now = utcnow()
    value = shopping_review(now)
    value["compiled_at"] = (now - timedelta(hours=25)).isoformat()
    unsigned = dict(value)
    unsigned.pop("runtime_registration_review_sha256")
    value["runtime_registration_review_sha256"] = stable_digest(unsigned)

    with pytest.raises(tx26.TransactionRuntimeRegistrationPlanError):
        tx26.compile_runtime_registration_change_plan(value, now=now)


def test_tx26_rejects_review_claiming_runtime_authority():
    now = utcnow()
    value = travel_review(now)
    value["runtime_enabled"] = True
    unsigned = dict(value)
    unsigned.pop("runtime_registration_review_sha256")
    value["runtime_registration_review_sha256"] = stable_digest(unsigned)

    with pytest.raises(tx26.TransactionRuntimeRegistrationPlanError):
        tx26.compile_runtime_registration_change_plan(value, now=now)


def test_tx26_rejects_already_registered_action(monkeypatch):
    now = utcnow()
    value = shopping_review(now)
    monkeypatch.setitem(tx26.ACTION_SPECS, "shopping_checkout_create", object())

    with pytest.raises(tx26.TransactionRuntimeRegistrationPlanError):
        tx26.compile_runtime_registration_change_plan(value, now=now)


def test_tx26_rejects_already_registered_operation(monkeypatch):
    now = utcnow()
    value = travel_review(now)
    monkeypatch.setattr(
        tx26,
        "registered_transaction_operations",
        lambda: frozenset({"travelco:travel_booking_create"}),
    )

    with pytest.raises(tx26.TransactionRuntimeRegistrationPlanError):
        tx26.compile_runtime_registration_change_plan(value, now=now)
