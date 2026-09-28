from __future__ import annotations

import pytest

from scripts import staging_live_personal_transactions as live


def test_guard_is_explicit(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_PERSONAL_TRANSACTIONS", raising=False)
    with pytest.raises(live.PersonalTransactionsValidationFailure):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_PERSONAL_TRANSACTIONS", "true")
    live.require_guard()


def test_transaction_authority_requires_exact_provider_operation():
    live.validate_transaction_authority({
        "schema_version": 1,
        "personal_transactions_enabled": True,
        "operations": ["google:negotiation_commitment_email"],
    }, "google")

    with pytest.raises(live.PersonalTransactionsValidationFailure, match="does not allow"):
        live.validate_transaction_authority({
            "schema_version": 1,
            "personal_transactions_enabled": True,
            "operations": ["microsoft:negotiation_commitment_email"],
        }, "google")


def test_connection_requires_one_active_email_account_for_provider():
    value = live.connection_for([{
        "id": "connection",
        "provider": "google",
        "capability": "email",
        "active": True,
        "email": "alice@example.test",
    }], "google")
    assert value["id"] == "connection"
    with pytest.raises(live.PersonalTransactionsValidationFailure):
        live.connection_for([], "google")


def prepared_action():
    connection = {"id": "connection", "provider": "google"}
    payload = live.expected_payload("counterparty@example.org", "marker123")
    preview = {
        "version": 6,
        "provider": "google",
        "connection_id": "connection",
        "payload": payload,
        "transaction": {
            "class": "binding_negotiation_commitment",
            "approval": "exact_final_terms",
            "changed_terms": "fresh_preview_required",
            "uncertain_outcome": "do_not_retry",
            "provider_idempotency": "provider_specific_only",
        },
    }
    preview["approval_scope"] = {
        "contract": "shuddho.consequential-action",
        "contract_version": 6,
        "action_kind": "negotiation_commitment_email",
        "destinations": {"to": ["counterparty@example.org"], "cc": [], "bcc": []},
        "policy": {"transaction": preview["transaction"]},
    }
    prepared = {
        "id": "11111111-1111-1111-1111-111111111111",
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": live.digest(preview),
    }
    return connection, payload, prepared


def test_prepared_transaction_binds_exact_terms_and_policy():
    connection, payload, prepared = prepared_action()
    live.validate_prepared(prepared, connection, payload)

    changed = dict(prepared)
    changed_preview = dict(prepared["preview"])
    changed_preview["transaction"] = dict(prepared["preview"]["transaction"], uncertain_outcome="retry")
    changed["preview"] = changed_preview
    changed["preview_hash"] = live.digest(changed_preview)
    with pytest.raises(live.PersonalTransactionsValidationFailure):
        live.validate_prepared(changed, connection, payload)


def test_completed_transaction_requires_single_execution_and_provider_acceptance():
    _, _, prepared = prepared_action()
    completed = {
        **prepared,
        "state": "succeeded",
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.approved"},
            {"action": "action.execution_started"},
            {"action": "action.succeeded"},
        ],
        "receipt": {
            "provider": "google",
            "provider_id": "mail-1",
            "thread_id": "thread-1",
            "status": "accepted_by_gmail",
            "confirmed_at": "2026-09-28T11:00:00+00:00",
        },
    }
    live.validate_completion(completed, prepared)

    completed["receipt"] = dict(completed["receipt"], status="delivered")
    with pytest.raises(live.PersonalTransactionsValidationFailure):
        live.validate_completion(completed, prepared)


def test_wrong_hash_changes_exactly_one_nibble():
    value = "a" * 64
    changed = live.wrong_hash(value)
    assert changed != value
    assert changed[1:] == value[1:]
    with pytest.raises(live.PersonalTransactionsValidationFailure):
        live.wrong_hash("too-short")
