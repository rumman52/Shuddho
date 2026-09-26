from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from .config import Settings
from .errors import CoworkerError
from .agent_schemas import AgentMemoryProposal
from .memory_schemas import MemoryFactCreate, MemoryFactUpdate
from .models import Account, AgentRun, AuditEvent, Document, DocumentVersion, MemoryFact, MemoryProposal, Workspace, utcnow
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
            "active": row.expires_at is None or aware(row.expires_at) > utcnow(),
        }

    def _enabled(self):
        if not self.settings.agent_memory_enabled:
            raise CoworkerError("agent_memory_unavailable", "Structured memory is not enabled in this workspace yet.", 409)

    def create(self, owner: str, request: MemoryFactCreate) -> dict:
        self._enabled()
        with self.sessions.begin() as db:
            if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
                raise not_found()
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
            rows = db.scalars(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
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

    @staticmethod
    def _proposal_dto(row: MemoryProposal) -> dict:
        state = "expired" if row.state == "proposed" and aware(row.expires_at) <= utcnow() else row.state
        return {
            "id": row.id,
            "run_id": row.run_id,
            "namespace": row.namespace,
            "key": row.key,
            "value": row.value,
            "language": row.language,
            "source_refs": list(row.source_refs or []),
            "state": state,
            "accepted_fact_id": row.accepted_fact_id,
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
            "reviewed_at": iso(row.reviewed_at) if row.reviewed_at else None,
        }

    def propose_from_agent(
        self,
        owner: str,
        run_id: str,
        proposal: AgentMemoryProposal,
        source_map: dict[str, dict],
    ) -> dict:
        self._enabled()
        if not self.settings.context_retrieval_enabled:
            raise CoworkerError("context_retrieval_unavailable", "Context retrieval is not enabled.", 409)
        if not set(proposal.source_ids).issubset(source_map):
            raise CoworkerError("memory_proposal_source", "The memory proposal cites an unavailable context source.", 409)
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(
                AgentRun.id == run_id, AgentRun.owner_id == owner,
            ).with_for_update())
            if run is None:
                raise not_found()
            active = db.scalar(select(func.count()).select_from(MemoryProposal).where(
                MemoryProposal.owner_id == owner,
                MemoryProposal.state == "proposed",
                MemoryProposal.expires_at > utcnow(),
            ))
            if active >= self.settings.max_memory_proposals:
                raise CoworkerError("memory_proposal_limit", "Your pending memory proposal limit has been reached.", 429)
            refs = [
                {"source_id": source_id, **source_map[source_id]}
                for source_id in proposal.source_ids
            ]
            row = MemoryProposal(
                id=str(uuid4()),
                owner_id=owner,
                workspace_id=run.workspace_id,
                run_id=run.id,
                namespace=proposal.namespace,
                key=proposal.key,
                value=proposal.value,
                language=proposal.language,
                source_refs=refs,
                state="proposed",
                expires_at=utcnow() + timedelta(hours=24),
            )
            db.add(row)
            self._audit(db, owner, row.id, "memory.proposed")
            db.flush()
            return self._proposal_dto(row)

    def proposals(self, owner: str) -> list[dict]:
        with self.sessions() as db:
            rows = db.scalars(select(MemoryProposal).where(
                MemoryProposal.owner_id == owner,
            ).order_by(MemoryProposal.created_at.desc()).limit(50)).all()
            return [self._proposal_dto(row) for row in rows]

    def _validate_proposal_sources(self, db, row: MemoryProposal) -> None:
        for ref in list(row.source_refs or []):
            if ref.get("type") == "goal":
                run = db.scalar(select(AgentRun).where(
                    AgentRun.id == row.run_id,
                    AgentRun.owner_id == row.owner_id,
                ))
                if run is None:
                    raise CoworkerError("memory_proposal_source_invalidated", "A cited context source is no longer available.", 409)
                continue
            if ref.get("type") != "document":
                raise CoworkerError("memory_proposal_source_invalidated", "A cited context source is no longer available.", 409)
            version = db.scalar(select(DocumentVersion).where(
                DocumentVersion.id == ref.get("version_id"),
                DocumentVersion.owner_id == row.owner_id,
                DocumentVersion.sha256 == ref.get("sha256"),
                DocumentVersion.state == "uploaded",
            ))
            document = db.scalar(select(Document).where(
                Document.id == ref.get("document_id"),
                Document.owner_id == row.owner_id,
                Document.deleted.is_(False),
            ))
            if version is None or document is None or version.document_id != document.id:
                raise CoworkerError("memory_proposal_source_invalidated", "A cited context source is no longer available.", 409)

    def accept_proposal(self, owner: str, proposal_id: str) -> dict:
        self._enabled()
        with self.sessions.begin() as db:
            row = db.scalar(select(MemoryProposal).where(
                MemoryProposal.id == proposal_id,
                MemoryProposal.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state == "accepted" and row.accepted_fact_id:
                fact = db.scalar(select(MemoryFact).where(
                    MemoryFact.id == row.accepted_fact_id,
                    MemoryFact.owner_id == owner,
                ))
                return {"proposal": self._proposal_dto(row), "fact": self._dto(fact)} if fact else {"proposal": self._proposal_dto(row), "fact": None}
            if row.state != "proposed" or aware(row.expires_at) <= utcnow():
                if row.state == "proposed":
                    row.state = "expired"
                    row.reviewed_at = utcnow()
                raise CoworkerError("memory_proposal_unavailable", "This memory proposal can no longer be accepted.", 409)
            self._validate_proposal_sources(db, row)
            fact = db.scalar(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
                MemoryFact.workspace_id == row.workspace_id,
                MemoryFact.namespace == row.namespace,
                MemoryFact.key == row.key,
            ).with_for_update())
            if fact is None:
                if db.scalar(select(func.count()).select_from(MemoryFact).where(
                    MemoryFact.owner_id == owner,
                )) >= self.settings.max_memory_facts:
                    raise CoworkerError("memory_limit", "Your structured memory fact limit has been reached.", 429)
                fact = MemoryFact(
                    id=str(uuid4()), owner_id=owner, workspace_id=row.workspace_id,
                    namespace=row.namespace, key=row.key, value=row.value,
                    language=row.language, provenance_type="proposal", provenance_ref=row.id,
                    version=1, expires_at=None,
                )
                db.add(fact)
            else:
                fact.value = row.value
                fact.language = row.language
                fact.provenance_type = "proposal"
                fact.provenance_ref = row.id
                fact.version += 1
                fact.updated_at = utcnow()
            db.flush()
            row.state = "accepted"
            row.accepted_fact_id = fact.id
            row.reviewed_at = utcnow()
            self._audit(db, owner, row.id, "memory.proposal_accepted")
            self._audit(db, owner, fact.id, "memory.created_from_proposal")
            return {"proposal": self._proposal_dto(row), "fact": self._dto(fact)}

    def reject_proposal(self, owner: str, proposal_id: str) -> dict:
        with self.sessions.begin() as db:
            row = db.scalar(select(MemoryProposal).where(
                MemoryProposal.id == proposal_id,
                MemoryProposal.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state == "rejected":
                return self._proposal_dto(row)
            if row.state != "proposed" or aware(row.expires_at) <= utcnow():
                if row.state == "proposed":
                    row.state = "expired"
                    row.reviewed_at = utcnow()
                raise CoworkerError("memory_proposal_unavailable", "This memory proposal can no longer be rejected.", 409)
            row.state = "rejected"
            row.reviewed_at = utcnow()
            self._audit(db, owner, row.id, "memory.proposal_rejected")
            return self._proposal_dto(row)

    def context_for_run(self, owner: str, run_id: str) -> dict:
        if not self.settings.agent_memory_enabled:
            return {"facts": [], "provenance": []}
        with self.sessions() as db:
            run = db.scalar(select(AgentRun).where(
                AgentRun.id == run_id, AgentRun.owner_id == owner,
            ))
            if run is None:
                raise not_found()
            namespaces = list(run.memory_namespaces or [])
            if not namespaces:
                return {"facts": [], "provenance": []}
            now = utcnow()
            rows = db.scalars(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
                MemoryFact.workspace_id == run.workspace_id,
                MemoryFact.namespace.in_(namespaces),
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
