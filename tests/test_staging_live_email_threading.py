from __future__ import annotations

import pytest

from scripts import staging_live_email_threading as live


def test_guard_is_explicit(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_EMAIL_THREADING", raising=False)
    with pytest.raises(live.EmailThreadingValidationFailure):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_EMAIL_THREADING", "true")
    live.require_guard()


def test_connection_requires_one_active_google_email():
    value = live.connection_for([{
        "id": "connection",
        "provider": "google",
        "capability": "email",
        "active": True,
        "email": "owner@example.test",
    }])
    assert value["id"] == "connection"
    with pytest.raises(live.EmailThreadingValidationFailure):
        live.connection_for([])


def parent_action():
    action_id = "11111111-1111-1111-1111-111111111111"
    preview = {
        "payload": {
            "kind": "email_send",
            "to": ["reader@example.test"],
            "cc": [],
            "bcc": [],
            "subject": "Thread subject",
            "body": "Parent",
        },
    }
    return {
        "id": action_id,
        "state": "succeeded",
        "preview": preview,
        "preview_hash": live.digest(preview),
        "receipt": {
            "provider": "google",
            "provider_id": "gmail-parent",
            "thread_id": "thread-1",
            "status": "accepted_by_gmail",
            "message_id": f"<{action_id}@shuddho.invalid>",
            "confirmed_at": "2026-09-24T00:00:00+00:00",
        },
        "audit": [],
    }


def test_prepared_reply_binds_parent_thread_and_send_only_policy():
    parent = parent_action()
    preview = {
        "payload": {
            "kind": "email_thread_reply",
            "parent_action_id": parent["id"],
            "to": ["reader@example.test"],
            "cc": [],
            "bcc": [],
            "subject": "Thread subject",
            "body": "Reply",
        },
        "threading": {
            "source": "owned_confirmed_shuddho_email",
            "provider": "google",
            "recipients": "same_to_cc",
            "bcc": "forbidden",
            "subject": "unchanged",
            "mailbox_read": "none",
        },
        "reply_context": {
            "parent_action_id": parent["id"],
            "root_action_id": parent["id"],
            "thread_id": "thread-1",
            "parent_message_id": parent["receipt"]["message_id"],
            "parent_provider_id": "gmail-parent",
            "references": [parent["receipt"]["message_id"]],
        },
    }
    prepared = {
        "id": "22222222-2222-2222-2222-222222222222",
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": live.digest(preview),
    }
    live.validate_prepared_reply(prepared, parent, "Reply")
    changed = dict(prepared)
    changed_preview = dict(preview)
    changed_preview["threading"] = dict(preview["threading"], mailbox_read="allowed")
    changed["preview"] = changed_preview
    changed["preview_hash"] = live.digest(changed_preview)
    with pytest.raises(live.EmailThreadingValidationFailure):
        live.validate_prepared_reply(changed, parent, "Reply")


def test_completed_reply_must_stay_in_approved_thread():
    prepared = {
        "id": "22222222-2222-2222-2222-222222222222",
        "preview": {"payload": {"kind": "email_thread_reply"}},
        "preview_hash": "a" * 64,
    }
    completed = {
        **prepared,
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.approved"},
            {"action": "action.execution_started"},
            {"action": "action.succeeded"},
        ],
        "receipt": {
            "provider": "google",
            "provider_id": "gmail-reply",
            "thread_id": "thread-1",
            "status": "accepted_by_gmail",
            "message_id": "<22222222-2222-2222-2222-222222222222@shuddho.invalid>",
        },
    }
    live.validate_completion(completed, prepared, expected_thread_id="thread-1")
    completed["receipt"] = dict(completed["receipt"], thread_id="escaped-thread")
    with pytest.raises(live.EmailThreadingValidationFailure, match="escaped"):
        live.validate_completion(completed, prepared, expected_thread_id="thread-1")
