from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from .auth import Principal
from .config import Settings
from .errors import CoworkerError
from .models import Account, Artifact, AuditEvent, DailyUsage, Document, DocumentVersion, ModelAttempt, Outbox, Step, Task, TaskEvent, Workspace, utcnow
from .schemas import TaskCreate, UploadRequest
from .skills import ARTIFACT_SKILLS, SKILLS, skill_for_version

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
            account.preferences = preferences
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

    def create_task(self, owner: str, request: TaskCreate, idempotency_key: str) -> tuple[dict, bool]:
        self.expire_tasks(owner)
        payload = request.model_dump(mode="json")
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
                return self._task_dto(db, previous), False
            enabled = (self.settings.artifact_services_enabled if request.skill_id in ARTIFACT_SKILLS
                       else self.settings.work_services_enabled or request.skill_id == "report_email")
            if not enabled:
                raise CoworkerError("service_unavailable", "This work service is not available yet. Please choose another service.", 409)
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
            task = Task(id=str(uuid4()), owner_id=owner, workspace_id=self._workspace(db, owner),
                        idempotency_key=idempotency_key, fingerprint=fingerprint, instruction=request.instruction,
                        notes=request.notes, output_language=request.output_language, input_versions=versions,
                        workflow_version=SKILLS[request.skill_id].version,
                        deadline_at=utcnow() + timedelta(seconds=self.settings.task_timeout_seconds))
            db.add(task)
            db.flush()
            usage.task_count += 1
            db.add(Outbox(task_id=task.id))
            self._event(db, task, "queued", "queued", "Queued for your coworker.")
            self._audit(db, owner, task.id, "task_created")
            return self._task_dto(db, task), True

    def _task_dto(self, db, task, detail=True):
        artifacts = db.scalars(select(Artifact).where(Artifact.task_id == task.id, Artifact.owner_id == task.owner_id)).all()
        draft_step = db.get(Step, (task.id, "draft")) if detail else None
        usage = db.scalars(select(ModelAttempt).where(ModelAttempt.task_id == task.id)).all()
        return {"id": task.id, "state": task.state, "phase": task.phase, "message": task.message,
                "error_code": task.error_code, "output_language": task.output_language,
                "skill_id": skill_for_version(task.workflow_version).id, "workflow_version": task.workflow_version,
                "instruction": task.instruction, "created_at": iso(task.created_at), "updated_at": iso(task.updated_at),
                "event_sequence": task.event_sequence, "cancel_requested": task.cancel_requested,
                "artifacts": [{"id": item.id, "filename": item.filename, "content_type": item.content_type,
                               "byte_size": item.byte_size, "sha256": item.sha256} for item in artifacts],
                "draft": draft_step.output.get("draft") if draft_step else None,
                "preview": draft_step.output.get("preview") if draft_step else None,
                "sources": draft_step.output.get("sources", []) if draft_step else [],
                "input": {"notes": task.notes, "document_ids": list(db.scalars(select(DocumentVersion.document_id).where(
                    DocumentVersion.id.in_(task.input_versions), DocumentVersion.owner_id == task.owner_id,
                )))} if detail else None,
                "usage": {"model_attempts": len(usage), "accounted_tokens": sum(item.charged_tokens for item in usage)}}

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

    def artifact(self, owner, artifact_id):
        with self.sessions.begin() as db:
            item = db.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.owner_id == owner))
            if item is None:
                raise not_found()
            self._audit(db, owner, artifact_id, "artifact_downloaded")
            return {"filename": item.filename, "content_type": item.content_type, "object_key": item.object_key,
                    "byte_size": item.byte_size, "sha256": item.sha256}

    # Below this boundary, calls are made only by the trusted worker/dispatcher.
    def worker_task(self, task_id, check_live=True):
        with self.sessions() as db:
            task = db.get(Task, task_id)
            if task is None:
                raise not_found()
            if check_live:
                self._check_live(task)
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
                    "workflow_version": task.workflow_version, "skill_id": skill_for_version(task.workflow_version).id,
                    "notes": task.notes, "output_language": task.output_language, "documents": documents,
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

    def reserve_model(self, task_id, token_upper_bound):
        owner = self.worker_task(task_id)["owner_id"]
        with self.sessions.begin() as db:
            self._account(db, owner)
            task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
            self._check_live(task)
            attempts = db.scalars(select(ModelAttempt).where(ModelAttempt.task_id == task_id)).all()
            if len(attempts) >= self.settings.max_model_attempts or sum(row.charged_tokens for row in attempts) + token_upper_bound > self.settings.task_token_budget:
                raise CoworkerError("task_budget", "This task reached its model budget. Try a shorter document.", 429)
            day = utcnow().date().isoformat()
            daily = db.get(DailyUsage, (owner, day))
            if daily is None:
                daily = DailyUsage(owner_id=owner, day=day, allocated_tokens=0, task_count=0)
                db.add(daily)
            if daily.allocated_tokens + token_upper_bound > self.settings.daily_token_budget:
                raise CoworkerError("daily_limit", "Your daily coworker model budget has been reached.", 429)
            daily.allocated_tokens += token_upper_bound
            number = len(attempts) + 1
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
                return
            # Unknown network outcomes retain the whole reservation; no free retry.
            charged = actual_tokens if isinstance(actual_tokens, int) and not isinstance(actual_tokens, bool) and actual_tokens >= 0 else row.reserved_tokens
            daily = db.get(DailyUsage, (row.owner_id, row.day))
            daily.allocated_tokens += charged - row.charged_tokens
            row.charged_tokens, row.latency_ms, row.state = charged, latency_ms, state

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
        step = db.get(Step, (task_id, "extract"))
        if step:
            # Finished tasks keep provenance, original pasted notes, and drafts.
            # The extra full-text copy of uploaded files is no longer needed.
            step.output = {"sources": [{key: value for key, value in source.items() if key != "text"}
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

    def claim_outbox(self, limit=10):
        with self.sessions.begin() as db:
            now = utcnow()
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
