from copy import deepcopy

import pytest

from services.coworker.action_registry import (
    ACTION_SPECS,
    action_spec,
    build_approval_scope,
    registered_actions,
    validate_approval_scope,
)
from services.coworker.errors import CoworkerError


def email_preview():
    return {
        "version": 1,
        "provider": "google",
        "connection_id": "connection-1",
        "account": "alice@example.test",
        "subject_id": "google-subject-1",
        "payload": {
            "kind": "email_send",
            "to": ["recipient@example.org"],
            "cc": [],
            "bcc": ["private@example.org"],
            "subject": "Status",
            "body": "Approved content.",
        },
        "execution": "immediately_after_approval",
        "attachments": [],
        "calendar": None,
        "guest_notifications": None,
        "reminders": "none",
        "expires_at": "2026-09-22T14:00:00+00:00",
    }


def calendar_preview():
    return {
        "version": 1,
        "provider": "google",
        "connection_id": "connection-2",
        "account": "alice@example.test",
        "subject_id": "google-subject-1",
        "payload": {
            "kind": "calendar_create",
            "title": "Planning",
            "description": "",
            "location": "",
            "start_at": "2026-09-23T10:00:00+06:00",
            "end_at": "2026-09-23T11:00:00+06:00",
            "time_zone": "Asia/Dhaka",
            "attendees": ["guest@example.org"],
        },
        "execution": "immediately_after_approval",
        "attachments": [],
        "calendar": "primary",
        "guest_notifications": "all",
        "reminders": "none",
        "expires_at": "2026-09-22T14:00:00+00:00",
    }


def bind(preview):
    preview["approval_scope"] = build_approval_scope(preview)
    return preview


def test_registry_declares_existing_consequential_actions():
    assert set(ACTION_SPECS) == {"email_send", "calendar_create"}
    assert action_spec("email_send", "google").capability == "email"
    assert action_spec("calendar_create", "google").reconcile_supported
    assert not action_spec("email_send", "google").reconcile_supported
    assert {item["kind"] for item in registered_actions()} == set(ACTION_SPECS)


def test_approval_scope_binds_identity_payload_destinations_and_policy():
    preview = bind(email_preview())
    scope = preview["approval_scope"]
    assert scope["contract"] == "shuddho.consequential-action"
    assert scope["connection_id"] == "connection-1"
    assert scope["account"] == "alice@example.test"
    assert scope["destinations"] == {
        "to": ["recipient@example.org"],
        "cc": [],
        "bcc": ["private@example.org"],
    }
    assert scope["policy"]["attachments"] == "none"
    assert len(scope["payload_sha256"]) == 64
    assert validate_approval_scope(preview).kind == "email_send"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("payload", "body"), "Changed after approval"),
        (("payload", "to"), ["other@example.org"]),
        (("account",), "other@example.test"),
        (("connection_id",), "connection-99"),
        (("expires_at",), "2026-09-22T15:00:00+00:00"),
    ],
)
def test_approval_scope_rejects_any_bound_mutation(path, value):
    preview = bind(email_preview())
    changed = deepcopy(preview)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(CoworkerError, match="approval scope"):
        validate_approval_scope(changed)


def test_calendar_scope_binds_primary_calendar_and_guest_policy():
    preview = bind(calendar_preview())
    scope = preview["approval_scope"]
    assert scope["destinations"] == {
        "attendees": ["guest@example.org"],
        "calendar": "primary",
    }
    assert scope["policy"]["guest_notifications"] == "all"
    assert scope["policy"]["reminders"] == "none"


def test_unregistered_action_or_provider_fails_closed():
    with pytest.raises(CoworkerError, match="not registered"):
        action_spec("social_publish", "google")
    with pytest.raises(CoworkerError, match="cannot perform"):
        action_spec("email_send", "outlook")


def test_legacy_v1_preview_keeps_hash_bound_compatibility():
    preview = email_preview()
    assert "approval_scope" not in preview
    assert validate_approval_scope(preview).kind == "email_send"


def test_v2_preview_cannot_omit_approval_scope():
    preview = email_preview()
    preview["version"] = 2
    with pytest.raises(CoworkerError, match="approval scope is missing"):
        validate_approval_scope(preview)
