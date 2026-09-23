from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("sqlalchemy")

from scripts import staging_live_action_reminders as live
from services.coworker.action_repository import digest
from services.coworker.action_registry import build_approval_scope


CONNECTION_ID = "22222222-2222-2222-2222-222222222222"


def payload():
    return {
        "kind": "calendar_create_with_reminder",
        "title": "Synthetic reminder",
        "description": "Synthetic staging content.",
        "location": "Controlled staging",
        "start_at": "2026-09-24T10:00:00+00:00",
        "end_at": "2026-09-24T10:30:00+00:00",
        "time_zone": "UTC",
        "attendees": ["recipient@example.com"],
        "reminder_minutes_before_start": 15,
    }


def prepared(provider="google"):
    preview = {
        "version": 2,
        "provider": provider,
        "connection_id": CONNECTION_ID,
        "account": "sender@example.com",
        "subject_id": "subject-1",
        "payload": payload(),
        "execution": "immediately_after_approval",
        "attachments": [],
        "calendar": "primary",
        "guest_notifications": "all",
        "reminders": "single_explicit",
        "expires_at": datetime.now(timezone.utc).isoformat(),
    }
    preview["approval_scope"] = build_approval_scope(preview)
    return {
        "id": "33333333-3333-3333-3333-333333333333",
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": digest(preview),
    }


def test_connection_must_be_exact_provider_calendar():
    value = [{"provider": "google", "capability": "calendar", "active": True, "id": CONNECTION_ID}]
    assert live.connection_for(value, "google")["id"] == CONNECTION_ID
    with pytest.raises(live.ReminderValidationFailure):
        live.connection_for(value, "microsoft")


def test_prepared_reminder_binds_exact_payload_and_policy():
    value = prepared()
    live.validate_prepared(value, "google", CONNECTION_ID, payload())

    changed = prepared()
    changed["preview"]["payload"]["reminder_minutes_before_start"] = 30
    with pytest.raises(live.ReminderValidationFailure):
        live.validate_prepared(changed, "google", CONNECTION_ID, payload())


def test_completion_requires_single_audit_path_and_event_receipt():
    start = prepared()
    completed = {
        **start,
        "state": "succeeded",
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.approved"},
            {"action": "action.execution_started"},
            {"action": "action.succeeded"},
        ],
        "receipt": {
            "provider": "google",
            "provider_id": "event-1",
            "status": "event_created",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    live.validate_completion(completed, start, "google")
    completed["receipt"]["status"] = "accepted_by_gmail"
    with pytest.raises(live.ReminderValidationFailure):
        live.validate_completion(completed, start, "google")


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_REMINDERS", raising=False)
    with pytest.raises(live.ReminderValidationFailure):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_REMINDERS", "true")
    live.require_guard()
