from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from action_samples import connected, enable_actions
from test_coworker import account, container, new_task
from services.coworker.action_schemas import ActionPrepare
from services.coworker.agent_schemas import AgentActionProposal
from services.coworker.errors import CoworkerError
from services.coworker.microsoft_actions import email_body


def enable_attachments(container):
    provider = enable_actions(container)
    settings = replace(
        container.settings,
        action_attachments_enabled=True,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    return provider


def owned_artifact(
    container,
    owner,
    *,
    filename="approved.txt",
    content_type="text/plain",
    body=b"approved attachment bytes",
):
    task = new_task(container, owner)
    key = f"{owner}/outputs/{task['id']}/{filename}"
    container.storage.put(key, body, content_type)
    container.repository.complete(task["id"], [{
        "filename": filename,
        "content_type": content_type,
        "object_key": key,
        "byte_size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }])
    artifact = container.repository.get_task(owner, task["id"])["artifacts"][0]
    return artifact, key, body


def attachment_request(connection, artifact_id):
    return ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "attachment_ids": [artifact_id],
        "payload": {
            "kind": "email_send_with_attachments",
            "to": ["recipient@example.org"],
            "cc": [],
            "bcc": [],
            "subject": "Approved attachment",
            "body": "Please review the attached Shuddho artifact.",
        },
    })


def test_attachment_action_is_default_off(container):
    enable_actions(container)
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "email")
    with pytest.raises(CoworkerError) as error:
        container.actions.repo.prepare(
            owner,
            attachment_request(connection, artifact["id"]),
            "attachment-default-off",
        )
    assert error.value.code == "action_attachments_disabled"
    assert error.value.status_code == 503


def test_prepare_binds_exact_owned_artifact_manifest(container):
    enable_attachments(container)
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "email")
    action = container.actions.repo.prepare(
        owner,
        attachment_request(connection, artifact["id"]),
        "attachment-manifest",
    )
    assert action["kind"] == "email_send_with_attachments"
    assert action["preview"]["version"] == 3
    assert action["preview"]["attachments"] == [{
        "id": artifact["id"],
        "filename": artifact["filename"],
        "content_type": "text/plain",
        "byte_size": artifact["byte_size"],
        "sha256": artifact["sha256"],
    }]
    scope = action["preview"]["approval_scope"]
    assert scope["attachments"] == action["preview"]["attachments"]
    assert scope["policy"]["attachments"] == "owned_artifacts"
    assert len(scope["attachments_sha256"]) == 64


def test_cross_owner_artifact_cannot_enter_action_preview(container):
    enable_attachments(container)
    alice = account(container, "alice")
    bob = account(container, "bob")
    artifact, _key, _body = owned_artifact(container, bob)
    connection = connected(container.actions.repo, alice, "email")
    with pytest.raises(CoworkerError) as error:
        container.actions.repo.prepare(
            alice,
            attachment_request(connection, artifact["id"]),
            "cross-owner-attachment",
        )
    assert error.value.status_code == 404


def test_gmail_attachment_bytes_are_reverified_and_sent_once(container):
    provider = enable_attachments(container)
    owner = account(container)
    artifact, _key, expected_body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "email")
    action = container.actions.repo.prepare(
        owner,
        attachment_request(connection, artifact["id"]),
        "gmail-attachment",
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    asyncio.run(container.actions.execute(approved["id"]))
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "succeeded"
    assert len(provider.sent) == 1

    message = BytesParser(policy=policy.default).parsebytes(provider.sent[0])
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == artifact["filename"]
    assert attachments[0].get_content_type() == "text/plain"
    assert attachments[0].get_payload(decode=True) == expected_body


def test_changed_storage_bytes_fail_before_provider_mutation(container):
    provider = enable_attachments(container)
    owner = account(container)
    artifact, key, expected_body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "email")
    action = container.actions.repo.prepare(
        owner,
        attachment_request(connection, artifact["id"]),
        "tampered-attachment",
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    changed = b"x" * len(expected_body)
    assert hashlib.sha256(changed).hexdigest() != artifact["sha256"]
    container.storage.put(key, changed, "text/plain")

    asyncio.run(container.actions.execute(approved["id"]))
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "failed"
    assert result["error_code"] == "attachment_unavailable"
    assert provider.sent == []


def test_graph_attachment_encoding_is_bounded_to_verified_bytes():
    action = {
        "preview": {
            "payload": {
                "kind": "email_send_with_attachments",
                "to": ["recipient@example.org"],
                "cc": [],
                "bcc": [],
                "subject": "Attachment",
                "body": "Body",
            },
        },
    }
    body = email_body(action, [{
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "body": b"%PDF-synthetic",
    }])
    attached = body["message"]["attachments"]
    assert len(attached) == 1
    assert attached[0]["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert attached[0]["name"] == "report.pdf"
    assert base64.b64decode(attached[0]["contentBytes"]) == b"%PDF-synthetic"


def test_agent_proposals_cannot_select_attachment_action_kind():
    with pytest.raises(Exception):
        AgentActionProposal.model_validate({
            "payload": {
                "kind": "email_send_with_attachments",
                "to": ["recipient@example.org"],
                "cc": [],
                "bcc": [],
                "subject": "Not allowed",
                "body": "The model must not choose attachments.",
            },
            "rationale": "Attempted attachment action",
        })


def test_attachment_schema_rejects_duplicates_and_plain_email_ids():
    value = str(uuid4())
    with pytest.raises(Exception):
        ActionPrepare.model_validate({
            "connection_id": str(uuid4()),
            "attachment_ids": [value, value],
            "payload": {
                "kind": "email_send_with_attachments",
                "to": ["recipient@example.org"],
                "subject": "Duplicate",
                "body": "Body",
            },
        })
    with pytest.raises(Exception):
        ActionPrepare.model_validate({
            "connection_id": str(uuid4()),
            "attachment_ids": [value],
            "payload": {
                "kind": "email_send",
                "to": ["recipient@example.org"],
                "subject": "Plain email",
                "body": "Body",
            },
        })
