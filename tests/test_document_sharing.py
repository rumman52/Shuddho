from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from action_samples import connected, enable_actions
from test_coworker import account, container, new_task
from services.coworker.action_schemas import ActionPrepare
from services.coworker.agent_schemas import AgentActionProposal
from services.coworker.errors import CoworkerError


def enable_document_sharing(container):
    provider = enable_actions(container)
    settings = replace(
        container.settings,
        artifact_services_enabled=True,
        action_document_sharing_enabled=True,
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
    body=b"approved document bytes",
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


def share_request(connection, artifact_id, recipient="reader@example.org"):
    return ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "artifact_ids": [artifact_id],
        "payload": {
            "kind": "document_share",
            "recipients": [recipient],
        },
    })


def test_document_sharing_requires_actions_and_artifacts(container):
    with pytest.raises(ValueError, match="ACTIONS_ENABLED"):
        replace(
            container.settings,
            action_document_sharing_enabled=True,
            artifact_services_enabled=True,
        ).validate()
    enable_actions(container)
    with pytest.raises(ValueError, match="ARTIFACT_SERVICES_ENABLED"):
        replace(
            container.settings,
            action_document_sharing_enabled=True,
        ).validate()


def test_document_share_is_default_off(container):
    enable_actions(container)
    settings = replace(container.settings, artifact_services_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    with pytest.raises(CoworkerError) as error:
        container.actions.repo.prepare(
            owner,
            share_request(connection, artifact["id"]),
            "drive-disabled",
        )
    assert error.value.code == "action_document_sharing_disabled"


def test_schema_requires_exactly_one_recipient_and_owned_artifact():
    artifact_id = str(uuid4())
    connection_id = str(uuid4())
    for invalid in (
        {
            "connection_id": connection_id,
            "artifact_ids": [],
            "payload": {"kind": "document_share", "recipients": ["a@example.org"]},
        },
        {
            "connection_id": connection_id,
            "artifact_ids": [artifact_id],
            "payload": {"kind": "document_share", "recipients": []},
        },
        {
            "connection_id": connection_id,
            "artifact_ids": [artifact_id],
            "payload": {
                "kind": "document_share",
                "recipients": ["a@example.org", "b@example.org"],
            },
        },
        {
            "connection_id": connection_id,
            "artifact_ids": [artifact_id],
            "attachment_ids": [str(uuid4())],
            "payload": {"kind": "document_share", "recipients": ["a@example.org"]},
        },
    ):
        with pytest.raises(Exception):
            ActionPrepare.model_validate(invalid)


def test_prepare_binds_exact_document_and_reader_policy(container):
    enable_document_sharing(container)
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    action = container.actions.repo.prepare(
        owner,
        share_request(connection, artifact["id"]),
        "drive-preview",
    )
    assert action["kind"] == "document_share"
    assert action["preview"]["version"] == 4
    assert action["preview"]["shared_artifact"] == {
        "id": artifact["id"],
        "filename": artifact["filename"],
        "content_type": "text/plain",
        "byte_size": artifact["byte_size"],
        "sha256": artifact["sha256"],
    }
    assert action["preview"]["document_sharing"] == {
        "source": "owned_shuddho_artifact",
        "access": "reader",
        "notifications": "recipient",
    }
    scope = action["preview"]["approval_scope"]
    assert scope["contract_version"] == 3
    assert scope["destinations"] == {"recipients": ["reader@example.org"]}
    assert scope["policy"]["document_sharing"]["access"] == "reader"
    assert scope["shared_artifact"] == action["preview"]["shared_artifact"]
    assert len(scope["shared_artifact_sha256"]) == 64


def test_cross_owner_artifact_cannot_be_shared(container):
    enable_document_sharing(container)
    alice = account(container, "alice")
    bob = account(container, "bob")
    artifact, _key, _body = owned_artifact(container, bob)
    connection = connected(container.actions.repo, alice, "drive")
    with pytest.raises(CoworkerError) as error:
        container.actions.repo.prepare(
            alice,
            share_request(connection, artifact["id"]),
            "drive-cross-owner",
        )
    assert error.value.status_code == 404


def test_google_drive_share_uploads_once_and_grants_exact_reader(container):
    provider = enable_document_sharing(container)
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    action = container.actions.repo.prepare(
        owner,
        share_request(connection, artifact["id"]),
        "drive-share-success",
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    asyncio.run(container.actions.execute(approved["id"]))
    asyncio.run(container.actions.execute(approved["id"]))

    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "succeeded"
    assert len(provider.drive_files) == 1
    file_id = next(iter(provider.drive_files))
    assert provider.drive_files[file_id]["appProperties"]["shuddhoAction"] == action["id"]
    assert provider.drive_files[file_id]["appProperties"]["shuddhoSha256"] == artifact["sha256"]
    assert provider.drive_permissions[file_id] == [{
        "type": "user",
        "role": "reader",
        "emailAddress": "reader@example.org",
        "id": "permission-1",
        "deleted": False,
    }]
    assert result["receipt"]["provider_id"] == file_id
    assert result["receipt"]["recipient"] == "reader@example.org"
    assert result["receipt"]["access"] == "reader"
    assert result["receipt"]["artifact_sha256"] == artifact["sha256"]


def test_lost_permission_response_reconciles_without_second_mutation(container):
    provider = enable_document_sharing(container)
    provider.lose_drive_permission_reply = True
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    action = container.actions.repo.prepare(
        owner,
        share_request(connection, artifact["id"]),
        "drive-lost-permission-reply",
    )
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    asyncio.run(container.actions.execute(approved["id"]))

    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "succeeded"
    assert len(provider.drive_files) == 1
    file_id = next(iter(provider.drive_files))
    assert len(provider.drive_permissions[file_id]) == 1


def test_lost_upload_response_never_uploads_twice(container):
    provider = enable_document_sharing(container)
    provider.lose_drive_upload_reply = True
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    action = container.actions.repo.prepare(
        owner,
        share_request(connection, artifact["id"]),
        "drive-lost-upload-reply",
    )
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    asyncio.run(container.actions.execute(approved["id"]))
    first = container.actions.repo.get(owner, approved["id"])
    assert first["state"] == "outcome_unknown"
    assert len(provider.drive_files) == 1
    file_id = next(iter(provider.drive_files))
    assert provider.drive_permissions[file_id] == []

    provider.lose_drive_upload_reply = False
    asyncio.run(container.actions.execute(approved["id"]))
    second = container.actions.repo.get(owner, approved["id"])
    assert second["state"] == "outcome_unknown"
    assert len(provider.drive_files) == 1
    assert provider.drive_permissions[file_id] == []


def test_changed_document_bytes_fail_before_drive_mutation(container):
    provider = enable_document_sharing(container)
    owner = account(container)
    artifact, key, original = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    action = container.actions.repo.prepare(
        owner,
        share_request(connection, artifact["id"]),
        "drive-tampered-bytes",
    )
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    changed = b"x" * len(original)
    assert hashlib.sha256(changed).hexdigest() != artifact["sha256"]
    container.storage.put(key, changed, "text/plain")

    asyncio.run(container.actions.execute(approved["id"]))
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "failed"
    assert result["error_code"] == "document_share_changed"
    assert provider.drive_files == {}


def test_document_share_kill_switch_cancels_before_google_mutation(container):
    provider = enable_document_sharing(container)
    owner = account(container)
    artifact, _key, _body = owned_artifact(container, owner)
    connection = connected(container.actions.repo, owner, "drive")
    action = container.actions.repo.prepare(
        owner,
        share_request(connection, artifact["id"]),
        "drive-kill-switch",
    )
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    disabled = replace(container.settings, action_document_sharing_enabled=False)
    container.settings = disabled
    container.repository.settings = disabled
    container.actions.repo.settings = disabled

    asyncio.run(container.actions.execute(approved["id"]))
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "action_document_sharing_disabled"
    assert provider.drive_files == {}


def test_agent_cannot_propose_document_sharing():
    with pytest.raises(Exception):
        AgentActionProposal.model_validate({
            "payload": {
                "kind": "document_share",
                "recipients": ["reader@example.org"],
            },
            "rationale": "The model must not select external document access.",
        })
