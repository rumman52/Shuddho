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
    assert set(ACTION_SPECS) == {"email_send", "email_send_with_attachments", "calendar_create", "calendar_create_with_reminder"}
    assert action_spec("email_send", "google").capability == "email"
    assert action_spec("calendar_create", "google").reconcile_supported
    assert action_spec("calendar_create_with_reminder", "google").reminders == "single_explicit"
    assert not action_spec("email_send", "google").reconcile_supported
    assert action_spec("email_send_with_attachments", "google").attachments_allowed
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

def attachment_preview():
    value = email_preview()
    value["version"] = 3
    value["payload"]["kind"] = "email_send_with_attachments"
    value["attachments"] = [{
        "id": "11111111-1111-1111-1111-111111111111",
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "byte_size": 1024,
        "sha256": "a" * 64,
    }]
    return value


def test_attachment_scope_binds_exact_owned_artifact_manifest():
    preview = bind(attachment_preview())
    scope = preview["approval_scope"]
    assert scope["policy"]["attachments"] == "owned_artifacts"
    assert scope["attachments"] == preview["attachments"]
    assert len(scope["attachments_sha256"]) == 64
    assert validate_approval_scope(preview).kind == "email_send_with_attachments"

    changed = deepcopy(preview)
    changed["attachments"][0]["sha256"] = "b" * 64
    with pytest.raises(CoworkerError, match="approval scope"):
        validate_approval_scope(changed)


def test_plain_email_rejects_unexpected_attachment_manifest():
    preview = email_preview()
    preview["attachments"] = [{
        "id": "11111111-1111-1111-1111-111111111111",
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "byte_size": 1024,
        "sha256": "a" * 64,
    }]
    with pytest.raises(CoworkerError, match="does not allow attachments"):
        build_approval_scope(preview)

def test_plain_v2_scope_keeps_exact_contract_v1_shape():
    preview = email_preview()
    preview["version"] = 2
    scope = build_approval_scope(preview)
    assert scope["contract_version"] == 1
    assert "attachments_sha256" not in scope
    assert "attachments" not in scope
    preview["approval_scope"] = scope
    assert validate_approval_scope(preview).kind == "email_send"



def test_reminder_approval_scope_binds_exact_minutes_and_policy():
    preview = calendar_preview()
    preview["payload"]["kind"] = "calendar_create_with_reminder"
    preview["payload"]["reminder_minutes_before_start"] = 15
    preview["reminders"] = "single_explicit"
    preview["version"] = 2
    bind(preview)
    scope = preview["approval_scope"]
    assert scope["action_kind"] == "calendar_create_with_reminder"
    assert scope["policy"]["reminders"] == "single_explicit"
    before = scope["payload_sha256"]

    changed = json.loads(json.dumps(preview))
    changed["payload"]["reminder_minutes_before_start"] = 30
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)
    assert build_approval_scope(changed)["payload_sha256"] != before
