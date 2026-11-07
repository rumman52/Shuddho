"""Owner-scoped project organization over existing chats and documents.

Account-before-project locking matches conversation creation and erasure. Links
never authorize reading sources in chat or starting Agent work.
"""
from uuid import uuid4
from sqlalchemy import delete, func, select
from .conversation_repository import ConversationRepository, fingerprint
from .errors import CoworkerError
from .models import Conversation, Document, Project, ProjectResource, utcnow
from .repository import iso, not_found

class ProjectRepository:
    def __init__(self, sessions, settings): self.sessions, self.settings = sessions, settings

    def enabled(self):
        if not self.settings.projects_enabled or not self.settings.conversations_enabled:
            raise CoworkerError("projects_unavailable", "Projects are not available in this workspace yet.", 409)

    @staticmethod
    def _project(db, owner, project_id, lock=False):
        query = select(Project).where(Project.id == project_id, Project.owner_id == owner, Project.deleted.is_(False))
        row = db.scalar(query.with_for_update() if lock else query)
        if row is None: raise not_found()
        return row

    @staticmethod
    def _dto(row):
        return {"id": row.id, "name": row.name, "description": row.description, "revision": row.revision,
                "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}

    @staticmethod
    def _resource(db, owner, kind, resource_id):
        model = Conversation if kind == "conversation" else Document
        return db.scalar(select(model).where(model.id == resource_id, model.owner_id == owner, model.deleted.is_(False)))

    def _detail(self, db, owner, row):
        resources = []
        for link in db.scalars(select(ProjectResource).where(ProjectResource.project_id == row.id, ProjectResource.owner_id == owner).order_by(ProjectResource.resource_type, ProjectResource.resource_id)):
            source = self._resource(db, owner, link.resource_type, link.resource_id)
            if source is not None:
                resources.append({"resource_type": link.resource_type, "resource_id": source.id,
                                  "title": source.title if link.resource_type == "conversation" else source.filename})
        return {**self._dto(row), "resources": resources}

    @staticmethod
    def _check_revision(row, expected):
        if row.revision != expected:
            raise CoworkerError("project_revision_conflict", "This project changed elsewhere. Refresh and review it before trying again.", 409)

    @staticmethod
    def _touch(row):
        row.revision += 1
        row.updated_at = utcnow()

    def create(self, owner, request, key):
        self.enabled()
        digest = fingerprint(request.model_dump(mode="json"))
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = db.scalar(select(Project).where(Project.owner_id == owner, Project.idempotency_key == key))
            if row:
                if row.deleted or row.fingerprint != digest:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to another project or a deleted project.", 409)
                return self._dto(row), False
            if db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == owner)) >= 100:
                raise CoworkerError("project_limit", "This workspace reached its project limit.", 429)
            row = Project(id=str(uuid4()), owner_id=owner, idempotency_key=key, fingerprint=digest, name=request.name,
                          description=request.description, revision=1, deleted=False, created_at=utcnow(), updated_at=utcnow())
            db.add(row); db.flush()
            ConversationRepository._audit(db, owner, row.id, "project.created")
            return self._dto(row), True

    def list(self, owner):
        self.enabled()
        with self.sessions() as db:
            rows = list(db.scalars(select(Project).where(
                Project.owner_id == owner, Project.deleted.is_(False)
            ).order_by(Project.updated_at.desc(), Project.id).limit(100)))
            if not rows:
                return []
            counts = dict(db.execute(
                select(ProjectResource.project_id, func.count(Conversation.id))
                .select_from(ProjectResource)
                .join(Conversation, Conversation.id == ProjectResource.resource_id)
                .where(
                    ProjectResource.owner_id == owner,
                    ProjectResource.resource_type == "conversation",
                    ProjectResource.project_id.in_([row.id for row in rows]),
                    Conversation.owner_id == owner,
                    Conversation.deleted.is_(False),
                )
                .group_by(ProjectResource.project_id)
            ).all())
            return [{**self._dto(row), "conversation_count": counts.get(row.id, 0)} for row in rows]

    def get(self, owner, project_id):
        self.enabled()
        with self.sessions() as db: return self._detail(db, owner, self._project(db, owner, project_id))

    def edit(self, owner, project_id, request):
        self.enabled()
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = self._project(db, owner, project_id, True)
            if row.name == request.name and row.description == request.description: return self._dto(row)
            self._check_revision(row, request.expected_revision)
            row.name, row.description = request.name, request.description
            self._touch(row)
            ConversationRepository._audit(db, owner, row.id, "project.updated")
            return self._dto(row)

    def link(self, owner, project_id, request):
        self.enabled()
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = self._project(db, owner, project_id, True)
            kind, resource_id = request.resource_type, str(request.resource_id)
            if self._resource(db, owner, kind, resource_id) is None: raise not_found()
            current = db.get(ProjectResource, (project_id, kind, resource_id))
            if current is not None: return self._detail(db, owner, row)
            self._check_revision(row, request.expected_revision)
            if db.scalar(select(func.count()).select_from(ProjectResource).where(ProjectResource.project_id == project_id)) >= 1000:
                raise CoworkerError("project_resource_limit", "This project reached its resource limit.", 429)
            db.add(ProjectResource(project_id=project_id, owner_id=owner, resource_type=kind, resource_id=resource_id))
            self._touch(row); db.flush()
            ConversationRepository._audit(db, owner, row.id, "project.resource_linked")
            return self._detail(db, owner, row)

    def unlink(self, owner, project_id, kind, resource_id, expected_revision):
        self.enabled()
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = self._project(db, owner, project_id, True)
            current = db.get(ProjectResource, (project_id, kind, resource_id))
            if current is None: return self._detail(db, owner, row)
            self._check_revision(row, expected_revision)
            db.delete(current); self._touch(row); db.flush()
            ConversationRepository._audit(db, owner, row.id, "project.resource_unlinked")
            return self._detail(db, owner, row)

    def delete(self, owner, project_id, expected_revision):
        self.enabled()
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = self._project(db, owner, project_id, True)
            self._check_revision(row, expected_revision)
            db.execute(delete(ProjectResource).where(ProjectResource.project_id == project_id, ProjectResource.owner_id == owner))
            row.deleted = True; self._touch(row)
            ConversationRepository._audit(db, owner, row.id, "project.deleted")
            return {"message": "Project deleted. Its conversations and files are preserved."}
