from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import func, select

from .config import Settings
from .errors import CoworkerError
from .memory_schemas import MemoryFactCreate, MemoryFactUpdate
from .models import AuditEvent, MemoryFact, Workspace, utcnow
from .repository import aware, iso, not_found


class MemoryRepository:
    def __init__(self, sessions, settings: Settings):
        self.sessions, self.settings = sessions, settings

    def _workspace(self, db, owner: str) -> str:
        value = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
        if value is None:
            raise not_found()
        return value

    def _audit(self, db, owner: str, resource: str, action: str):
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    def _dto(self, row: MemoryFact) -> dict:
        return {
            "id": row.id,
            "namespace": row.namespace,
            "key": row.key,
            "value": row.value,
            "language": row.language,
            "provenance": {"type": row.provenance_type, "ref": row.provenance_ref},
            "version": row.version,
            "expires_at": iso(row.expires_at) if row.expires_at else None,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
        }

    def _enabled(self):
        if not self.settings.agent_memory_enabled:
            raise CoworkerError("agent_memory_unavailable", "Structured memory is not enabled in this workspace yet.", 409)

    def create(self, owner: str, request: MemoryFactCreate) -> dict:
        self._enabled()
        with self.sessions.begin() as db:
            workspace_id = self._workspace(db, owner)
            if db.scalar(select(func.count()).select_from(MemoryFact).where(MemoryFact.owner_id == owner)) >= self.settings.max_memory_facts:
                raise CoworkerError("memory_limit", "Your structured memory fact limit has been reached.", 429)
            old = db.scalar(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
                MemoryFact.workspace_id == workspace_id,
                MemoryFact.namespace == request.namespace,
                MemoryFact.key == request.key,
            ))
            if old is not None:
                raise CoworkerError("memory_conflict", "A memory fact with this namespace and key already exists.", 409)
            if request.expires_at is not None and aware(request.expires_at) <= utcnow():
                raise CoworkerError("memory_expiry", "Memory expiry must be in the future.", 422)
            row = MemoryFact(
                id=str(uuid4()), owner_id=owner, workspace_id=workspace_id,
                namespace=request.namespace, key=request.key, value=request.value,
                language=request.language, provenance_type="user", provenance_ref=None,
                version=1, expires_at=request.expires_at,
            )
            db.add(row)
            self._audit(db, owner, row.id, "memory.created")
            db.flush()
            return self._dto(row)

    def list(self, owner: str) -> list[dict]:
        with self.sessions() as db:
            now = utcnow()
            rows = db.scalars(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
                (MemoryFact.expires_at.is_(None) | (MemoryFact.expires_at > now)),
            ).order_by(MemoryFact.namespace, MemoryFact.key)).all()
            return [self._dto(row) for row in rows]

    def update(self, owner: str, fact_id: str, request: MemoryFactUpdate) -> dict:
        self._enabled()
        with self.sessions.begin() as db:
            row = db.scalar(select(MemoryFact).where(
                MemoryFact.id == fact_id, MemoryFact.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if request.expires_at is not None and aware(request.expires_at) <= utcnow():
                raise CoworkerError("memory_expiry", "Memory expiry must be in the future.", 422)
            row.value = request.value
            row.language = request.language
            row.expires_at = request.expires_at
            row.version += 1
            row.updated_at = utcnow()
            self._audit(db, owner, row.id, "memory.updated")
            return self._dto(row)

    def delete(self, owner: str, fact_id: str) -> dict:
        with self.sessions.begin() as db:
            row = db.scalar(select(MemoryFact).where(
                MemoryFact.id == fact_id, MemoryFact.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            db.delete(row)
            self._audit(db, owner, fact_id, "memory.deleted")
        return {"deleted": True, "id": fact_id}

    def context(self, owner: str) -> dict:
        if not self.settings.agent_memory_enabled:
            return {"facts": [], "provenance": []}
        with self.sessions() as db:
            now = utcnow()
            rows = db.scalars(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
                (MemoryFact.expires_at.is_(None) | (MemoryFact.expires_at > now)),
            ).order_by(MemoryFact.updated_at.desc()).limit(self.settings.max_memory_context_facts)).all()
            facts, provenance, used = [], [], 0
            for row in rows:
                entry = {"namespace": row.namespace, "key": row.key, "value": row.value, "language": row.language}
                encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True).encode("utf-8")
                if used + len(encoded) > self.settings.max_memory_context_bytes:
                    continue
                used += len(encoded)
                facts.append(entry)
                provenance.append({"id": row.id, "version": row.version})
            return {"facts": facts, "provenance": provenance}
