from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for live Google action staging tests")

from scripts import staging_live_google_actions as live


def test_wrong_hash_changes_exactly_one_hex_character():
    value = "a" * 64
    wrong = live.wrong_hash(value)
    assert len(wrong) == 64
    assert wrong != value
    assert wrong[1:] == value[1:]


def test_connection_for_requires_exactly_one_active_google_capability():
    connections = [
        {"id": "1", "provider": "google", "capability": "email", "active": True, "email": "a@example.com"},
        {"id": "2", "provider": "google", "capability": "calendar", "active": True, "email": "a@example.com"},
    ]
    assert live.connection_for(connections, "email")["id"] == "1"
    with pytest.raises(live.GoogleActionValidationFailure, match="exactly one active"):
        live.connection_for(connections + [connections[0] | {"id": "3"}], "email")


def test_validate_email_receipt_accepts_bound_provider_receipt():
    action = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "receipt": {
            "provider": "google",
            "provider_id": "gmail-message-1",
            "status": "accepted_by_gmail",
            "message_id": "<123e4567-e89b-12d3-a456-426614174000@shuddho.invalid>",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    live.validate_email_receipt(action)


def test_validate_calendar_receipt_requires_stable_event_id():
    action_id = "123e4567-e89b-12d3-a456-426614174000"
    action = {
        "id": action_id,
        "receipt": {
            "provider": "google",
            "provider_id": "shuddho" + action_id.replace("-", ""),
            "status": "event_created",
            "calendar": "primary",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    live.validate_calendar_receipt(action)
    action["receipt"]["provider_id"] = "unexpected"
    with pytest.raises(live.GoogleActionValidationFailure, match="stable Shuddho event id"):
        live.validate_calendar_receipt(action)


def test_validate_audit_requires_one_prepared_approval_execution_and_success():
    action = {
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.approved"},
            {"action": "action.execution_started"},
            {"action": "action.succeeded"},
        ]
    }
    live.validate_audit(action)
    action["audit"].append({"action": "action.execution_started"})
    with pytest.raises(live.GoogleActionValidationFailure, match="exactly one"):
        live.validate_audit(action)


def test_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS", raising=False)
    with pytest.raises(live.GoogleActionValidationFailure, match="SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS"):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS", "true")
    live.require_guard()
