"""CW-08 owner-scoped, revisioned workspace inventory.

A read-only *projection* over authoritative records, not a second file ledger
or a history store. The digest allows clients to detect changes and reselect
context; it never grants access to file bytes or memory by itself.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select

from .errors import CoworkerError
from .models import Artifact, Document, DocumentVersion, MemoryFact, Workspace, utcnow
from .repository import aware, iso, not_found

MAX_ROWS_PER_KIND = 250


class WorkspaceManifestService:
    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings

    def get(self, owner: str) -> dict:
        if not self.settings.conversations_enabled:
            raise CoworkerError(
                "conversations_unavailable", "Workspace continuity is not enabled.", 409
            )
        now = utcnow()
        with self.sessions() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.owner_id == owner))
            if workspace is None:
                raise not_found()
            document_rows = db.execute(
                select(DocumentVersion, Document)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(Document.owner_id == owner, DocumentVersion.owner_id == owner,
                       Document.workspace_id == workspace.id, Document.deleted.is_(False),
                       DocumentVersion.state == "uploaded")
                .order_by(Document.id, DocumentVersion.version, DocumentVersion.id)
                .limit(MAX_ROWS_PER_KIND + 1)
            ).all()
            artifact_rows = db.scalars(
                select(Artifact).where(Artifact.owner_id == owner)
                .order_by(Artifact.id).limit(MAX_ROWS_PER_KIND + 1)
            ).all()
            # Reviewable metadata only. Do not expose memory values from a
            # metadata inventory, especially when memory capability is disabled.
            memory_rows = list(db.scalars(
                select(MemoryFact).where(MemoryFact.owner_id == owner,
                                         MemoryFact.workspace_id == workspace.id)
                .order_by(MemoryFact.namespace, MemoryFact.key, MemoryFact.id)
                .limit(MAX_ROWS_PER_KIND + 1)
            )) if self.settings.agent_memory_enabled else []

            documents = [{
                "document_id": document.id, "version_id": version.id,
                "name": document.filename, "version": version.version,
                "sha256": version.sha256, "expires_at": iso(version.expires_at),
                "available": version.expires_at is None or aware(version.expires_at) > now,
                "trust": "untrusted_source",
            } for version, document in document_rows[:MAX_ROWS_PER_KIND]]
            artifacts = [{
                "artifact_id": row.id, "name": row.filename,
                "sha256": row.sha256,
                "expires_at": iso(row.expires_at) if row.expires_at else None,
                "available": row.expires_at is None or aware(row.expires_at) > now,
                "trust": "untrusted_source",
            } for row in artifact_rows[:MAX_ROWS_PER_KIND]]
            memory = [{
                "fact_id": row.id, "namespace": row.namespace, "key": row.key,
                "version": row.version,
                "active": row.expires_at is None or aware(row.expires_at) > now,
            } for row in memory_rows[:MAX_ROWS_PER_KIND]]
            result = {
                "schema_version": 1,
                "workspace_id": workspace.id,
                "workspace_name": workspace.name,
                "documents": documents,
                "artifacts": artifacts,
                "memory": memory,
                "truncated": {
                    "documents": len(document_rows) > MAX_ROWS_PER_KIND,
                    "artifacts": len(artifact_rows) > MAX_ROWS_PER_KIND,
                    "memory": len(memory_rows) > MAX_ROWS_PER_KIND,
                },
            }
            canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            return result | {"revision_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}
