from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from .agent_schemas import AgentRunCreate
from .agent_tools import available_tools
from .config import Settings
from .errors import CoworkerError
from .models import AgentRun, AgentStep, AuditEvent, Document, DocumentVersion, ToolInvocation, ToolReceipt, Workspace, utcnow
from .repository import iso, not_found

ACTIVE_RUN_STATES = {"queued", "planning", "running", "awaiting_approval"}


class AgentRepository:
    """Owned durable ledger for agent runs.

    This foundation release persists goals and execution records but deliberately
    does not start an autonomous planner. Later runtimes must write through this
    ledger and the server-owned tool registry.
    """

    def __init__(self, sessions, settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def _workspace(self, db, owner: str) -> str:
        value = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
        if value is None:
            raise not_found()
        return value

    def _audit(self, db, owner: str, resource: str, action: str):
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    def create(self, owner: str, request: AgentRunCreate, idempotency_key: str) -> tuple[dict, bool]:
        if not self.settings.agent_runtime_enabled:
            raise CoworkerError("agent_runtime_unavailable", "Agent runs are not enabled in this workspace yet.", 409)
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as db:
            previous = db.scalar(select(AgentRun).where(
                AgentRun.owner_id == owner, AgentRun.idempotency_key == idempotency_key,
            ))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to a different agent goal.", 409)
                return self._dto(db, previous), False

            active = db.scalar(select(func.count()).select_from(AgentRun).where(
                AgentRun.owner_id == owner, AgentRun.state.in_(ACTIVE_RUN_STATES),
            ))
            if active >= self.settings.max_active_agent_runs:
                raise CoworkerError("active_agent_limit", "Your coworker already has the maximum active agent runs.", 429)

            versions: list[str] = []
            for document_id in request.document_ids:
                row = db.execute(select(DocumentVersion, Document).join(
                    Document, DocumentVersion.document_id == Document.id,
                ).where(
                    Document.id == str(document_id),
                    Document.owner_id == owner,
                    Document.deleted.is_(False),
                    DocumentVersion.owner_id == owner,
                    DocumentVersion.state == "uploaded",
                )).first()
                if row is None:
                    raise not_found()
                versions.append(row[0].id)

            now = utcnow()
            run = AgentRun(
                id=str(uuid4()),
                owner_id=owner,
                workspace_id=self._workspace(db, owner),
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                goal=request.goal,
                output_language=request.output_language,
                input_versions=versions,
                state="queued",
                phase="planning",
                message="Agent run created. Waiting for the bounded planner runtime.",
                deadline_at=now + timedelta(seconds=self.settings.agent_run_timeout_seconds),
            )
            db.add(run)
            db.flush()
            db.add(AgentStep(
                id=str(uuid4()), run_id=run.id, owner_id=owner, ordinal=0,
                tool_name=None, state="queued",
                input={"kind": "goal", "output_language": request.output_language},
                output={},
            ))
            self._audit(db, owner, run.id, "agent_run_created")
            return self._dto(db, run), True

    def _dto(self, db, run: AgentRun) -> dict:
        steps = db.scalars(select(AgentStep).where(
            AgentStep.run_id == run.id, AgentStep.owner_id == run.owner_id,
        ).order_by(AgentStep.ordinal)).all()
        invocations = db.scalars(select(ToolInvocation).where(
            ToolInvocation.run_id == run.id, ToolInvocation.owner_id == run.owner_id,
        ).order_by(ToolInvocation.created_at)).all()
        receipts = db.scalars(select(ToolReceipt).where(
            ToolReceipt.run_id == run.id, ToolReceipt.owner_id == run.owner_id,
        )).all()
        receipt_by_invocation = {item.invocation_id: item for item in receipts}
        documents = list(db.scalars(select(DocumentVersion.document_id).where(
            DocumentVersion.id.in_(run.input_versions), DocumentVersion.owner_id == run.owner_id,
        ))) if run.input_versions else []
        return {
            "id": run.id,
            "goal": run.goal,
            "output_language": run.output_language,
            "document_ids": documents,
            "state": run.state,
            "phase": run.phase,
            "message": run.message,
            "error_code": run.error_code,
            "cancel_requested": run.cancel_requested,
            "created_at": iso(run.created_at),
            "updated_at": iso(run.updated_at),
            "deadline_at": iso(run.deadline_at),
            "steps": [{
                "id": step.id,
                "ordinal": step.ordinal,
                "tool": step.tool_name,
                "state": step.state,
                "error_code": step.error_code,
            } for step in steps],
            "tool_invocations": [{
                "id": item.id,
                "step_id": item.step_id,
                "tool": item.tool_name,
                "version": item.tool_version,
                "state": item.state,
                "consequential": item.consequential,
                "approval_required": item.approval_required,
                "receipt": ({
                    "status": receipt_by_invocation[item.id].status,
                    "resource_type": receipt_by_invocation[item.id].resource_type,
                    "resource_id": receipt_by_invocation[item.id].resource_id,
                    "summary": receipt_by_invocation[item.id].summary,
                    "created_at": iso(receipt_by_invocation[item.id].created_at),
                } if item.id in receipt_by_invocation else None),
            } for item in invocations],
        }

    def get(self, owner: str, run_id: str) -> dict:
        with self.sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_id == owner))
            if run is None:
                raise not_found()
            return self._dto(db, run)

    def list(self, owner: str) -> list[dict]:
        with self.sessions() as db:
            rows = db.scalars(select(AgentRun).where(
                AgentRun.owner_id == owner,
            ).order_by(AgentRun.created_at.desc()).limit(30))
            return [self._dto(db, row) for row in rows]

    def cancel(self, owner: str, run_id: str) -> dict:
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(
                AgentRun.id == run_id, AgentRun.owner_id == owner,
            ).with_for_update())
            if run is None:
                raise not_found()
            if run.state in {"completed", "failed", "cancelled"}:
                return self._dto(db, run)
            run.cancel_requested = True
            run.state = "cancelled"
            run.phase = "cancelled"
            run.message = "Agent run cancelled."
            run.updated_at = utcnow()
            for step in db.scalars(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.owner_id == owner,
                AgentStep.state.in_({"queued", "planned"}),
            )):
                step.state = "cancelled"
                step.finished_at = utcnow()
            self._audit(db, owner, run.id, "agent_run_cancelled")
            return self._dto(db, run)

    def tools(self) -> list[dict]:
        if not self.settings.agent_runtime_enabled:
            return []
        return available_tools(self.settings)
