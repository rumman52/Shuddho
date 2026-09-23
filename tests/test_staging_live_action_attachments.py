from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("sqlalchemy", reason="Install coworker extra for attachment staging tests")

from scripts import staging_live_action_attachments as live
from services.coworker.action_repository import digest
from services.coworker.action_registry import build_approval_scope


ARTIFACT_ID = "11111111-1111-1111-1111-111111111111"
CONNECTION_ID = "22222222-2222-2222-2222-222222222222"


def artifact():
    return {
        "id": ARTIFACT_ID,
        "filename": "staging-report.pdf",
        "content_type": "application/pdf",
        "byte_size": 1024,
        "sha256": "a" * 64,
    }


def payload():
    return {
        "kind": "email_send_with_attachments",
        "to": ["sender@example.com"],
        "cc": [],
        "bcc": ["recipient@example.com"],
        "subject": "Synthetic attachment test",
        "body": "Synthetic staging content.",
    }


def prepared():
    preview = {
        "version": 3,
        "provider": "google",
        "connection_id": CONNECTION_ID,
        "account": "sender@example.com",
        "subject_id": "subject-1",
        "payload": payload(),
        "execution": "immediately_after_approval",
        "attachments": [artifact()],
        "calendar": None,
        "guest_notifications": None,
        "reminders": "none",
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


def test_explicit_artifact_must_be_safe_and_enabled():
    value = {"attachments_enabled": True, "artifacts": [artifact()]}
    assert live.artifact_for(value, ARTIFACT_ID) == artifact()

    disabled = {"attachments_enabled": False, "artifacts": [artifact()]}
    with pytest.raises(live.AttachmentValidationFailure, match="not enabled"):
        live.artifact_for(disabled, ARTIFACT_ID)

    unsafe = {"attachments_enabled": True, "artifacts": [artifact() | {"content_type": "image/png"}]}
    with pytest.raises(live.AttachmentValidationFailure, match="attachment-safe"):
        live.artifact_for(unsafe, ARTIFACT_ID)


def test_prepared_preview_binds_exact_manifest_and_scope():
    value = prepared()
    live.validate_prepared(value, "google", CONNECTION_ID, payload(), artifact())

    changed = prepared()
    changed["preview"]["attachments"][0]["sha256"] = "b" * 64
    with pytest.raises(live.AttachmentValidationFailure, match="hash|metadata"):
        live.validate_prepared(changed, "google", CONNECTION_ID, payload(), artifact())


def test_wrong_hash_changes_exactly_one_character():
    value = "a" * 64
    wrong = live.wrong_hash(value)
    assert wrong != value
    assert wrong[1:] == value[1:]


def test_completion_requires_single_audit_path_and_provider_receipt():
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
            "status": "accepted_by_gmail",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    live.validate_completion(completed, start, "google")
    completed["audit"].append({"action": "action.execution_started"})
    with pytest.raises(live.AttachmentValidationFailure, match="exactly one"):
        live.validate_completion(completed, start, "google")


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_ATTACHMENTS", raising=False)
    with pytest.raises(live.AttachmentValidationFailure):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_ATTACHMENTS", "true")
    live.require_guard()
