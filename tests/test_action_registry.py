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
    assert set(ACTION_SPECS) == {"email_send", "email_send_with_attachments", "email_thread_reply", "calendar_create", "calendar_create_with_reminder", "document_share", "social_publish_linkedin"}
    assert action_spec("email_send", "google").capability == "email"
    assert action_spec("calendar_create", "google").reconcile_supported
    assert action_spec("calendar_create_with_reminder", "google").reminders == "single_explicit"
    assert not action_spec("email_send", "google").reconcile_supported
    assert action_spec("email_send_with_attachments", "google").attachments_allowed
    assert action_spec("document_share", "google").capability == "drive"
    assert action_spec("document_share", "google").owned_artifact_required
    assert action_spec("document_share", "google").reconcile_supported
    assert action_spec("email_thread_reply", "google").thread_reply
    assert action_spec("social_publish_linkedin", "linkedin").social_publish
    assert action_spec("social_publish_linkedin", "linkedin").capability == "social"
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
        action_spec("social_publish_unregistered", "google")
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

    changed = deepcopy(preview)
    changed["payload"]["reminder_minutes_before_start"] = 30
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)
    assert build_approval_scope(changed)["payload_sha256"] != before


def document_share_preview():
    return {
        "version": 4,
        "provider": "google",
        "connection_id": "connection-drive",
        "account": "alice@example.test",
        "subject_id": "google-subject-1",
        "payload": {
            "kind": "document_share",
            "recipients": ["reader@example.org"],
        },
        "execution": "immediately_after_approval",
        "attachments": [],
        "calendar": None,
        "guest_notifications": None,
        "reminders": "none",
        "document_sharing": {
            "source": "owned_shuddho_artifact",
            "access": "reader",
            "notifications": "recipient",
        },
        "shared_artifact": {
            "id": "22222222-2222-2222-2222-222222222222",
            "filename": "report.pdf",
            "content_type": "application/pdf",
            "byte_size": 2048,
            "sha256": "c" * 64,
        },
        "expires_at": "2026-09-24T14:00:00+00:00",
    }


def test_document_share_scope_binds_recipient_reader_policy_and_artifact():
    preview = bind(document_share_preview())
    scope = preview["approval_scope"]
    assert scope["contract_version"] == 3
    assert scope["destinations"] == {"recipients": ["reader@example.org"]}
    assert scope["policy"]["document_sharing"] == preview["document_sharing"]
    assert scope["shared_artifact"] == preview["shared_artifact"]
    assert len(scope["shared_artifact_sha256"]) == 64
    assert validate_approval_scope(preview).kind == "document_share"

    changed = deepcopy(preview)
    changed["payload"]["recipients"] = ["other@example.org"]
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)

    changed = deepcopy(preview)
    changed["shared_artifact"]["sha256"] = "d" * 64
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)


def test_document_share_is_google_only():
    with pytest.raises(CoworkerError, match="cannot perform"):
        action_spec("document_share", "microsoft")


def thread_reply_preview():
    parent_id = "11111111-1111-1111-1111-111111111111"
    value = email_preview()
    value["version"] = 2
    value["payload"] = {
        **value["payload"],
        "kind": "email_thread_reply",
        "parent_action_id": parent_id,
        "bcc": [],
    }
    value["threading"] = {
        "source": "owned_confirmed_shuddho_email",
        "provider": "google",
        "recipients": "same_to_cc",
        "bcc": "forbidden",
        "subject": "unchanged",
        "mailbox_read": "none",
    }
    value["reply_context"] = {
        "parent_action_id": parent_id,
        "root_action_id": parent_id,
        "thread_id": "gmail-thread-1",
        "parent_message_id": f"<{parent_id}@shuddho.invalid>",
        "parent_provider_id": "gmail-message-1",
        "references": [f"<{parent_id}@shuddho.invalid>"],
    }
    return value


def test_thread_reply_scope_binds_owned_parent_and_provider_thread():
    preview = bind(thread_reply_preview())
    scope = preview["approval_scope"]
    assert scope["contract_version"] == 4
    assert scope["policy"]["threading"]["mailbox_read"] == "none"
    assert scope["reply_context"] == preview["reply_context"]
    assert validate_approval_scope(preview).kind == "email_thread_reply"

    changed = deepcopy(preview)
    changed["reply_context"]["thread_id"] = "different-thread"
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)

    with pytest.raises(CoworkerError, match="cannot perform"):
        action_spec("email_thread_reply", "microsoft")



def social_publish_preview():
    return {
        "version": 5,
        "provider": "linkedin",
        "connection_id": "connection-linkedin",
        "account": "urn:li:person:member_123",
        "subject_id": "member_123",
        "payload": {
            "kind": "social_publish_linkedin",
            "text": "Reviewed launch update #Shuddho",
        },
        "execution": "immediately_after_approval",
        "attachments": [],
        "calendar": None,
        "guest_notifications": None,
        "reminders": "none",
        "social_publishing": {
            "provider": "linkedin",
            "author": "connected_personal_member",
            "visibility": "public",
            "media": "none",
            "scheduling": "none",
            "social_read": "none",
            "agent_authority": "none",
        },
        "expires_at": "2026-09-24T14:00:00+00:00",
    }


def test_social_publish_scope_binds_exact_author_text_and_narrow_policy():
    preview = bind(social_publish_preview())
    scope = preview["approval_scope"]
    assert scope["contract_version"] == 5
    assert scope["destinations"] == {}
    assert scope["account"] == "urn:li:person:member_123"
    assert scope["policy"]["social_publishing"] == preview["social_publishing"]
    assert scope["policy"]["social_publishing"]["social_read"] == "none"
    assert scope["policy"]["social_publishing"]["agent_authority"] == "none"
    assert validate_approval_scope(preview).kind == "social_publish_linkedin"

    changed = deepcopy(preview)
    changed["payload"]["text"] = "Changed after approval"
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)

    changed = deepcopy(preview)
    changed["account"] = "urn:li:person:other"
    with pytest.raises(CoworkerError, match="changed"):
        validate_approval_scope(changed)

    with pytest.raises(CoworkerError, match="cannot perform"):
        action_spec("social_publish_linkedin", "google")
