from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from .agent_schemas import AgentPlanStep, AgentRunCreate
from .agent_tools import available_tools, tool
from .config import Settings
from .errors import CoworkerError
from .models import Account, AgentEvent, AgentRun, AgentStep, AuditEvent, Document, DocumentVersion, ExternalAction, ToolInvocation, ToolReceipt, Workspace, utcnow
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

    def _event(self, db, run: AgentRun, state: str, phase: str, message: str):
        run.state = state
        run.phase = phase
        run.message = message
        run.updated_at = utcnow()
        run.event_sequence += 1
        db.add(AgentEvent(run_id=run.id, sequence=run.event_sequence, owner_id=run.owner_id,
                          state=state, phase=phase, message=message))

    def _run(self, db, owner: str, run_id: str, lock: bool = False) -> AgentRun:
        query = select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_id == owner)
        if lock:
            query = query.with_for_update()
        value = db.scalar(query)
        if value is None:
            raise not_found()
        return value

    def _run_document_ids(self, db, run: AgentRun) -> set[str]:
        if not run.input_versions:
            return set()
        return set(db.scalars(select(DocumentVersion.document_id).where(
            DocumentVersion.id.in_(run.input_versions), DocumentVersion.owner_id == run.owner_id,
        )))

    def create(self, owner: str, request: AgentRunCreate, idempotency_key: str) -> tuple[dict, bool]:
        if not self.settings.agent_runtime_enabled:
            raise CoworkerError("agent_runtime_unavailable", "Agent runs are not enabled in this workspace yet.", 409)
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as db:
            if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
                raise not_found()
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
            self._event(db, run, "queued", "planning", "Agent run created. Waiting for the bounded planner runtime.")
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
            "event_sequence": run.event_sequence,
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
            return self._dto(db, self._run(db, owner, run_id))

    def events(self, owner: str, run_id: str, after: int = 0) -> dict:
        with self.sessions() as db:
            run = self._run(db, owner, run_id)
            rows = db.scalars(select(AgentEvent).where(
                AgentEvent.run_id == run.id, AgentEvent.owner_id == owner, AgentEvent.sequence > after,
            ).order_by(AgentEvent.sequence).limit(100)).all()
            return {
                "events": [{
                    "sequence": item.sequence,
                    "state": item.state,
                    "phase": item.phase,
                    "message": item.message,
                    "created_at": iso(item.created_at),
                } for item in rows],
                "terminal": run.state in {"completed", "failed", "cancelled"},
                "sequence": run.event_sequence,
            }

    def save_plan(self, owner: str, run_id: str, steps: list[AgentPlanStep]) -> dict:
        if not 1 <= len(steps) <= 8:
            raise CoworkerError("invalid_plan", "An agent plan must contain between one and eight steps.", 422)
        with self.sessions.begin() as db:
            run = self._run(db, owner, run_id, lock=True)
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            existing = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run.id, ToolInvocation.owner_id == owner,
            ))
            if existing:
                raise CoworkerError("plan_already_saved", "This agent run already has a saved plan.", 409)
            run_docs = self._run_document_ids(db, run)
            placeholder = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.owner_id == owner, AgentStep.ordinal == 0,
            ))
            if placeholder is not None:
                db.delete(placeholder)
                db.flush()
            for ordinal, planned in enumerate(steps, 1):
                spec = tool(planned.tool)
                if not spec.enabled(self.settings):
                    raise CoworkerError("tool_unavailable", "A required agent tool is not enabled.", 409)
                validated = spec.validate(planned.arguments)
                if hasattr(validated, "document_ids"):
                    requested = {str(value) for value in validated.document_ids}
                    if not requested.issubset(run_docs):
                        raise CoworkerError("tool_source_scope", "An agent tool can use only sources attached to this run.", 409)
                if spec.kind == "approved_action":
                    action = db.scalar(select(ExternalAction).where(
                        ExternalAction.id == str(validated.action_id), ExternalAction.owner_id == owner,
                    ))
                    expected = "email_send" if spec.capability == "email" else "calendar_create"
                    if action is None or action.kind != expected:
                        raise CoworkerError("action_scope", "The approved action is not available to this agent run.", 409)
                step = AgentStep(
                    id=str(uuid4()), run_id=run.id, owner_id=owner, ordinal=ordinal,
                    tool_name=spec.name, state="planned",
                    input={"arguments": validated.model_dump(mode="json")}, output={},
                )
                db.add(step)
                db.flush()
                db.add(ToolInvocation(
                    id=str(uuid4()), run_id=run.id, step_id=step.id, owner_id=owner,
                    tool_name=spec.name, tool_version=spec.version,
                    arguments=validated.model_dump(mode="json"), state="prepared",
                    consequential=spec.consequential, approval_required=spec.approval_required,
                ))
            self._event(db, run, "planning", "planned", f"Plan saved with {len(steps)} bounded steps.")
            self._audit(db, owner, run.id, "agent_plan_saved")
            return self._dto(db, run)

    def list(self, owner: str) -> list[dict]:
        with self.sessions() as db:
            rows = db.scalars(select(AgentRun).where(
                AgentRun.owner_id == owner,
            ).order_by(AgentRun.created_at.desc()).limit(30))
            return [self._dto(db, row) for row in rows]

    def cancel(self, owner: str, run_id: str) -> dict:
        with self.sessions.begin() as db:
            run = self._run(db, owner, run_id, lock=True)
            if run.state in {"completed", "failed", "cancelled"}:
                return self._dto(db, run)
            run.cancel_requested = True
            for step in db.scalars(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.owner_id == owner,
                AgentStep.state.in_({"queued", "planned"}),
            )):
                step.state = "cancelled"
                step.finished_at = utcnow()
            self._event(db, run, "cancelled", "cancelled", "Agent run cancelled.")
            self._audit(db, owner, run.id, "agent_run_cancelled")
            return self._dto(db, run)

    def tools(self) -> list[dict]:
        if not self.settings.agent_runtime_enabled:
            return []
        return available_tools(self.settings)
