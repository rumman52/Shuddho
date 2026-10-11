"""Durable conversation ownership, idempotency, deletion and bounded admission."""
from dataclasses import replace
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")
from test_coworker import account, container, signed_client
from services.coworker.conversation_repository import ConversationRepository
from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import AuditEvent
from sqlalchemy import select


def conversations(container):
    settings = replace(container.settings, conversations_enabled=True)
    return ConversationRepository(container.repository.sessions, settings)


def test_conversation_default_off(container):
    with pytest.raises(CoworkerError) as error:
        container.conversations.create(account(container), ConversationCreate(title="Work"), "conversation-key")
    assert error.value.code == "conversations_unavailable"


def test_conversation_and_message_replay_are_owned_and_fingerprint_bound(container):
    repo = conversations(container)
    owner, other = account(container), account(container, "other")
    conversation, created = repo.create(owner, ConversationCreate(title="প্রকল্প"), "conversation-key")
    assert created
    replay, created = repo.create(owner, ConversationCreate(title="প্রকল্প"), "conversation-key")
    assert replay == conversation and not created
    with pytest.raises(CoworkerError) as conflict:
        repo.create(owner, ConversationCreate(title="Changed"), "conversation-key")
    assert conflict.value.code == "idempotency_conflict"
    request = MessageCreate(text="প্রতিবেদন তৈরি করুন", client_request_key="message-key")
    message, created = repo.append_message(owner, conversation["id"], request)
    assert created and message["sequence"] == 1
    assert message["resource_links"] == []
    replay, created = repo.append_message(owner, conversation["id"], request)
    assert replay == message and not created
    with pytest.raises(CoworkerError) as conflict:
        repo.append_message(owner, conversation["id"], MessageCreate(text="Changed", client_request_key="message-key"))
    assert conflict.value.code == "idempotency_conflict"
    with pytest.raises(CoworkerError) as hidden:
        repo.get(other, conversation["id"])
    assert hidden.value.code == "not_found"
    with pytest.raises(CoworkerError) as hidden:
        repo.append_message(other, conversation["id"], request)
    assert hidden.value.code == "not_found"
    assert repo.list(other) == []
    assert repo.messages(owner, conversation["id"], after=0, limit=10)["items"] == [message]
    with container.repository.sessions() as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.owner_id == owner)).all()
        assert all("প্রতিবেদন" not in (event.action + event.resource_id) for event in events)


def test_foreign_or_missing_selected_sources_cannot_be_admitted(container):
    repo, owner = conversations(container), account(container)
    conversation, _ = repo.create(owner, ConversationCreate(title="Work"), "conversation-key")
    with pytest.raises(CoworkerError) as hidden:
        repo.append_message(owner, conversation["id"], MessageCreate(text="Use source", client_request_key="message-key", selected_resource_ids=[uuid4()]))
    assert hidden.value.code == "not_found"
    assert repo.messages(owner, conversation["id"], after=0, limit=10)["items"] == []


def test_deleted_conversation_is_redacted_and_cannot_resurrect_on_replay(container):
    repo, owner = conversations(container), account(container)
    conversation, _ = repo.create(owner, ConversationCreate(title="Private"), "conversation-key")
    request = MessageCreate(text="private source text", client_request_key="message-key")
    repo.append_message(owner, conversation["id"], request)
    repo.delete(owner, conversation["id"])
    assert repo.list(owner) == []
    with pytest.raises(CoworkerError) as deleted:
        repo.create(owner, ConversationCreate(title="Private"), "conversation-key")
    assert deleted.value.code == "conversation_deleted"
    from services.coworker.models import Conversation, ConversationMessage
    with repo.sessions() as db:
        assert db.get(Conversation, conversation["id"]).title == ""
        assert db.scalar(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation["id"])).text == ""


