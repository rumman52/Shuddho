"""Trusted owner/project/document scope validation for project-bound goals and runs."""
from __future__ import annotations

from sqlalchemy import select

from .errors import CoworkerError
from .models import Document, DocumentVersion, Project, ProjectResource, utcnow
from .repository import aware, not_found


def validate_project_document_scope(
    db,
    owner: str,
    project_id: str | None,
    resources: list[dict] | None,
    *,
    require_documents: bool = False,
) -> list[str]:
    """Validate that selected document IDs still belong to this owner's live project.

    A project link is organizational metadata, not read permission by itself:
    callers must also supply the document IDs in the goal's explicit authorized
    resources. This helper validates that binding and the latest uploaded version.
    """
    if not project_id:
        if require_documents:
            raise CoworkerError(
                "briefing_project_required",
                "A recurring project briefing requires an owner-approved project.",
                409,
            )
        return []

    project = db.scalar(select(Project).where(
        Project.id == str(project_id),
        Project.owner_id == owner,
        Project.deleted.is_(False),
    ).with_for_update())
    if project is None:
        raise not_found()

    entries = resources if isinstance(resources, list) else []
    document_ids = [
        str(item.get("reference"))
        for item in entries
        if isinstance(item, dict)
        and item.get("kind") == "document"
        and isinstance(item.get("reference"), str)
        and item.get("reference")
    ]
    if require_documents and (
        len(entries) != len(document_ids) or not 1 <= len(document_ids) <= 5
    ):
        raise CoworkerError(
            "briefing_source_scope",
            "A project briefing requires one to five explicitly approved project documents only.",
            409,
        )
    if len(document_ids) != len(set(document_ids)):
        raise CoworkerError(
            "project_document_scope",
            "The selected project document scope contains duplicate IDs.",
            409,
        )
    if not document_ids:
        return []

    documents = db.scalars(select(Document).where(
        Document.id.in_(document_ids),
        Document.owner_id == owner,
        Document.deleted.is_(False),
    ).with_for_update()).all()
    if len(documents) != len(document_ids):
        raise not_found()

    linked_ids = set(db.scalars(select(ProjectResource.resource_id).where(
        ProjectResource.project_id == str(project_id),
        ProjectResource.owner_id == owner,
        ProjectResource.resource_type == "document",
        ProjectResource.resource_id.in_(document_ids),
    ).with_for_update()).all())
    if linked_ids != set(document_ids):
        raise CoworkerError(
            "project_document_unlinked",
            "A selected source document is no longer linked to the approved project.",
            409,
        )

    now = utcnow()
    for document in documents:
        latest = db.scalar(select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.owner_id == owner,
        ).order_by(DocumentVersion.version.desc()).limit(1).with_for_update())
        if (
            latest is None
            or latest.state != "uploaded"
            or (latest.expires_at is not None and aware(latest.expires_at) <= now)
        ):
            raise CoworkerError(
                "project_document_unavailable",
                "Each selected project document must have a current uploaded version.",
                409,
            )

    return document_ids
