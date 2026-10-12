"""CW-08: revalidate owner-selected context before agent admission."""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import CoworkerError
from .models import Artifact, Document, DocumentVersion, utcnow
from .repository import aware

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_SELECTED = 10


def revalidate_selected_sources(
    db: Session, owner_id: str, selected_sources: list[dict], *,
    now: datetime | None = None,
) -> dict:
    """Recheck pinned CW-05 sources without granting authority or exposing contents."""
    if not isinstance(owner_id, str) or not owner_id:
        raise CoworkerError("context_scope", "Workspace identity is required.", 403)
    if not isinstance(selected_sources, list) or len(selected_sources) > _MAX_SELECTED:
        raise CoworkerError("context_sources_invalid", "Invalid selected source list.", 409)
    current_time = aware(now or utcnow())
    seen: set[tuple[str, str]] = set()
    active: list[dict] = []
    invalidated: list[dict] = []
    for index, source in enumerate(selected_sources):
        invalid = {"index": index, "reason": "unavailable_or_changed"}
        if not isinstance(source, dict):
            invalidated.append(invalid)
            continue
        source_type, resource_id, sha = (source.get("resource_type"), source.get("resource_id"), source.get("sha256"))
        if (source_type not in {"document_version", "artifact"} or not isinstance(resource_id, str)
            or not resource_id or not isinstance(sha, str) or not _SHA256.fullmatch(sha)):
            invalidated.append(invalid)
            continue
        identity = (source_type, resource_id)
        if identity in seen:
            invalidated.append(invalid)
            continue
        seen.add(identity)
        if source_type == "document_version":
            version_number = source.get("version")
            document_id = source.get("document_id")
            if type(version_number) is not int or version_number < 1 or not isinstance(document_id, str):
                invalidated.append(invalid)
                continue
            result = db.execute(
                select(DocumentVersion, Document)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentVersion.id == resource_id,
                    DocumentVersion.owner_id == owner_id,
                    Document.owner_id == owner_id,
                    Document.id == document_id,
                )
            ).first()
            if result is None:
                invalidated.append(invalid)
                continue
            version, document = result
            if (document.deleted or version.state != "uploaded" or version.version != version_number
                or version.sha256 != sha or
                (version.expires_at is not None and aware(version.expires_at) <= current_time)):
                invalidated.append(invalid)
                continue
            active.append({
                "resource_type": source_type, "resource_id": version.id,
                "document_id": document.id, "version": version.version,
                "sha256": version.sha256, "trust": "untrusted_source",
            })
        else:
            artifact = db.scalar(select(Artifact).where(Artifact.id == resource_id, Artifact.owner_id == owner_id))
            if (artifact is None or artifact.sha256 != sha or
                (artifact.expires_at is not None and aware(artifact.expires_at) <= current_time)):
                invalidated.append(invalid)
                continue
            active.append({
                "resource_type": source_type, "resource_id": artifact.id,
                "sha256": artifact.sha256, "trust": "untrusted_source",
            })
    return {"active": active, "invalidated": invalidated}


def require_current_selected_sources(db: Session, owner_id: str, selected_sources: list[dict]) -> list[dict]:
    """Deny admission if any persisted source changed, expired or left scope."""
    result = revalidate_selected_sources(db, owner_id, selected_sources)
    if result["invalidated"]:
        raise CoworkerError(
            "context_sources_changed",
            "One or more selected sources are unavailable or changed. Reselect them before running.",
            409,
        )
    return result["active"]