def test_conversation_erased_with_account(container):
    repo, owner = conversations(container), account(container)
    conversation, _ = repo.create(owner, ConversationCreate(title="Work"), "conversation-key")
    repo.append_message(owner, conversation["id"], MessageCreate(text="Private", client_request_key="message-key"))
    assert container.retention.erase_account(owner)["database_erased"]
    from services.coworker.models import Conversation, ConversationMessage
    with repo.sessions() as db:
        assert db.get(Conversation, conversation["id"]) is None
        assert db.scalar(select(ConversationMessage)) is None


def test_public_conversation_routes_replay_and_deny_other_owner(container, signed_client):
    container.settings = replace(container.settings, conversations_enabled=True)
    container.conversations.settings = container.settings
    client, headers = signed_client
    auth = headers() | {"Idempotency-Key": "conversation-api-key"}
    created = client.post("/api/v1/conversations", json={"title": "Work"}, headers=auth)
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    replay = client.post("/api/v1/conversations", json={"title": "Work"}, headers=auth)
    assert replay.status_code == 200 and replay.json() == created.json()
    path = created.headers["location"]
    request = {"text": "Create a report", "client_request_key": "message-api-key"}
    message = client.post(path + "/messages", json=request, headers=auth)
    assert message.status_code == 201 and message.json()["resource_links"] == []
    replay = client.post(path + "/messages", json=request, headers=auth)
    assert replay.status_code == 200 and replay.json() == message.json()
    assert client.get(path, headers=headers("bob")).status_code == 404
    assert client.post(path + "/messages", json=request, headers=headers("bob")).status_code == 404
    assert client.get(path + "/messages?after=1", headers=auth).json()["items"] == []
    assert client.get(path + "/messages?after=-1", headers=auth).status_code == 422


def test_source_selection_binds_owned_uploaded_version_and_rejects_deleted_source(container):
    from services.coworker.schemas import UploadRequest
    from services.coworker.models import Document
    repo, owner, other = conversations(container), account(container), account(container, "other")
    upload = container.repository.create_upload(owner, UploadRequest(filename="source.txt", byte_size=5, sha256="a" * 64))
    container.repository.finish_upload(owner, upload["id"])
    conversation, _ = repo.create(owner, ConversationCreate(title="Work"), "conversation-key")
    request = MessageCreate(text="Use the selected source", client_request_key="message-source-key", selected_resource_ids=[upload["version_id"]])
    message, _ = repo.append_message(owner, conversation["id"], request)
    assert message["selected_sources"] == [{"resource_type": "document_version", "resource_id": upload["version_id"], "document_id": upload["id"], "version": 1, "sha256": "a" * 64, "trust": "untrusted_source"}]
    other_conversation, _ = repo.create(other, ConversationCreate(title="Other"), "conversation-key")
    with pytest.raises(CoworkerError) as hidden:
        repo.append_message(other, other_conversation["id"], request)
    assert hidden.value.code == "not_found"
    with pytest.raises(CoworkerError) as conflict:
        repo.append_message(owner, conversation["id"], MessageCreate(text=request.text, client_request_key=request.client_request_key))
    assert conflict.value.code == "idempotency_conflict"
    with repo.sessions.begin() as db:
        db.get(Document, upload["id"]).deleted = True
    with pytest.raises(CoworkerError) as hidden:
        repo.append_message(owner, conversation["id"], request.model_copy(update={"client_request_key": "message-after-delete"}))
    assert hidden.value.code == "not_found"


def test_conversation_message_budget_has_no_partial_acceptance(container):
    owner = account(container)
    repo = ConversationRepository(container.repository.sessions, replace(container.settings, conversations_enabled=True, max_conversation_messages=1))
    conversation, _ = repo.create(owner, ConversationCreate(title="Work"), "conversation-key")
    repo.append_message(owner, conversation["id"], MessageCreate(text="First", client_request_key="message-first"))
    with pytest.raises(CoworkerError) as limit:
        repo.append_message(owner, conversation["id"], MessageCreate(text="Second", client_request_key="message-second"))
    assert limit.value.code == "conversation_message_limit"
    assert repo.get(owner, conversation["id"])["message_sequence"] == 1
