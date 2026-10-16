from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from .auth import Principal
from .config import Settings
from .errors import CoworkerError
from .models import (
    Account, AgentRun, AgentStep, Artifact, AuditEvent, DailyUsage, Document,
    DocumentVersion, ModelAttempt, Outbox, ReviewedSkillPublication,
    ReviewedSkillSelection, Step, Task, TaskEvent, ToolInvocation, WorkerInstance,
    Workspace, utcnow,
)
from .provider_capacity import acquire_provider_lease, release_provider_lease, settle_provider_lease
from .schemas import TaskCreate, UploadRequest
from .skills import SKILLS, service_enabled
from .reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
    WORKER_ACTIVE_STATES,
    WORKER_HEARTBEAT_TTL_SECONDS,
    build_pilot_publication,
    require_pinned_publication,
    require_selected_pilot,
)
from .task_workflow_versions import (
    PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION,
    REVIEWED_RESEARCH_WORKFLOW_VERSION,
    task_skill_for_version,
)

TERMINAL = {"completed", "failed", "cancelled", "needs_input"}


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def iso(value: datetime) -> str:
    return aware(value).isoformat()


def not_found():
    return CoworkerError("not_found", "This item was not found in your workspace.", 404)


class Repository:
    def __init__(self, sessions, settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def _require_compatible_worker_fleet(
        self, db, *, task_queue: str, required_source_revision: str | None,
    ) -> None:
        if not required_source_revision:
            raise CoworkerError(
                "skill_worker_revision_mismatch",
                "Reviewed skill selection requires a full worker source revision.",
                409,
            )
        cutoff = utcnow() - timedelta(seconds=WORKER_HEARTBEAT_TTL_SECONDS)
        rows = db.scalars(select(WorkerInstance).where(
            WorkerInstance.task_queue == task_queue,
            WorkerInstance.state.in_(WORKER_ACTIVE_STATES),
        ).with_for_update()).all()
        incompatible = [
            row for row in rows
            if row.source_revision != required_source_revision
        ]
        if incompatible:
            raise CoworkerError(
                "worker_fleet_incompatible",
                "Reviewed skill selection is blocked while an incompatible worker is active or draining.",
                409,
            )
        if not any(
            row.source_revision == required_source_revision
            and row.state == "running"
            and aware(row.heartbeat_at) >= cutoff
            for row in rows
        ):
            raise CoworkerError(
                "worker_fleet_unavailable",
                "Reviewed skill selection requires at least one fresh compatible running worker.",
                409,
            )

    def publish_reviewed_skill(
        self, publication: dict, *, actor_reference: str, reason: str,
    ) -> dict:
        """Persist one immutable reviewed publication; never selects it."""
        if not actor_reference.strip() or len(actor_reference) > 200:
            raise CoworkerError("skill_publication_operator", "A non-empty operator reference is required.", 409)
        if not reason.strip() or len(reason) > 500:
            raise CoworkerError("skill_publication_operator", "A non-empty publication reason is required.", 409)
        required = {
            "skill_name", "publication_version", "task_workflow_version",
            "manifest_version", "review_sha256", "publication_sha256",
            "source_revision", "tool_names", "resource_limits", "manifest",
            "rollback_target_version",
        }
        if set(publication) != required:
            raise CoworkerError("skill_publication_untrusted", "The publication envelope is incomplete.", 409)
        if publication["skill_name"] != REVIEWED_RESEARCH_SKILL:
            raise CoworkerError("skill_publication_untrusted", "Only the reviewed research pilot is supported.", 409)
        if type(publication["publication_version"]) is not str or not publication["publication_version"].strip():
            raise CoworkerError("skill_publication_untrusted", "The publication version is invalid.", 409)
        if publication["task_workflow_version"] != REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION:
            raise CoworkerError("skill_publication_untrusted", "The publication workflow version is not reviewed.", 409)
        expected = build_pilot_publication(
            source_revision=publication["source_revision"],
            publication_version=publication["publication_version"],
            task_workflow_version=publication["task_workflow_version"],
            rollback_target_version=publication["rollback_target_version"],
        )
        if publication != expected:
            raise CoworkerError(
                "skill_publication_untrusted",
                "The publication does not match the code-reviewed pilot envelope.",
                409,
            )
        with self.sessions.begin() as db:
            existing = db.scalar(select(ReviewedSkillPublication).where(
                ReviewedSkillPublication.skill_name == publication["skill_name"],
                ReviewedSkillPublication.publication_version == publication["publication_version"],
            ))
            if existing is not None:
                raise CoworkerError("skill_publication_exists", "That reviewed skill publication version already exists.", 409)
            rollback_target = publication["rollback_target_version"]
            if rollback_target is not None:
                target_exists = db.scalar(select(ReviewedSkillPublication.id).where(
                    ReviewedSkillPublication.skill_name == publication["skill_name"],
                    ReviewedSkillPublication.publication_version == rollback_target,
                    ReviewedSkillPublication.state == "published",
                ))
                if target_exists is None:
                    raise CoworkerError(
                        "skill_publication_untrusted",
                        "The explicit rollback target must already be a published reviewed version.",
                        409,
                    )
            row = ReviewedSkillPublication(
                id=str(uuid4()), skill_name=publication["skill_name"],
                publication_version=publication["publication_version"],
                task_workflow_version=publication["task_workflow_version"],
                manifest_version=publication["manifest_version"],
                review_sha256=publication["review_sha256"],
                publication_sha256=publication["publication_sha256"],
                source_revision=publication["source_revision"],
                tool_names=publication["tool_names"],
                resource_limits=publication["resource_limits"],
                manifest=publication["manifest"],
                rollback_target_version=publication["rollback_target_version"],
                state="published",
            )
            db.add(row)
            db.flush()
            return self._reviewed_publication_dto(row)

    def select_reviewed_skill(
        self, skill_name: str, publication_version: str, *,
        actor_reference: str, reason: str, worker_source_revision: str | None,
    ) -> dict:
        if skill_name != REVIEWED_RESEARCH_SKILL:
            raise CoworkerError("skill_publication_untrusted", "Unsupported reviewed skill.", 409)
        if not actor_reference.strip() or len(actor_reference) > 200:
            raise CoworkerError("skill_publication_operator", "A non-empty operator reference is required.", 409)
        if not reason.strip() or len(reason) > 500:
            raise CoworkerError("skill_publication_operator", "A non-empty selection reason is required.", 409)
        with self.sessions.begin() as db:
            self._require_compatible_worker_fleet(
                db,
                task_queue=self.settings.task_queue,
                required_source_revision=worker_source_revision,
            )
            publication = db.scalar(select(ReviewedSkillPublication).where(
                ReviewedSkillPublication.skill_name == skill_name,
                ReviewedSkillPublication.publication_version == publication_version,
            ).with_for_update())
            if publication is None:
                raise CoworkerError("skill_publication_unavailable", "The requested reviewed publication is not published.", 409)
            binding = require_selected_pilot(publication, worker_source_revision=worker_source_revision)
            selection = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == skill_name,
            ).with_for_update())
            if selection is None:
                selection = ReviewedSkillSelection(
                    skill_name=skill_name, publication_id=binding.publication_id,
                    generation=1, state="selected",
                    updated_by=actor_reference, reason=reason,
                )
                db.add(selection)
            else:
                if selection.publication_id != binding.publication_id:
                    selection.publication_id = binding.publication_id
                    selection.generation = int(selection.generation or 0) + 1
                selection.state = "selected"
                selection.updated_by = actor_reference
                selection.reason = reason
                selection.updated_at = utcnow()
            db.flush()
            return self._reviewed_selection_dto(selection, publication)

    def rollback_reviewed_skill(
        self, skill_name: str, target_publication_version: str, *,
        actor_reference: str, reason: str, worker_source_revision: str | None,
    ) -> dict:
        if skill_name != REVIEWED_RESEARCH_SKILL:
            raise CoworkerError("skill_publication_untrusted", "Unsupported reviewed skill.", 409)
        if not actor_reference.strip() or len(actor_reference) > 200:
            raise CoworkerError("skill_publication_operator", "A non-empty operator reference is required.", 409)
        if not reason.strip() or len(reason) > 500:
            raise CoworkerError("skill_publication_operator", "A non-empty rollback reason is required.", 409)
        with self.sessions.begin() as db:
            selection = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == skill_name,
            ).with_for_update())
            if selection is None:
                raise CoworkerError("skill_rollback_unavailable", "There is no selected reviewed publication to roll back.", 409)
            current = db.scalar(select(ReviewedSkillPublication).where(
                ReviewedSkillPublication.id == selection.publication_id,
            ).with_for_update())
            target = db.scalar(select(ReviewedSkillPublication).where(
                ReviewedSkillPublication.skill_name == skill_name,
                ReviewedSkillPublication.publication_version == target_publication_version,
            ).with_for_update())
            if current is None or target is None:
                raise CoworkerError("skill_rollback_unavailable", "The selected or rollback publication is missing.", 409)
            if current.id == target.id:
                raise CoworkerError("skill_rollback_unavailable", "Rollback target is already selected.", 409)
            if current.state != "published":
                raise CoworkerError("skill_rollback_unavailable", "The current publication is not rollback-eligible.", 409)
            if current.rollback_target_version != target_publication_version:
                raise CoworkerError(
                    "skill_rollback_unavailable",
                    "Rollback target does not match the publication's explicitly declared rollback target.",
                    409,
                )
            self._require_compatible_worker_fleet(
                db,
                task_queue=self.settings.task_queue,
                required_source_revision=worker_source_revision,
            )
            require_selected_pilot(target, worker_source_revision=worker_source_revision)
            current.state = "rolled_back"
            current.updated_at = utcnow()
            selection.publication_id = target.id
            selection.generation = int(selection.generation or 0) + 1
            selection.state = "selected"
            selection.updated_by = actor_reference
            selection.reason = reason
            selection.updated_at = utcnow()
            db.flush()
            return self._reviewed_selection_dto(selection, target)

    def selected_reviewed_skill(self, skill_name: str) -> dict | None:
        with self.sessions() as db:
            selection = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == skill_name,
            ))
            if selection is None or selection.state != "selected":
                return None
            publication = db.get(ReviewedSkillPublication, selection.publication_id)
            if publication is None:
                return None
            return self._reviewed_selection_dto(selection, publication)

    @staticmethod
    def _reviewed_publication_dto(row: ReviewedSkillPublication) -> dict:
        return {
            "id": row.id, "skill_name": row.skill_name,
            "publication_version": row.publication_version,
            "task_workflow_version": row.task_workflow_version,
            "manifest_version": row.manifest_version,
            "review_sha256": row.review_sha256,
            "publication_sha256": row.publication_sha256,
            "source_revision": row.source_revision,
            "tool_names": list(row.tool_names or ()),
            "resource_limits": dict(row.resource_limits or {}),
            "rollback_target_version": row.rollback_target_version,
            "state": row.state, "published_at": iso(row.published_at),
            "updated_at": iso(row.updated_at),
        }

    @classmethod
    def _reviewed_selection_dto(
        cls, selection: ReviewedSkillSelection, publication: ReviewedSkillPublication,
    ) -> dict:
        return {
            "skill_name": selection.skill_name,
            "publication_id": selection.publication_id,
            "publication_version": publication.publication_version,
            "task_workflow_version": publication.task_workflow_version,
            "publication_sha256": publication.publication_sha256,
            "review_sha256": publication.review_sha256,
            "source_revision": publication.source_revision,
            "generation": selection.generation,
            "state": selection.state,
            "updated_at": iso(selection.updated_at),
        }

    def reviewed_skill_runtime_manifest(self) -> dict:
        selected = self.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)
        if selected is None:
            return {"research": {
                "state": "unselected", "publication_version": None,
                "publication_sha256": None, "review_sha256": None,
                "source_revision": None, "task_workflow_version": None,
                "generation": None,
            }}
        return {"research": {
            key: selected[key]
            for key in (
                "state", "publication_version", "publication_sha256",
                "review_sha256", "source_revision",
                "task_workflow_version", "generation",
            )
        }}

    def register_worker(self, *, task_queue: str, source_revision: str | None) -> str:
        worker_id = str(uuid4())
        with self.sessions.begin() as db:
            db.add(WorkerInstance(
                id=worker_id, task_queue=task_queue,
                source_revision=source_revision or "unknown",
                state="starting",
            ))
        return worker_id

    def heartbeat_worker(self, worker_id: str) -> str:
        with self.sessions.begin() as db:
            row = db.get(WorkerInstance, worker_id)
            if row is None:
                return "lost"
            if row.state in {"drained", "lost"}:
                return row.state
            row.state = "draining" if row.drain_requested_at is not None else "running"
            row.heartbeat_at = utcnow()
            return row.state

    def mark_worker_drained(self, worker_id: str) -> None:
        with self.sessions.begin() as db:
            row = db.get(WorkerInstance, worker_id)
            if row is not None and row.state != "lost":
                row.state = "drained"
                row.drained_at = utcnow()
                row.heartbeat_at = utcnow()

    def request_worker_drain(
        self, *, task_queue: str, source_revision: str,
        actor_reference: str, reason: str,
    ) -> int:
        if not actor_reference.strip() or len(actor_reference) > 200:
            raise CoworkerError("worker_drain_operator", "A non-empty operator reference is required.", 409)
        if not reason.strip() or len(reason) > 500:
            raise CoworkerError("worker_drain_operator", "A non-empty drain reason is required.", 409)
        with self.sessions.begin() as db:
            cutoff = utcnow() - timedelta(seconds=WORKER_HEARTBEAT_TTL_SECONDS)
            rows = db.scalars(select(WorkerInstance).where(
                WorkerInstance.task_queue == task_queue,
                WorkerInstance.source_revision == source_revision,
                WorkerInstance.state.in_(WORKER_ACTIVE_STATES),
                WorkerInstance.heartbeat_at >= cutoff,
            ).with_for_update()).all()
            now = utcnow()
            for row in rows:
                row.state = "draining"
                row.drain_requested_at = now
                row.heartbeat_at = now
            return len(rows)

    def worker_inventory(self, *, task_queue: str | None = None) -> list[dict]:
        with self.sessions() as db:
            stmt = select(WorkerInstance).order_by(WorkerInstance.started_at.desc())
            if task_queue:
                stmt = stmt.where(WorkerInstance.task_queue == task_queue)
            rows = db.scalars(stmt).all()
            cutoff = utcnow() - timedelta(seconds=WORKER_HEARTBEAT_TTL_SECONDS)
            return [{
                "id": row.id, "task_queue": row.task_queue,
                "source_revision": row.source_revision, "state": row.state,
                "started_at": iso(row.started_at),
                "heartbeat_at": iso(row.heartbeat_at),
                "heartbeat_fresh": aware(row.heartbeat_at) >= cutoff,
                "drain_requested_at": iso(row.drain_requested_at) if row.drain_requested_at else None,
                "drained_at": iso(row.drained_at) if row.drained_at else None,
            } for row in rows]

    def assert_worker_drain_complete(
        self, *, task_queue: str, old_source_revision: str,
    ) -> dict:
        inventory = self.worker_inventory(task_queue=task_queue)
        blockers = [
            row for row in inventory
            if row["source_revision"] == old_source_revision
            and row["state"] in (WORKER_ACTIVE_STATES | {"lost"})
        ]
        if blockers:
            raise CoworkerError(
                "worker_drain_incomplete",
                "The legacy worker fleet has not reached an explicit drained state; lost workers are treated as uncertain.",
                409,
            )
        return {
            "task_queue": task_queue,
            "old_source_revision": old_source_revision,
            "verified": True,
            "workers": inventory,
        }

    def _require_selected_reviewed_publication(
        self, db, review_sha256: str,
    ):
        selection = db.scalar(select(ReviewedSkillSelection).where(
            ReviewedSkillSelection.skill_name == REVIEWED_RESEARCH_SKILL,
        ).with_for_update())
        if selection is None or selection.state != "selected":
            raise CoworkerError(
                "skill_publication_unavailable",
                "The reviewed research skill has no explicitly selected publication.",
                409,
            )
        publication = db.scalar(select(ReviewedSkillPublication).where(
            ReviewedSkillPublication.id == selection.publication_id,
        ).with_for_update())
        binding = require_selected_pilot(
            publication,
            worker_source_revision=self.settings.source_revision,
        )
        if binding.review_sha256 != review_sha256:
            raise CoworkerError(
                "skill_publication_unavailable",
                "The selected publication does not match the admitted reviewed manifest.",
                409,
            )
        return binding

    def migrate_legacy_reviewed_tasks(
        self, *, task_queue: str, old_source_revision: str,
        publication_version: str, actor_reference: str, reason: str,
    ) -> dict:
        """Migrate only safely admitted legacy reviewed tasks after explicit worker drain."""
        self.assert_worker_drain_complete(
            task_queue=task_queue,
            old_source_revision=old_source_revision,
        )
        with self.sessions.begin() as db:
            self._require_compatible_worker_fleet(
                db,
                task_queue=task_queue,
                required_source_revision=self.settings.source_revision,
            )
            selection = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == REVIEWED_RESEARCH_SKILL,
            ).with_for_update())
            if selection is None or selection.state != "selected":
                raise CoworkerError(
                    "skill_migration_blocked",
                    "A reviewed publication must be explicitly selected before historical migration.",
                    409,
                )
            publication = db.scalar(select(ReviewedSkillPublication).where(
                ReviewedSkillPublication.id == selection.publication_id,
            ).with_for_update())
            if publication is None or publication.publication_version != publication_version:
                raise CoworkerError(
                    "skill_migration_blocked",
                    "The selected publication does not match the requested migration target.",
                    409,
                )
            binding = require_selected_pilot(
                publication,
                worker_source_revision=self.settings.source_revision,
            )
            rows = db.scalars(
                select(Task)
                .join(Step, (Step.task_id == Task.id) & (Step.phase == "reviewed_skill_identity"))
                .where(
                    Task.workflow_version == PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION,
                    Task.state.not_in(TERMINAL),
                )
                .with_for_update()
            ).all()
            blockers: list[dict] = []
            for task in rows:
                if task.agent_run_id is None or task.agent_step_id is None:
                    blockers.append({"task_id": task.id, "code": "missing_agent_binding"})
                    continue
                options = db.get(Step, (task.id, "research_input"))
                if options is None:
                    blockers.append({"task_id": task.id, "code": "missing_research_input"})
                    continue
                try:
                    from .schemas import ResearchOptions
                    document_ids = []
                    for version_id in task.input_versions:
                        version = db.get(DocumentVersion, version_id)
                        if version is None or version.owner_id != task.owner_id:
                            raise CoworkerError("skill_run_scope", "A source version is missing.")
                        document_ids.append(UUID(version.document_id))
                    request = TaskCreate(
                        skill_id="research",
                        instruction=task.instruction,
                        notes=task.notes,
                        document_ids=document_ids,
                        output_language=task.output_language,
                        research=ResearchOptions.model_validate(options.output),
                    )
                    digest = self._require_reviewed_agent_research(
                        db, task.owner_id, task.agent_run_id, task.agent_step_id,
                        request, input_versions=list(task.input_versions or ()),
                        enforce_gate=False,
                    )
                    identity = db.get(Step, (task.id, "reviewed_skill_identity"))
                    expected_identity = {
                        "name": "research",
                        "version": "work_research_v1",
                        "tool": "research.search",
                        "tool_version": "1",
                        "review_sha256": digest,
                    }
                    if identity is None or identity.output != expected_identity:
                        raise CoworkerError(
                            "skill_manifest_unreviewed",
                            "The historical reviewed identity is not exact.",
                        )
                    if digest != binding.review_sha256:
                        raise CoworkerError(
                            "skill_manifest_unreviewed",
                            "The historical review hash does not match the migration publication.",
                        )
                    if task.deadline_at is None or aware(task.deadline_at) <= utcnow():
                        raise CoworkerError("skill_migration_blocked", "The historical task deadline expired.")
                    run = db.get(AgentRun, task.agent_run_id)
                    if run is None or run.cancel_requested or aware(run.deadline_at) <= utcnow():
                        raise CoworkerError("skill_migration_blocked", "The historical Agent run is cancelled or expired.")
                    search_attempt = db.get(Step, (task.id, "search_attempt"))
                    if search_attempt is not None:
                        raise CoworkerError(
                            "skill_migration_blocked",
                            "A historical task already has a search attempt and cannot be safely rebound.",
                        )
                except (CoworkerError, ValueError, TypeError) as error:
                    blockers.append({"task_id": task.id, "code": getattr(error, "code", "invalid_historical_task")})
            if blockers:
                raise CoworkerError(
                    "skill_migration_blocked",
                    "Historical reviewed-task migration is blocked by unsafe or ambiguous rows.",
                    409,
                )
            migrated = 0
            for task in rows:
                identity = db.get(Step, (task.id, "reviewed_skill_identity"))
                task.workflow_version = binding.task_workflow_version
                identity.output = {
                    "publication_id": binding.publication_id,
                    "publication_version": binding.publication_version,
                    "publication_sha256": binding.publication_sha256,
                    "review_sha256": binding.review_sha256,
                    "source_revision": binding.source_revision,
                    "task_workflow_version": binding.task_workflow_version,
                }
                task.updated_at = utcnow()
                migrated += 1
            return {
                "task_queue": task_queue,
                "old_source_revision": old_source_revision,
                "publication_version": publication_version,
                "migrated": migrated,
                "verified": True,
            }

    def ensure_account(self, principal: Principal) -> dict:
        owner = principal.account_id
        workspace_id = str(uuid5(NAMESPACE_URL, "shuddho:workspace:" + owner))
        with self.sessions.begin() as db:
            if db.get(Account, owner) is None:
                try:
                    with db.begin_nested():
                        db.add(Account(id=owner, issuer=principal.issuer, subject=principal.subject))
                        db.flush()
                except IntegrityError:
                    pass
            if db.get(Workspace, workspace_id) is None:
                try:
                    with db.begin_nested():
                        db.add(Workspace(id=workspace_id, owner_id=owner))
                        db.flush()
                except IntegrityError:
                    pass
            account = db.get(Account, owner)
            usage = db.get(DailyUsage, (owner, utcnow().date().isoformat()))
            return {"account_id": owner, "workspace_id": workspace_id, "workspace_name": "My workspace",
                    "preferences": account.preferences, "usage": {"tasks_today": usage.task_count if usage else 0,
                    "allocated_tokens_today": usage.allocated_tokens if usage else 0},
                    "limits": {"daily_tasks": self.settings.max_daily_tasks, "active_tasks": self.settings.max_active_tasks,
                               "upload_bytes": self.settings.max_upload_bytes, "daily_tokens": self.settings.daily_token_budget}}

    def _account(self, db, owner):
        value = db.scalar(select(Account).where(Account.id == owner).with_for_update())
        if value is None:
            raise not_found()
        return value

    def _workspace(self, db, owner):
        return db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))

    def _audit(self, db, owner, resource, action):
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    def save_preferences(self, owner, preferences):
        with self.sessions.begin() as db:
            account = self._account(db, owner)
            current = dict(account.preferences or {})
            current.update(preferences)
            account.preferences = current
            self._audit(db, owner, owner, "preferences_updated")
        return preferences

    def create_upload(self, owner: str, request: UploadRequest) -> dict:
        with self.sessions.begin() as db:
            account = self._account(db, owner)
            if request.filename.rsplit(".", 1)[1].lower() in {"csv", "xlsx", "pptx"} and not self.settings.artifact_services_enabled:
                raise CoworkerError("service_unavailable", "Spreadsheet and presentation uploads are not available yet.", 409)
            count = db.scalar(select(func.count()).select_from(Document).where(Document.owner_id == owner, Document.deleted.is_(False)))
            if count >= 100:
                raise CoworkerError("document_limit", "Your workspace has 100 source files. Remove an unused upload before adding another.", 429)
            if request.byte_size > self.settings.max_upload_bytes or account.storage_bytes + request.byte_size > self.settings.max_account_bytes:
                raise CoworkerError("storage_limit", "Your workspace has reached its file storage limit.", 429)
            document_id, version_id = str(uuid4()), str(uuid4())
            document = Document(id=document_id, owner_id=owner, workspace_id=self._workspace(db, owner), filename=request.filename)
            db.add(document)
            db.flush()
            version = DocumentVersion(id=version_id, document_id=document_id, owner_id=owner,
                                      kind=request.filename.rsplit(".", 1)[1].lower(), byte_size=request.byte_size,
                                      sha256=request.sha256, object_key=f"{owner}/inputs/{version_id}/{request.sha256}",
                                      expires_at=utcnow() + timedelta(hours=1))
            db.add(version)
            account.storage_bytes += request.byte_size
            self._audit(db, owner, document_id, "upload_initialized")
            db.flush()
            return self._document_dto(document, version)

    def _document_dto(self, document, version):
        return {"id": document.id, "version_id": version.id, "filename": document.filename,
                "kind": version.kind, "byte_size": version.byte_size, "sha256": version.sha256,
                "state": version.state, "expires_at": iso(version.expires_at)}

    def get_upload(self, owner, document_id):
        with self.sessions() as db:
            document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner, Document.deleted.is_(False)))
            if document is None:
                raise not_found()
            version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id, DocumentVersion.owner_id == owner))
            if version.state != "uploaded" and aware(version.expires_at) < utcnow():
                raise CoworkerError("upload_expired", "This upload expired. Please select the file again.", 410)
            return self._document_dto(document, version) | {"object_key": version.object_key}

    def finish_upload(self, owner, document_id):
        with self.sessions.begin() as db:
            version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id, DocumentVersion.owner_id == owner).with_for_update())
            document = db.get(Document, document_id)
            if version is None or document is None or document.deleted:
                raise not_found()
            if version.state != "uploaded":
                if aware(version.expires_at) < utcnow():
                    raise CoworkerError("upload_expired", "This upload expired. Please select the file again.", 410)
                version.state = "uploaded"
                self._audit(db, owner, document_id, "upload_completed")
            return self._document_dto(document, version)

    def list_documents(self, owner):
        with self.sessions() as db:
            rows = db.execute(select(Document, DocumentVersion).join(DocumentVersion, Document.id == DocumentVersion.document_id).where(
                Document.owner_id == owner, Document.deleted.is_(False), DocumentVersion.state == "uploaded",
            ).order_by(Document.created_at.desc()).limit(100))
            return [self._document_dto(document, version) for document, version in rows]

    def delete_document(self, owner, document_id):
        with self.sessions.begin() as db:
            self._account(db, owner)
            document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner))
            if document is None:
                raise not_found()
            versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id)).all()
            version_ids = {value.id for value in versions}
            active = db.scalars(select(Task).where(Task.owner_id == owner, Task.state.not_in(TERMINAL)))
            if any(version_ids.intersection(value.input_versions) for value in active):
                raise CoworkerError("document_in_use", "This source is used by an active task. Wait for it to finish or cancel it first.", 409)
            if not document.deleted:
                document.deleted = True
                for version in versions:
                    version.expires_at = utcnow()
                self._audit(db, owner, document_id, "source_deletion_requested")
            return {"id": document_id, "state": "deleted", "message": "Upload removed. Existing drafts remain in your task history."}

    def _require_reviewed_agent_research(
        self, db, owner: str, run_id: str, step_id: str | None,
        request: TaskCreate, *, input_versions: list[str] | None = None,
        enforce_gate: bool = True,
    ) -> str | None:
        """Bind an opted-in reviewed research skill to the existing SQL run/step/tool."""
        if not self.settings.agent_reviewed_research_skill_enabled and enforce_gate:
            return None
        from .agent_tools import TOOLS
        from .skill_manifests import pilot_skill_manifest, validate_manifest
        from .schemas import ResearchOptions

        run = db.scalar(select(AgentRun).where(
            AgentRun.id == run_id, AgentRun.owner_id == owner,
        ))
        step = db.scalar(select(AgentStep).where(
            AgentStep.id == step_id, AgentStep.run_id == run_id,
            AgentStep.owner_id == owner,
        )) if step_id else None
        invocation = db.scalar(select(ToolInvocation).where(
            ToolInvocation.step_id == step_id,
            ToolInvocation.run_id == run_id, ToolInvocation.owner_id == owner,
        )) if step_id else None
        spec = TOOLS.get("research.search")
        if (
            run is None or step is None or invocation is None
            or run.cancel_requested
            or aware(run.deadline_at) <= utcnow()
            or run.state not in {"queued", "planning", "running", "awaiting_approval"}
            or step.tool_name != "research.search"
            or invocation.tool_name != "research.search"
            or invocation.state not in {"prepared", "running"}
            or spec is None or not spec.enabled(self.settings)
            or invocation.tool_version != spec.version
            or request.skill_id != "research"
            # The pilot manifest authorizes only ONE research tool call per run.
            or db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run_id,
                ToolInvocation.owner_id == owner,
                ToolInvocation.tool_name == "research.search",
            )) != 1
        ):
            raise CoworkerError(
                "skill_run_scope",
                "The research task is not bound to an eligible owned Agent run and tool.",
                409,
            )
        arguments = spec.validate(invocation.arguments)
        if (
            request.instruction != arguments.instruction
            or request.notes != arguments.notes
            or request.document_ids != arguments.document_ids
            or request.output_language != arguments.output_language
            or request.research != ResearchOptions(
                query=arguments.query, time_range=arguments.time_range,
            )
        ):
            raise CoworkerError(
                "skill_run_scope",
                "Research task inputs differ from the authorized Agent invocation.",
                409,
            )
        try:
            manifest = pilot_skill_manifest()
        except (ValueError, TypeError, OSError):
            raise CoworkerError(
                "skill_manifest_unreviewed",
                "The reviewed research skill source or version is unavailable.",
                409,
            ) from None
        if manifest.version != SKILLS["research"].version:
            raise CoworkerError(
                "skill_manifest_unreviewed",
                "The task skill version is not reviewed.",
                409,
            )
        validate_manifest(manifest, frozenset(run.tool_allowlist or ()))
        # Document identities alone are insufficient: the reviewed Agent run
        # pinned *versions*. A later upload/replacement cannot be pulled into
        # this Task merely because it has the same document ID.
        if input_versions is not None and not set(input_versions).issubset(
            set(run.input_versions or ())
        ):
            raise CoworkerError(
                "skill_run_scope",
                "The reviewed Task uses source versions outside the admitted Agent run.",
                409,
            )
        return manifest.review_sha256()

    def _reviewed_research_worker_task(self, db, task: Task) -> None:
        """Rebuild pinned task inputs and recheck manifest/grants before each phase."""
        from .schemas import ResearchOptions

        document_ids = []
        for version_id in task.input_versions:
            version = db.get(DocumentVersion, version_id)
            if version is None or version.owner_id != task.owner_id:
                raise not_found()
            document_ids.append(UUID(version.document_id))
        options = db.get(Step, (task.id, "research_input"))
        if options is None:
            raise CoworkerError(
                "skill_run_scope", "The pinned research inputs are missing.", 409,
            )
        request = TaskCreate(
            skill_id="research", instruction=task.instruction,
            notes=task.notes, document_ids=document_ids,
            output_language=task.output_language,
            research=ResearchOptions.model_validate(options.output),
        )
        digest = self._require_reviewed_agent_research(
            db, task.owner_id, task.agent_run_id, task.agent_step_id,
            request, input_versions=list(task.input_versions or ()),
        )
        stored_review = db.get(Step, (task.id, "reviewed_skill_identity"))
        if stored_review is None or digest is None:
            raise CoworkerError(
                "skill_manifest_unreviewed",
                "The Task has no matching immutable reviewed skill identity.",
                409,
            )
        publication_id = (
            stored_review.output.get("publication_id")
            if isinstance(stored_review.output, dict) else None
        )
        publication = (
            db.get(ReviewedSkillPublication, publication_id)
            if publication_id else None
        )
        binding = require_pinned_publication(
            publication,
            stored_review.output,
            worker_source_revision=self.settings.source_revision,
        )
        if (
            task.workflow_version != REVIEWED_RESEARCH_WORKFLOW_VERSION
            or binding.task_workflow_version != REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION
            or binding.review_sha256 != digest
        ):
            raise CoworkerError(
                "skill_manifest_unreviewed",
                "The Task has no matching immutable reviewed skill identity.",
                409,
            )

    def create_task(self, owner: str, request: TaskCreate, idempotency_key: str, *, enqueue: bool = True, agent_run_id: str | None = None, agent_step_id: str | None = None) -> tuple[dict, bool]:
        self.expire_tasks(owner)
        if agent_step_id is not None and agent_run_id is None:
            raise CoworkerError("agent_step_scope", "An agent step requires an agent run.", 409)
        payload = request.model_dump(mode="json")
        if request.research is None:
            payload.pop("research")  # Preserve fingerprints for every pre-research service.
        # Preserve the exact Part 2 fingerprint when the legacy service is selected.
        if request.skill_id == "report_email":
            payload.pop("skill_id")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as db:
            self._account(db, owner)  # Serializes quota and idempotency decisions per account.
            previous = db.scalar(select(Task).where(Task.owner_id == owner, Task.idempotency_key == idempotency_key))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to different input. Submit a new task.", 409)
                # The public Task API accepts arbitrary keys, including the
                # predictable agent:<run>:<step> namespace. Never let an Agent
                # adopt a standalone task (or a different Agent step), nor let
                # a standalone replay read an Agent-owned task.
                if (
                    previous.agent_run_id != agent_run_id
                    or previous.agent_step_id != agent_step_id
                ):
                    raise CoworkerError(
                        "task_agent_binding_conflict",
                        "This task key is bound to a different Agent execution.",
                        409,
                    )
                if previous.state not in TERMINAL and (
                    db.get(Step, (previous.id, "reviewed_skill_identity")) is not None
                    or previous.workflow_version == REVIEWED_RESEARCH_WORKFLOW_VERSION
                    or (
                        self.settings.agent_reviewed_research_skill_enabled
                        and request.skill_id == "research"
                        and agent_run_id is not None
                    )
                ):
                    # A task admitted under reviewed policy stays reviewed even
                    # after a deployment disables new reviewed-skill admission.
                    # It must fail closed, never replay as legacy research.
                    self._reviewed_research_worker_task(db, previous)
                return self._task_dto(db, previous), False
            enabled = service_enabled(request.skill_id, self.settings.work_services_enabled,
                                      self.settings.artifact_services_enabled, self.settings.research_services_enabled)
            if not enabled:
                raise CoworkerError("service_unavailable", "This work service is not available yet. Please choose another service.", 409)
            reviewed_skill_digest = None
            reviewed_publication = None
            if request.skill_id == "research" and agent_run_id is not None:
                reviewed_skill_digest = self._require_reviewed_agent_research(
                    db, owner, agent_run_id, agent_step_id, request,
                )
                if reviewed_skill_digest is not None:
                    reviewed_publication = self._require_selected_reviewed_publication(
                        db, reviewed_skill_digest,
                    )
            if reviewed_publication is not None:
                duplicate = db.scalar(select(Task.id).where(
                    Task.agent_run_id == agent_run_id,
                    Task.agent_step_id == agent_step_id,
                ))
                if duplicate is not None:
                    raise CoworkerError(
                        "task_agent_binding_conflict",
                        "This Agent research invocation is already bound to a Task.",
                        409,
                    )
            active = db.scalar(select(func.count()).select_from(Task).where(Task.owner_id == owner, Task.state.not_in(TERMINAL)))
            day = utcnow().date().isoformat()
            usage = db.get(DailyUsage, (owner, day))
            if usage is None:
                usage = DailyUsage(owner_id=owner, day=day, allocated_tokens=0, task_count=0)
                db.add(usage)
            if active >= self.settings.max_active_tasks:
                raise CoworkerError("active_task_limit", "Your coworker is already working on your active tasks. Try again when one finishes.", 429)
            if usage.task_count >= self.settings.max_daily_tasks or usage.allocated_tokens >= self.settings.daily_token_budget:
                raise CoworkerError("daily_limit", "Your daily coworker limit has been reached. Try again tomorrow.", 429)
            versions = []
            for document_id in request.document_ids:
                row = db.execute(select(DocumentVersion, Document).join(Document, DocumentVersion.document_id == Document.id).where(
                    Document.id == str(document_id), Document.owner_id == owner, Document.deleted.is_(False),
                    DocumentVersion.owner_id == owner, DocumentVersion.state == "uploaded",
                )).first()
                if row is None:
                    raise not_found()
                versions.append(row[0].id)
            if reviewed_skill_digest is not None:
                # The SQL-owned Agent run, not the latest document upload,
                # determines which exact source versions a reviewed Task uses.
                run = db.get(AgentRun, agent_run_id)
                if run is None or not set(versions).issubset(
                    set(run.input_versions or ())
                ):
                    raise CoworkerError(
                        "skill_run_scope",
                        "A Task source version is not pinned to its Agent run.",
                        409,
                    )
            task = Task(id=str(uuid4()), owner_id=owner, workspace_id=self._workspace(db, owner),
                        idempotency_key=idempotency_key, fingerprint=fingerprint, instruction=request.instruction,
                        agent_run_id=agent_run_id, agent_step_id=agent_step_id,
                        notes=request.notes, output_language=request.output_language, input_versions=versions,
                        workflow_version=(
                            REVIEWED_RESEARCH_WORKFLOW_VERSION if reviewed_publication is not None
                            else SKILLS[request.skill_id].version
                        ),
                        deadline_at=utcnow() + timedelta(seconds=self.settings.task_timeout_seconds))
            db.add(task)
            db.flush()
            if reviewed_publication is not None:
                # Pin the complete publication identity alongside the Task.
                # Normal selection changes do not mutate an admitted Task;
                # explicit rollback marks its publication rolled_back.
                db.add(Step(
                    task_id=task.id, phase="reviewed_skill_identity",
                    output={
                        "publication_id": reviewed_publication.publication_id,
                        "publication_version": reviewed_publication.publication_version,
                        "publication_sha256": reviewed_publication.publication_sha256,
                        "review_sha256": reviewed_publication.review_sha256,
                        "source_revision": reviewed_publication.source_revision,
                        "task_workflow_version": reviewed_publication.task_workflow_version,
                    },
                ))
            if request.research:
                # Immutable task options, committed atomically with the task/outbox.
                db.add(Step(task_id=task.id, phase="research_input", output=request.research.model_dump()))
            usage.task_count += 1
            if enqueue:
                db.add(Outbox(task_id=task.id))
            self._event(db, task, "queued", "queued", "Queued for your coworker.")
            self._audit(db, owner, task.id, "task_created")
            return self._task_dto(db, task), True

    def _task_dto(self, db, task, detail=True):
        artifacts = db.scalars(select(Artifact).where(Artifact.task_id == task.id, Artifact.owner_id == task.owner_id)).all()
        draft_step = db.get(Step, (task.id, "draft")) if detail else None
        usage = db.scalars(select(ModelAttempt).where(ModelAttempt.task_id == task.id)).all()
        research_input = db.get(Step, (task.id, "research_input")) if task.workflow_version in {
            "work_research_v1", REVIEWED_RESEARCH_WORKFLOW_VERSION,
        } else None
        search_attempt = db.get(Step, (task.id, "search_attempt")) if research_input else None
        return {"id": task.id, "state": task.state, "phase": task.phase, "message": task.message,
                "error_code": task.error_code, "output_language": task.output_language,
                "skill_id": task_skill_for_version(task.workflow_version).id, "workflow_version": task.workflow_version,
                "instruction": task.instruction, "created_at": iso(task.created_at), "updated_at": iso(task.updated_at),
                "event_sequence": task.event_sequence, "cancel_requested": task.cancel_requested,
                "artifacts": [{"id": item.id, "filename": item.filename, "content_type": item.content_type,
                               "byte_size": item.byte_size, "sha256": item.sha256} for item in artifacts],
                "draft": draft_step.output.get("draft") if draft_step else None,
                "preview": draft_step.output.get("preview") if draft_step else None,
                "sources": draft_step.output.get("sources", []) if draft_step else [],
                "research": draft_step.output.get("research") if draft_step else None,
                "input": {"notes": task.notes, "document_ids": list(db.scalars(select(DocumentVersion.document_id).where(
                    DocumentVersion.id.in_(task.input_versions), DocumentVersion.owner_id == task.owner_id,
                ))), **({"research": research_input.output} if research_input else {})} if detail else None,
                "usage": {"model_attempts": len(usage), "accounted_tokens": sum(item.charged_tokens for item in usage),
                          **({"search": search_attempt.output} if search_attempt else {})}}

    def get_task(self, owner, task_id):
        self.expire_tasks(owner)
        with self.sessions() as db:
            task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner))
            if task is None:
                raise not_found()
            return self._task_dto(db, task)

    def list_tasks(self, owner):
        self.expire_tasks(owner)
        with self.sessions() as db:
            tasks = db.scalars(select(Task).where(Task.owner_id == owner).order_by(Task.created_at.desc()).limit(30))
            return [self._task_dto(db, item, detail=False) for item in tasks]

    def _event(self, db, task, state, phase, message):
        task.state, task.phase, task.message = state, phase, message
        task.updated_at = utcnow()
        task.event_sequence += 1
        db.add(TaskEvent(task_id=task.id, sequence=task.event_sequence, state=state, phase=phase, message=message))

    def events(self, owner, task_id, after=0):
        self.expire_tasks(owner)
        with self.sessions() as db:
            task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner))
            if task is None:
                raise not_found()
            rows = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id, TaskEvent.sequence > after).order_by(TaskEvent.sequence).limit(100))
            return {"events": [{"sequence": row.sequence, "state": row.state, "phase": row.phase,
                                "message": row.message, "created_at": iso(row.created_at)} for row in rows],
                    "terminal": task.state in TERMINAL, "state": task.state}

    def cancel(self, owner, task_id):
        with self.sessions.begin() as db:
            task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner).with_for_update())
            if task is None:
                raise not_found()
            if task.state not in TERMINAL and not task.cancel_requested:
                task.cancel_requested = True
                state = "cancelled" if task.state == "queued" else "cancelling"
                self._event(db, task, state, task.phase, "Cancelled." if state == "cancelled" else "Stopping further work. An in-flight model call may still use tokens.")
                self._audit(db, owner, task_id, "cancellation_requested")
            return self._task_dto(db, task)

    def list_artifacts(self, owner, limit=100):
        with self.sessions() as db:
            rows = db.scalars(
                select(Artifact)
                .where(
                    Artifact.owner_id == owner,
                    Artifact.task_id.is_not(None),
                    Artifact.artifact_class == "task_output",
                )
                .order_by(Artifact.created_at.desc())
                .limit(limit)
            )
            return [{
                "id": item.id,
                "filename": item.filename,
                "content_type": item.content_type,
                "byte_size": item.byte_size,
                "sha256": item.sha256,
                "created_at": iso(item.created_at),
            } for item in rows]

    def artifact(self, owner, artifact_id):
        with self.sessions.begin() as db:
            item = db.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.owner_id == owner))
            if item is None:
                raise not_found()
            self._audit(db, owner, artifact_id, "artifact_downloaded")
            return {"filename": item.filename, "content_type": item.content_type, "object_key": item.object_key,
                    "byte_size": item.byte_size, "sha256": item.sha256, "artifact_class": item.artifact_class}

    # Below this boundary, calls are made only by the trusted worker/dispatcher.
    def worker_task(self, task_id, check_live=True):
        with self.sessions() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise not_found()
            if check_live:
                self._check_live(task)
            pinned_review = db.get(Step, (task.id, "reviewed_skill_identity"))
            if task.state not in TERMINAL and (
                pinned_review is not None
                or task.workflow_version == REVIEWED_RESEARCH_WORKFLOW_VERSION
                or (
                    self.settings.agent_reviewed_research_skill_enabled
                    and task.agent_run_id is not None
                )
            ):
                # The distinct task version is also rejected by older workers
                # that know only the legacy work_research_v1 workflow.
                if task.agent_run_id is None:
                    raise CoworkerError(
                        "skill_run_scope", "Reviewed task lost its owning Agent run.", 409,
                    )
                invocation = db.scalar(select(ToolInvocation).where(
                    ToolInvocation.run_id == task.agent_run_id,
                    ToolInvocation.step_id == task.agent_step_id,
                    ToolInvocation.owner_id == task.owner_id,
                ))
                if (
                    pinned_review is not None
                    or task.workflow_version in {
                        "work_research_v1", REVIEWED_RESEARCH_WORKFLOW_VERSION,
                    }
                    or (invocation is not None and invocation.tool_name == "research.search")
                ):
                    if task.workflow_version != REVIEWED_RESEARCH_WORKFLOW_VERSION:
                        raise CoworkerError(
                            "skill_run_scope",
                            "Task workflow is not the pinned reviewed research version.",
                            409,
                        )
                    self._reviewed_research_worker_task(db, task)
            documents = []
            for version_id in ([] if task.state in TERMINAL else task.input_versions):
                version = db.get(DocumentVersion, version_id)
                if version is None or version.owner_id != task.owner_id or version.state != "uploaded":
                    raise not_found()
                document = db.get(Document, version.document_id)
                if document.deleted:
                    raise not_found()
                documents.append(self._document_dto(document, version) | {"object_key": version.object_key})
            return {"id": task.id, "owner_id": task.owner_id, "instruction": task.instruction,
                    "workflow_version": task.workflow_version, "skill_id": task_skill_for_version(task.workflow_version).id,
                    "notes": task.notes, "output_language": task.output_language, "documents": documents,
                    "agent_run_id": task.agent_run_id, "agent_step_id": task.agent_step_id,
                    "state": task.state, "deadline_at": iso(task.deadline_at)}

    def _check_live(self, task):
        if task.cancel_requested or task.state == "cancelled":
            raise CoworkerError("task_cancelled", "Task cancelled.", 409)
        if aware(task.deadline_at) <= utcnow():
            raise CoworkerError("task_expired", "The task exceeded its time limit. Please try again.", 409)
        if task.state in TERMINAL:
            raise CoworkerError("task_terminal", "This task has already finished.", 409)

    def begin_phase(self, task_id, phase, message):
        with self.sessions.begin() as db:
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            self._check_live(task)
            completed = db.get(Step, (task_id, phase))
            if completed is not None:
                return completed.output
            if task.phase != phase or task.state != "running":
                self._event(db, task, "running", phase, message)
            return None

    def save_step(self, task_id, phase, output):
        with self.sessions.begin() as db:
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            self._check_live(task)
            existing = db.get(Step, (task_id, phase))
            if existing is None:
                db.add(Step(task_id=task_id, phase=phase, output=output))
            return existing.output if existing else output

    def step(self, task_id, phase):
        with self.sessions() as db:
            item = db.get(Step, (task_id, phase))
            return item.output if item else None

    def reserve_search(self, task_id):
        """At most one paid search per accepted task, including worker loss."""
        with self.sessions.begin() as db:
            existing = db.get(Task, task_id)
            if existing is None:
                raise not_found()
            # The immutable admission record, not a mutable feature flag,
            # determines whether the existing task requires reviewed policy.
            require_review = (
                db.get(Step, (task_id, "reviewed_skill_identity")) is not None
                or existing.workflow_version == REVIEWED_RESEARCH_WORKFLOW_VERSION
                or (
                    self.settings.agent_reviewed_research_skill_enabled
                    and existing.agent_run_id is not None
                )
            )
            if require_review:
                if existing.agent_run_id is None:
                    raise CoworkerError(
                        "skill_run_scope", "Reviewed task lost its owning Agent run.", 409,
                    )
                # Preserve AgentRun -> Task lock order so the credit
                # reservation serializes correctly with grant revocation.
                run = db.scalar(select(AgentRun).where(
                    AgentRun.id == existing.agent_run_id,
                    AgentRun.owner_id == existing.owner_id,
                ).with_for_update())
                if run is None:
                    raise CoworkerError(
                        "skill_run_scope", "The owning Agent run is unavailable.", 409,
                    )
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            self._check_live(task)
            if task.workflow_version not in {"work_research_v1", REVIEWED_RESEARCH_WORKFLOW_VERSION}:
                raise CoworkerError("workflow_version", "This task cannot use web research.")
            if require_review:
                if task.workflow_version != REVIEWED_RESEARCH_WORKFLOW_VERSION:
                    raise CoworkerError(
                        "skill_run_scope", "A reviewed task requires its distinct workflow version.", 409,
                    )
                self._reviewed_research_worker_task(db, task)
            if db.get(Step, (task_id, "search_attempt")):
                raise CoworkerError("search_outcome_unknown", "The previous search could not be recovered. Create a new task to search again.", 409)
            db.add(Step(task_id=task_id, phase="search_attempt", output={
                "provider": self.settings.search_provider, "state": "reserved", "reserved_credits": 1,
                "actual_credits": None, "accounted_credits": 1,
            }))
            self._audit(db, task.owner_id, task_id, "search_budget_reserved")

    def settle_search(self, task_id, state, credits=None):
        with self.sessions.begin() as db:
            row = db.scalar(select(Step).where(Step.task_id == task_id, Step.phase == "search_attempt").with_for_update())
            if row is not None and row.output["state"] == "reserved":
                actual = credits if type(credits) is int and 0 <= credits <= 100 else None
                row.output = row.output | {"state": state, "actual_credits": actual,
                                          "accounted_credits": actual if actual is not None else 1}

    def reserve_model(self, task_id, token_upper_bound):
        owner = self.worker_task(task_id)["owner_id"]
        with self.sessions.begin() as db:
            task_scope = db.get(Task, task_id)
            if task_scope is None:
                raise not_found()
            parent_run = None
            if task_scope.agent_run_id:
                # Keep the same run -> account lock order as AgentRepository.reserve_planner
                # so planner and child-model reservations cannot race past per-run budgets.
                parent_run = db.scalar(
                    select(AgentRun).where(
                        AgentRun.id == task_scope.agent_run_id,
                        AgentRun.owner_id == owner,
                    ).with_for_update()
                )
                if parent_run is None:
                    raise CoworkerError("agent_run_missing", "The parent Agent run no longer exists.", 409)
                if aware(parent_run.deadline_at) <= utcnow():
                    raise CoworkerError(
                        "agent_deadline",
                        "This bounded Agent run reached its task-level deadline.",
                        409,
                    )
            self._account(db, owner)
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            self._check_live(task)
            attempts = db.scalars(select(ModelAttempt).where(ModelAttempt.task_id == task_id)).all()
            if parent_run is not None:
                run_attempts = list(db.scalars(
                    select(ModelAttempt).join(Task, Task.id == ModelAttempt.task_id).where(
                        Task.agent_run_id == parent_run.id,
                    )
                ).all())
                child_calls = len(run_attempts)
                child_tokens = sum(max(0, int(item.charged_tokens or 0)) for item in run_attempts)
                if parent_run.planner_calls + child_calls >= self.settings.max_agent_model_calls_per_run:
                    raise CoworkerError(
                        "agent_model_call_limit",
                        "This Agent run reached its total model-call budget.",
                        429,
                    )
                if parent_run.planner_tokens + child_tokens + token_upper_bound > self.settings.max_agent_tokens_per_run:
                    raise CoworkerError(
                        "agent_token_limit",
                        "This Agent run reached its total token budget.",
                        429,
                    )
                rate = max(0, int(self.settings.agent_v3_planner_cost_microusd_per_1k_tokens))
                estimated_child_cost = (child_tokens * rate + 999) // 1000 if rate else 0
                estimated_next_cost = (max(0, int(token_upper_bound)) * rate + 999) // 1000 if rate else 0
                estimated_planner_cost = (parent_run.planner_tokens * rate + 999) // 1000 if rate else 0
                if (
                    max(int(parent_run.planner_cost_microusd or 0), estimated_planner_cost)
                    + estimated_child_cost
                    + estimated_next_cost
                    > self.settings.max_agent_cost_microusd_per_run
                ):
                    raise CoworkerError(
                        "agent_cost_limit",
                        "This Agent run reached its total model-cost budget.",
                        402,
                    )
            if len(attempts) >= self.settings.max_model_attempts or sum(row.charged_tokens for row in attempts) + token_upper_bound > self.settings.task_token_budget:
                raise CoworkerError("task_budget", "This task reached its model budget. Try a shorter document.", 429)
            day = utcnow().date().isoformat()
            daily = db.get(DailyUsage, (owner, day))
            if daily is None:
                daily = DailyUsage(owner_id=owner, day=day, allocated_tokens=0, task_count=0)
                db.add(daily)
            if daily.allocated_tokens + token_upper_bound > self.settings.daily_token_budget:
                raise CoworkerError("daily_limit", "Your daily coworker model budget has been reached.", 429)
            number = len(attempts) + 1
            acquire_provider_lease(
                db, self.settings, owner_id=owner, kind="draft",
                resource_id=task_id, sequence=number, reserved_tokens=token_upper_bound,
            )
            daily.allocated_tokens += token_upper_bound
            db.add(ModelAttempt(task_id=task_id, attempt=number, owner_id=owner, day=day,
                                reserved_tokens=token_upper_bound, charged_tokens=token_upper_bound,
                                model=self.settings.deepseek_model))
            self._audit(db, owner, task_id, "model_budget_reserved")
            return number

    def settle_model(self, task_id, attempt, actual_tokens, latency_ms, state):
        with self.sessions.begin() as db:
            owner = db.scalar(select(ModelAttempt.owner_id).where(ModelAttempt.task_id == task_id, ModelAttempt.attempt == attempt))
            self._account(db, owner)
            row = db.scalar(select(ModelAttempt).where(ModelAttempt.task_id == task_id, ModelAttempt.attempt == attempt).with_for_update())
            if row.state != "reserved":
                release_provider_lease(
                    db, kind="draft", resource_id=task_id, sequence=attempt,
                )
                return
            # Unknown network outcomes retain the whole reservation; no free retry.
            charged = actual_tokens if isinstance(actual_tokens, int) and not isinstance(actual_tokens, bool) and actual_tokens >= 0 else row.reserved_tokens
            daily = db.get(DailyUsage, (row.owner_id, row.day))
            daily.allocated_tokens += charged - row.charged_tokens
            row.charged_tokens, row.latency_ms, row.state = charged, latency_ms, state
            settle_provider_lease(
                db, kind="draft", resource_id=task_id, sequence=attempt,
                actual_tokens=actual_tokens if state != "unknown" else None,
            )

    def complete(self, task_id, artifacts, needs_input=False):
        owner = self.worker_task(task_id, check_live=False)["owner_id"]
        with self.sessions.begin() as db:
            account = self._account(db, owner)
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            if task.state in {"completed", "needs_input"}:
                return
            self._check_live(task)
            new_bytes = sum(item["byte_size"] for item in artifacts)
            if account.storage_bytes + new_bytes > self.settings.max_account_bytes:
                raise CoworkerError("storage_limit", "Your workspace has reached its file storage limit.", 429)
            for item in artifacts:
                db.add(Artifact(id=str(uuid5(NAMESPACE_URL, task_id + ":" + item["filename"])),
                                task_id=task_id, owner_id=owner, **item))
            account.storage_bytes += new_bytes
            self._event(db, task, "needs_input" if needs_input else "completed", "complete",
                        "Drafts are ready. Review the missing details before using them." if needs_input else "Your drafts and downloads are ready to review.")
            self._audit(db, owner, task_id, "drafts_created")
            self._discard_extracted_text(db, task_id)

    def _discard_extracted_text(self, db, task_id):
        attempt = db.get(Step, (task_id, "search_attempt"))
        if attempt and attempt.output["state"] == "reserved":
            attempt.output = attempt.output | {"state": "unknown"}
        for phase in ("extract", "research"):
            step = db.get(Step, (task_id, phase))
            if step:
                # Retain provenance and short cited evidence, not full extracted pages/files.
                step.output = step.output | {"sources": [{key: value for key, value in source.items() if key != "text"}
                                                        for source in step.output.get("sources", [])]}

    def fail(self, task_id, code, message):
        with self.sessions.begin() as db:
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            if task is None or task.state in TERMINAL:
                return
            cancelled = task.cancel_requested or code == "task_cancelled"
            task.error_code = "task_cancelled" if cancelled else code
            self._event(db, task, "cancelled" if cancelled else "failed", task.phase, "Task cancelled." if cancelled else message[:300])
            self._audit(db, task.owner_id, task_id, "task_cancelled" if cancelled else "task_failed")
            self._discard_extracted_text(db, task_id)

    def claim_outbox(self, limit=10, *, worker_id: str | None = None):
        with self.sessions.begin() as db:
            now = utcnow()
            if worker_id is not None:
                worker = db.scalar(
                    select(WorkerInstance).where(WorkerInstance.id == worker_id).with_for_update()
                )
                cutoff = now - timedelta(seconds=WORKER_HEARTBEAT_TTL_SECONDS)
                if (
                    worker is None
                    or worker.state != "running"
                    or aware(worker.heartbeat_at) < cutoff
                ):
                    return []
                worker.heartbeat_at = now
            rows = db.scalars(select(Outbox).where(Outbox.delivered.is_(False), or_(Outbox.lease_until.is_(None), Outbox.lease_until < now)).limit(limit).with_for_update(skip_locked=True)).all()
            for row in rows:
                row.lease_until = now + timedelta(seconds=30)
                row.attempts += 1
            return [row.task_id for row in rows]

    def delivered(self, task_id):
        with self.sessions.begin() as db:
            row = db.get(Outbox, task_id)
            if row:
                row.delivered = True

    def expire_tasks(self, owner=None):
        with self.sessions() as db:
            query = select(Task.id).where(Task.state.not_in(TERMINAL), Task.deadline_at < utcnow())
            if owner is not None:
                query = query.where(Task.owner_id == owner)
            ids = list(db.scalars(query.limit(100)))
        for task_id in ids:
            self.fail(task_id, "task_expired", "The task exceeded its time limit. Please try again.")

    def expired_uploads(self):
        """Reclaim abandoned reservations; keep tombstones for repeatable cleanup."""
        with self.sessions() as db:
            ids = list(db.scalars(select(DocumentVersion.id).join(Document, Document.id == DocumentVersion.document_id).where(
                or_(DocumentVersion.state.in_(["awaiting_upload", "expired"]), Document.deleted.is_(True)),
                DocumentVersion.state != "purged",
                DocumentVersion.expires_at < utcnow() - timedelta(minutes=2),
            ).order_by(DocumentVersion.expires_at).limit(100)))
        keys = []
        for version_id in ids:
            with self.sessions.begin() as db:
                owner = db.scalar(select(DocumentVersion.owner_id).where(DocumentVersion.id == version_id))
                account = self._account(db, owner)
                version = db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id).with_for_update())
                document = db.get(Document, version.document_id)
                if version.state == "uploaded" and not document.deleted:
                    continue
                if version.state != "expired":
                    account.storage_bytes -= version.byte_size
                    version.state = "expired"
                    document.deleted = True
                keys.append(version.object_key)
        return keys

    def upload_cleaned(self, key):
        with self.sessions.begin() as db:
            row = db.scalar(select(DocumentVersion).where(DocumentVersion.object_key == key, DocumentVersion.state == "expired").with_for_update())
            if row:
                row.state = "purged"
