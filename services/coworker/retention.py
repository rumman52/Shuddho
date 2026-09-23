from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select

from .errors import CoworkerError
from .models import (
    Account, ActionProposal, AgentEvent, AgentOutbox, AgentRun, AgentStep, Artifact, AuditEvent,
    Connection, DailyUsage, Document, DocumentVersion, ExternalAction, MemoryFact,
    ModelAttempt, OAuthAttempt, Outbox, Step, Task, TaskEvent, ToolInvocation,
    ToolReceipt, Workspace, utcnow,
)

TERMINAL_TASKS = {"completed", "failed", "cancelled", "needs_input"}
TERMINAL_AGENT_RUNS = {"completed", "failed", "cancelled"}
TERMINAL_ACTIONS = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}


class RetentionService:
    """Administrative retention/erasure operations.

    This service is intentionally not mounted as a public end-user endpoint.
    Operators/scripts must explicitly choose the owned task/account being erased.
    """

    def __init__(self, sessions, storage):
        self.sessions = sessions
        self.storage = storage

    @staticmethod
    def _step_object_keys(rows: list[Step]) -> set[str]:
        keys: set[str] = set()
        for row in rows:
            output = row.output or {}
            for item in output.get("artifacts", []):
                if isinstance(item, dict) and isinstance(item.get("object_key"), str):
                    keys.add(item["object_key"])
        return keys

    def referenced_object_keys(self) -> set[str]:
        with self.sessions() as db:
            keys = set(db.scalars(select(DocumentVersion.object_key)))
            keys.update(db.scalars(select(Artifact.object_key)))
            keys.update(self._step_object_keys(list(db.scalars(select(Step)).all())))
            return {key for key in keys if isinstance(key, str) and key}

    def erase_task(self, owner: str, task_id: str) -> dict:
        with self.sessions.begin() as db:
            task = db.scalar(select(Task).where(
                Task.id == task_id, Task.owner_id == owner,
            ).with_for_update())
            if task is None:
                raise CoworkerError("not_found", "This item was not found in your workspace.", 404)
            if task.state not in TERMINAL_TASKS:
                raise CoworkerError("task_active", "Cancel or finish this task before erasing it.", 409)
            if task.agent_run_id is not None:
                raise CoworkerError("agent_task_erasure", "Erase the owning account to remove tasks attached to an agent run.", 409)

            artifacts = list(db.scalars(select(Artifact).where(
                Artifact.task_id == task_id, Artifact.owner_id == owner,
            )).all())
            steps = list(db.scalars(select(Step).where(Step.task_id == task_id)).all())
            object_keys = {item.object_key for item in artifacts}
            object_keys.update(self._step_object_keys(steps))

            db.execute(delete(Artifact).where(Artifact.task_id == task_id, Artifact.owner_id == owner))
            db.execute(delete(ModelAttempt).where(ModelAttempt.task_id == task_id, ModelAttempt.owner_id == owner))
            db.execute(delete(Step).where(Step.task_id == task_id))
            db.execute(delete(TaskEvent).where(TaskEvent.task_id == task_id))
            db.execute(delete(Outbox).where(Outbox.task_id == task_id))
            db.execute(delete(AuditEvent).where(AuditEvent.owner_id == owner, AuditEvent.resource_id == task_id))
            db.delete(task)

        deleted, failed = self._delete_objects(object_keys)
        return {"task_id": task_id, "database_erased": True, "objects_deleted": deleted, "objects_failed": failed}

    def erase_account(self, owner: str) -> dict:
        with self.sessions.begin() as db:
            account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
            if account is None:
                raise CoworkerError("not_found", "This item was not found in your workspace.", 404)

            active_tasks = db.scalar(select(Task.id).where(
                Task.owner_id == owner, Task.state.not_in(TERMINAL_TASKS),
            ).limit(1))
            active_runs = db.scalar(select(AgentRun.id).where(
                AgentRun.owner_id == owner, AgentRun.state.not_in(TERMINAL_AGENT_RUNS),
            ).limit(1))
            active_actions = db.scalar(select(ExternalAction.id).where(
                ExternalAction.owner_id == owner, ExternalAction.state.not_in(TERMINAL_ACTIONS),
            ).limit(1))
            if active_tasks or active_runs or active_actions:
                raise CoworkerError("account_active", "Cancel or finish active coworker work before erasing this account.", 409)

            documents = list(db.scalars(select(DocumentVersion).where(DocumentVersion.owner_id == owner)).all())
            artifacts = list(db.scalars(select(Artifact).where(Artifact.owner_id == owner)).all())
            owned_task_ids = list(db.scalars(select(Task.id).where(Task.owner_id == owner)).all())
            steps = list(db.scalars(select(Step).where(Step.task_id.in_(owned_task_ids))).all()) if owned_task_ids else []
            object_keys = {item.object_key for item in documents}
            object_keys.update(item.object_key for item in artifacts)
            object_keys.update(self._step_object_keys(steps))

            run_ids = list(db.scalars(select(AgentRun.id).where(AgentRun.owner_id == owner)).all())
            step_ids = list(db.scalars(select(AgentStep.id).where(AgentStep.owner_id == owner)).all())

            db.execute(delete(ActionProposal).where(ActionProposal.owner_id == owner))
            db.execute(delete(ToolReceipt).where(ToolReceipt.owner_id == owner))
            db.execute(delete(ToolInvocation).where(ToolInvocation.owner_id == owner))
            db.execute(delete(AgentEvent).where(AgentEvent.owner_id == owner))
            if run_ids:
                db.execute(delete(AgentOutbox).where(AgentOutbox.run_id.in_(run_ids)))
            db.execute(delete(AgentStep).where(AgentStep.owner_id == owner))
            db.execute(delete(AgentRun).where(AgentRun.owner_id == owner))

            db.execute(delete(Artifact).where(Artifact.owner_id == owner))
            db.execute(delete(ModelAttempt).where(ModelAttempt.owner_id == owner))
            if owned_task_ids:
                db.execute(delete(Step).where(Step.task_id.in_(owned_task_ids)))
                db.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(owned_task_ids)))
                db.execute(delete(Outbox).where(Outbox.task_id.in_(owned_task_ids)))
            db.execute(delete(Task).where(Task.owner_id == owner))

            db.execute(delete(DocumentVersion).where(DocumentVersion.owner_id == owner))
            db.execute(delete(Document).where(Document.owner_id == owner))
            db.execute(delete(MemoryFact).where(MemoryFact.owner_id == owner))
            db.execute(delete(ExternalAction).where(ExternalAction.owner_id == owner))
            db.execute(delete(OAuthAttempt).where(OAuthAttempt.owner_id == owner))
            db.execute(delete(Connection).where(Connection.owner_id == owner))
            db.execute(delete(DailyUsage).where(DailyUsage.owner_id == owner))
            db.execute(delete(AuditEvent).where(AuditEvent.owner_id == owner))
            db.execute(delete(Workspace).where(Workspace.owner_id == owner))
            db.delete(account)

        deleted, failed = self._delete_objects(object_keys)
        return {"owner_id": owner, "database_erased": True, "objects_deleted": deleted, "objects_failed": failed}

    def _delete_objects(self, keys: set[str]) -> tuple[int, list[str]]:
        deleted = 0
        failed: list[str] = []
        for key in sorted(keys):
            try:
                self.storage.delete(key)
                deleted += 1
            except Exception:
                failed.append(key)
        return deleted, failed

    def orphan_candidates(self, *, prefix: str = "", min_age_seconds: int = 3600) -> list[dict]:
        cutoff = utcnow() - timedelta(seconds=max(300, min_age_seconds))
        referenced = self.referenced_object_keys()
        result = []
        for item in self.storage.inventory(prefix):
            if item.key in referenced or item.modified_at > cutoff:
                continue
            result.append({
                "key": item.key,
                "byte_size": item.byte_size,
                "modified_at": item.modified_at.isoformat(),
            })
        return result

    def cleanup_orphans(self, *, prefix: str = "", min_age_seconds: int = 3600, dry_run: bool = True) -> dict:
        candidates = self.orphan_candidates(prefix=prefix, min_age_seconds=min_age_seconds)
        if dry_run:
            return {"dry_run": True, "candidates": candidates, "deleted": 0, "failed": []}
        failed: list[str] = []
        deleted = 0
        for item in candidates:
            try:
                self.storage.delete(item["key"])
                deleted += 1
            except Exception:
                failed.append(item["key"])
        return {"dry_run": False, "candidates": candidates, "deleted": deleted, "failed": failed}
