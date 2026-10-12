"""Private owner-scoped messages; existing work ledgers remain authoritative."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select

from .conversation_schemas import ConversationCreate, MessageCreate
from .errors import CoworkerError
from .models import Account, AgentRun, Artifact, AuditEvent, Conversation, ConversationMessage, Document, DocumentVersion, utcnow
from .agent_repository import ACTIVE_RUN_STATES
from .repository import iso, not_found


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class ConversationRepository:
    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings

    def enabled(self):
        if not self.settings.conversations_enabled:
            raise CoworkerError("conversations_unavailable", "Conversations are not enabled in this workspace yet.", 409)

    @staticmethod
    def _conversation(db, owner, conversation_id, *, lock=False):
        query = select(Conversation).where(Conversation.owner_id == owner, Conversation.id == conversation_id, Conversation.deleted.is_(False))
        row = db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise not_found()
        return row

    @staticmethod
    def _lock_account(db, owner):
        # Match account erasure and FK insert lock ordering before child locks.
        if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
            raise not_found()

    @staticmethod
    def _dto(row):
        return {"id": row.id, "title": row.title, "message_sequence": row.message_sequence, "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}

    @staticmethod
    def message_dto(row):
        return {"id": row.id, "conversation_id": row.conversation_id, "sequence": row.sequence, "text": row.text, "selected_sources": row.selected_sources, "resource_links": row.resource_links, "created_at": iso(row.created_at)}

    @staticmethod
    def _audit(db, owner, resource_id, action):
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource_id, action=action))

    def create(self, owner: str, request: ConversationCreate, key: str) -> tuple[dict, bool]:
        self.enabled()
        digest = fingerprint(request.model_dump(mode="json"))
        with self.sessions.begin() as db:
            self._lock_account(db, owner)
            row = db.scalar(select(Conversation).where(Conversation.owner_id == owner, Conversation.idempotency_key == key))
            if row is not None:
                if row.deleted:
                    raise CoworkerError("conversation_deleted", "This conversation was deleted. Use a new request key.", 409)
                if row.fingerprint != digest:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to a different conversation.", 409)
                return self._dto(row), False
            count = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.owner_id == owner))
            if count >= self.settings.max_conversations:
                raise CoworkerError("conversation_limit", "This workspace reached its conversation limit.", 429)
            row = Conversation(id=str(uuid4()), owner_id=owner, idempotency_key=key, fingerprint=digest, title=request.title, message_sequence=0, deleted=False, created_at=utcnow(), updated_at=utcnow())
            db.add(row); db.flush()
            self._audit(db, owner, row.id, "conversation.created")
            return self._dto(row), True

    def list(self, owner: str) -> list[dict]:
        self.enabled()
        with self.sessions() as db:
            return [self._dto(row) for row in db.scalars(select(Conversation).where(Conversation.owner_id == owner, Conversation.deleted.is_(False)).order_by(Conversation.updated_at.desc(), Conversation.id).limit(self.settings.max_conversations))]

    def get(self, owner: str, conversation_id: str) -> dict:
        self.enabled()
        with self.sessions() as db:
            return self._dto(self._conversation(db, owner, conversation_id))

    @staticmethod
    def selected_sources(db, owner, resource_ids) -> list[dict]:
        sources = []
        for resource_id in resource_ids:
            identity = str(resource_id)
            version = db.scalar(select(DocumentVersion).join(Document, Document.id == DocumentVersion.document_id).where(DocumentVersion.id == identity, DocumentVersion.owner_id == owner, Document.owner_id == owner, Document.deleted.is_(False), DocumentVersion.state == "uploaded", DocumentVersion.expires_at > utcnow()))
            if version is not None:
                sources.append({"resource_type": "document_version", "resource_id": identity, "document_id": version.document_id, "version": version.version, "sha256": version.sha256, "trust": "untrusted_source"})
                continue
            artifact = db.scalar(select(Artifact).where(Artifact.id == identity, Artifact.owner_id == owner, (Artifact.expires_at.is_(None) | (Artifact.expires_at > utcnow()))))
            if artifact is None:
                raise not_found()
            sources.append({"resource_type": "artifact", "resource_id": identity, "sha256": artifact.sha256, "trust": "untrusted_source"})
        return sources

    def append_message(self, owner: str, conversation_id: str, request: MessageCreate) -> tuple[dict, bool]:
        self.enabled()
        digest = fingerprint(request.model_dump(mode="json", exclude={"client_request_key"}))
        with self.sessions.begin() as db:
            self._lock_account(db, owner)
            conversation = self._conversation(db, owner, conversation_id, lock=True)
            previous = db.scalar(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id, ConversationMessage.client_request_key == request.client_request_key))
            if previous is not None:
                if previous.fingerprint != digest:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to a different message or source selection.", 409)
                return self.message_dto(previous), False
            if conversation.message_sequence >= self.settings.max_conversation_messages:
                raise CoworkerError("conversation_message_limit", "This conversation reached its message limit.", 429)
            sources = self.selected_sources(db, owner, request.selected_resource_ids)
            conversation.message_sequence += 1
            conversation.updated_at = utcnow()
            row = ConversationMessage(id=str(uuid4()), owner_id=owner, conversation_id=conversation.id, client_request_key=request.client_request_key, fingerprint=digest, sequence=conversation.message_sequence, text=request.text, selected_sources=sources, resource_links=[], created_at=utcnow())
            db.add(row); db.flush()
            self._audit(db, owner, row.id, "conversation.message_added")
            return self.message_dto(row), True

    def messages(self, owner: str, conversation_id: str, *, after: int = 0, limit: int = 50) -> dict:
        self.enabled()
        if after < 0 or not 1 <= limit <= 100:
            raise CoworkerError("invalid_cursor", "Use a nonnegative sequence and a limit between 1 and 100.", 422)
        with self.sessions() as db:
            self._conversation(db, owner, conversation_id)
            rows = list(db.scalars(select(ConversationMessage).where(ConversationMessage.owner_id == owner, ConversationMessage.conversation_id == conversation_id, ConversationMessage.sequence > after).order_by(ConversationMessage.sequence).limit(limit)))
            return {"items": [self.message_dto(row) for row in rows], "next_cursor": rows[-1].sequence if rows else after}

    def delete(self, owner: str, conversation_id: str) -> dict:
        self.enabled()
        with self.sessions.begin() as db:
            self._lock_account(db, owner)
            row = self._conversation(db, owner, conversation_id, lock=True)
            messages = list(db.scalars(select(ConversationMessage).where(
                ConversationMessage.conversation_id == row.id, ConversationMessage.owner_id == owner,
            )))
            linked_ids = [link.get("resource_id") for message in messages
                          for link in (message.resource_links or [])
                          if link.get("resource_type") == "agent_run"]
            if linked_ids and db.scalar(select(AgentRun.id).where(
                AgentRun.owner_id == owner, AgentRun.id.in_(linked_ids),
                AgentRun.state.in_(ACTIVE_RUN_STATES),
            ).limit(1)) is not None:
                raise CoworkerError(
                    "conversation_active_work", "Cancel active Agent work before deleting this conversation.", 409,
                )
            row.deleted, row.title, row.updated_at = True, "", utcnow()
            for message in messages:
                message.text, message.selected_sources, message.resource_links = "", [], []
            self._audit(db, owner, row.id, "conversation.deleted")
        return {"id": conversation_id, "deleted": True}
