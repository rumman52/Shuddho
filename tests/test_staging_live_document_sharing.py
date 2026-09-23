from __future__ import annotations

import pytest

from scripts import staging_live_document_sharing as live


def test_guard_is_explicit(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_DOCUMENT_SHARING", raising=False)
    with pytest.raises(live.DocumentSharingValidationFailure):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_DOCUMENT_SHARING", "true")
    live.require_guard()


def test_connection_requires_one_active_google_drive():
    value = live.connection_for([{
        "id": "connection",
        "provider": "google",
        "capability": "drive",
        "active": True,
        "email": "owner@example.test",
    }])
    assert value["id"] == "connection"
    with pytest.raises(live.DocumentSharingValidationFailure):
        live.connection_for([])


def test_artifact_validation_is_bounded():
    row = {
        "id": "artifact",
        "filename": "report.txt",
        "content_type": "text/plain",
        "byte_size": 128,
        "sha256": "a" * 64,
    }
    assert live.artifact_for({
        "document_sharing_enabled": True,
        "artifacts": [row],
    }, "artifact") == row
    with pytest.raises(live.DocumentSharingValidationFailure):
        live.artifact_for({
            "document_sharing_enabled": True,
            "artifacts": [dict(row, byte_size=8 * 1024 * 1024 + 1)],
        }, "artifact")


def test_prepared_preview_requires_exact_reader_policy():
    artifact = {
        "id": "artifact",
        "filename": "report.txt",
        "content_type": "text/plain",
        "byte_size": 128,
        "sha256": "b" * 64,
    }
    preview = {
        "payload": {"kind": "document_share", "recipients": ["reader@example.test"]},
        "shared_artifact": artifact,
        "document_sharing": {
            "source": "owned_shuddho_artifact",
            "access": "reader",
            "notifications": "recipient",
        },
    }
    action = {
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": live.digest(preview),
    }
    live.validate_prepared(action, artifact, "reader@example.test")
    changed = dict(action)
    changed["preview"] = dict(preview, document_sharing={
        "source": "owned_shuddho_artifact",
        "access": "writer",
        "notifications": "recipient",
    })
    changed["preview_hash"] = live.digest(changed["preview"])
    with pytest.raises(live.DocumentSharingValidationFailure):
        live.validate_prepared(changed, artifact, "reader@example.test")
