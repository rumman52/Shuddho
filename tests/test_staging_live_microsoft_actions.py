from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip(
    "sqlalchemy",
    reason="Install the coworker extra for Microsoft staging tests",
)

from scripts import staging_live_microsoft_actions as live


def test_wrong_hash_changes_exactly_one_hex_character():
    value = "a" * 64
    wrong = live.wrong_hash(value)
    assert len(wrong) == 64
    assert wrong != value
    assert wrong[1:] == value[1:]


def test_connection_for_requires_exactly_one_active_microsoft_capability():
    connections = [
        {
            "id": "1",
            "provider": "microsoft",
            "capability": "email",
            "active": True,
            "email": "a@example.com",
        },
        {
            "id": "2",
            "provider": "microsoft",
            "capability": "calendar",
            "active": True,
            "email": "a@example.com",
        },
        {
            "id": "3",
            "provider": "google",
            "capability": "email",
            "active": True,
            "email": "a@example.com",
        },
    ]
    assert live.connection_for(connections, "email")["id"] == "1"
    with pytest.raises(
        live.MicrosoftActionValidationFailure,
        match="exactly one active",
    ):
        live.connection_for(
            connections
            + [
                {
                    "id": "4",
                    "provider": "microsoft",
                    "capability": "email",
                    "active": True,
                    "email": "b@example.com",
                }
            ],
            "email",
        )


def test_validate_email_receipt_accepts_graph_acceptance_without_fake_id():
    action = {
        "receipt": {
            "provider": "microsoft",
            "status": "accepted_by_microsoft_graph",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
    }
    live.validate_email_receipt(action)


def test_validate_calendar_receipt_requires_transaction_binding():
    action = {
        "receipt": {
            "provider": "microsoft",
            "provider_id": "graph-event-1",
            "status": "event_created",
            "calendar": "primary",
            "transaction_id": "shuddho-abc123",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
    }
    live.validate_calendar_receipt(action)
    action["receipt"]["transaction_id"] = "other"
    with pytest.raises(
        live.MicrosoftActionValidationFailure,
        match="transaction binding",
    ):
        live.validate_calendar_receipt(action)


def test_validate_audit_requires_single_execution_path():
    action = {
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.approved"},
            {"action": "action.execution_started"},
            {"action": "action.succeeded"},
        ]
    }
    live.validate_audit(action)
    action["audit"].append(
        {"action": "action.execution_started"}
    )
    with pytest.raises(
        live.MicrosoftActionValidationFailure,
        match="exactly one",
    ):
        live.validate_audit(action)


def test_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS",
        raising=False,
    )
    with pytest.raises(
        live.MicrosoftActionValidationFailure,
        match="SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS",
    ):
        live.require_guard()
    monkeypatch.setenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS",
        "true",
    )
    live.require_guard()
