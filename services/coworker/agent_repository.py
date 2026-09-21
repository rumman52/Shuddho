from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select

from .agent_schemas import AgentPlanStep, AgentRunCreate
from .agent_tools import available_tools, tool
from .config import Settings
from .errors import CoworkerError
from .models import Account, AgentEvent, AgentOutbox, AgentRun, AgentStep, AuditEvent, DailyUsage, Document, DocumentVersion, ExternalAction, Task, ToolInvocation, ToolReceipt, Workspace, utcnow
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
        if request.memory_namespaces and not self.settings.agent_memory_enabled:
            raise CoworkerError("agent_memory_unavailable", "Structured memory is not enabled in this workspace yet.", 409)
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

            run_id = str(uuid4())
            action_ids: list[str] = []
            if request.action_ids and not self.settings.actions_enabled:
                raise CoworkerError("actions_disabled", "Email and calendar actions are not available in this deployment.", 503)
            for action_id in request.action_ids:
                action = db.scalar(select(ExternalAction).where(
                    ExternalAction.id == str(action_id), ExternalAction.owner_id == owner,
                ))
                if action is None:
                    raise not_found()
                if action.state != "awaiting_approval":
                    raise CoworkerError("action_not_awaiting_approval", "Attach only actions that are still awaiting your approval.", 409)
                if action.agent_run_id is not None:
                    raise CoworkerError("action_already_bound", "This action is already attached to another agent run.", 409)
                action.agent_run_id = run_id
                action.agent_ready = False
                action_ids.append(action.id)

            now = utcnow()
            run = AgentRun(
                id=run_id,
                owner_id=owner,
                workspace_id=self._workspace(db, owner),
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                goal=request.goal,
                output_language=request.output_language,
                input_versions=versions,
                action_ids=action_ids,
                memory_namespaces=list(request.memory_namespaces),
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
            db.add(AgentOutbox(run_id=run.id))
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
            "action_ids": list(run.action_ids),
            "memory_namespaces": list(run.memory_namespaces),
            "state": run.state,
            "phase": run.phase,
            "message": run.message,
            "error_code": run.error_code,
            "cancel_requested": run.cancel_requested,
            "event_sequence": run.event_sequence,
            "planner_calls": run.planner_calls,
            "planner_tokens": run.planner_tokens,
            "planner_mode": run.planner_mode,
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

    def reserve_planner(self, run_id: str, reserve_tokens: int) -> dict:
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            if run.planner_calls >= self.settings.max_agent_planner_calls:
                raise CoworkerError("planner_call_limit", "This agent run reached its planner call limit.", 429)
            if reserve_tokens < 1 or run.planner_tokens + reserve_tokens > self.settings.agent_planner_token_budget:
                raise CoworkerError("planner_budget", "This agent run reached its planner token budget.", 429)
            if db.scalar(select(Account.id).where(Account.id == run.owner_id).with_for_update()) is None:
                raise not_found()
            day = utcnow().date().isoformat()
            daily = db.get(DailyUsage, (run.owner_id, day))
            if daily is None:
                daily = DailyUsage(owner_id=run.owner_id, day=day, allocated_tokens=0, task_count=0)
                db.add(daily)
            if daily.allocated_tokens + reserve_tokens > self.settings.daily_token_budget:
                raise CoworkerError("daily_limit", "Your daily coworker model budget has been reached.", 429)
            daily.allocated_tokens += reserve_tokens
            run.planner_calls += 1
            run.planner_tokens += reserve_tokens
            run.planner_mode = "intelligent"
            self._audit(db, run.owner_id, run.id, "agent_planner_budget_reserved")
            return {"call": run.planner_calls, "reserved_tokens": reserve_tokens, "day": day}

    def set_planner_mode(self, run_id: str, mode: str):
        if mode not in {"deterministic", "intelligent", "fallback", "replanned"}:
            raise CoworkerError("planner_mode", "Unsupported planner mode.", 422)
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            run.planner_mode = mode
            run.updated_at = utcnow()

    def replace_remaining_plan(self, owner: str, run_id: str, from_ordinal: int,
                               steps: list[AgentPlanStep]) -> dict:
        if not 1 <= len(steps) <= 8 or from_ordinal - 1 + len(steps) > 8:
            raise CoworkerError("invalid_plan", "An agent plan must contain at most eight total steps.", 422)
        with self.sessions.begin() as db:
            run = self._run(db, owner, run_id, lock=True)
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            if from_ordinal < 1:
                raise CoworkerError("invalid_replan", "The replan boundary is invalid.", 422)
            prior = db.scalars(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal < from_ordinal,
            )).all()
            if any(step.state != "completed" for step in prior):
                raise CoworkerError("invalid_replan", "Only completed steps may precede a replan.", 409)
            remaining_steps = db.scalars(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal >= from_ordinal,
            ).order_by(AgentStep.ordinal).with_for_update()).all()
            for step in remaining_steps:
                invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.step_id == step.id).with_for_update())
                if invocation is not None and invocation.state not in {"prepared"}:
                    raise CoworkerError("replan_started_step", "A started agent step cannot be replaced.", 409)
                if invocation is not None:
                    db.delete(invocation)
                db.delete(step)
            db.flush()
            run_docs = self._run_document_ids(db, run)
            for offset, planned in enumerate(steps):
                ordinal = from_ordinal + offset
                spec = tool(planned.tool)
                if not spec.enabled(self.settings):
                    raise CoworkerError("tool_unavailable", "A required agent tool is not enabled.", 409)
                validated = spec.validate(planned.arguments)
                if hasattr(validated, "document_ids"):
                    requested = {str(value) for value in validated.document_ids}
                    if not requested.issubset(run_docs):
                        raise CoworkerError("tool_source_scope", "An agent tool can use only sources attached to this run.", 409)
                if spec.kind == "approved_action":
                    if str(validated.action_id) not in set(run.action_ids):
                        raise CoworkerError("action_scope", "This action was not attached to the agent run.", 409)
                    action = db.scalar(select(ExternalAction).where(
                        ExternalAction.id == str(validated.action_id), ExternalAction.owner_id == owner,
                    ))
                    expected = "email_send" if spec.capability == "email" else "calendar_create"
                    if action is None or action.kind != expected or action.agent_run_id != run.id:
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
            self._event(db, run, "planning", "replanned", f"Plan updated from step {from_ordinal}.")
            self._audit(db, owner, run.id, "agent_plan_replanned")
            return self._dto(db, run)

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
                    if str(validated.action_id) not in set(run.action_ids):
                        raise CoworkerError("action_scope", "This action was not attached to the agent run.", 409)
                    action = db.scalar(select(ExternalAction).where(
                        ExternalAction.id == str(validated.action_id), ExternalAction.owner_id == owner,
                    ))
                    expected = "email_send" if spec.capability == "email" else "calendar_create"
                    if action is None or action.kind != expected or action.agent_run_id != run.id:
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
                AgentStep.state.in_({"queued", "planned", "running", "awaiting_approval"}),
            )):
                if step.output.get("resource_type") == "action":
                    action_row = db.scalar(select(ExternalAction).where(
                        ExternalAction.id == step.output.get("resource_id"), ExternalAction.owner_id == owner,
                    ).with_for_update())
                    if action_row is not None and action_row.state in {"awaiting_approval", "queued"}:
                        action_row.state, action_row.finished_at = "cancelled", utcnow()
                        self._audit(db, owner, action_row.id, "action.cancelled_agent")
                if step.state == "running" and step.output.get("resource_type") == "task":
                    task_row = db.scalar(select(Task).where(
                        Task.id == step.output.get("resource_id"), Task.owner_id == owner,
                    ).with_for_update())
                    if task_row is not None and task_row.state not in {"completed", "failed", "cancelled", "needs_input"}:
                        task_row.cancel_requested = True
                step.state = "cancelled"
                step.finished_at = utcnow()
            self._event(db, run, "cancelled", "cancelled", "Agent run cancelled.")
            self._audit(db, owner, run.id, "agent_run_cancelled")
            return self._dto(db, run)

    def tools(self) -> list[dict]:
        if not self.settings.agent_runtime_enabled:
            return []
        return available_tools(self.settings)


    # Trusted worker/dispatcher boundary.
    def claim_outbox(self, limit: int = 10) -> list[str]:
        with self.sessions.begin() as db:
            now = utcnow()
            rows = db.scalars(select(AgentOutbox).where(
                AgentOutbox.delivered.is_(False),
                or_(AgentOutbox.lease_until.is_(None), AgentOutbox.lease_until < now),
            ).limit(limit).with_for_update(skip_locked=True)).all()
            for row in rows:
                row.lease_until = now + timedelta(seconds=30)
                row.attempts += 1
            return [row.run_id for row in rows]

    def delivered(self, run_id: str):
        with self.sessions.begin() as db:
            row = db.get(AgentOutbox, run_id)
            if row is not None:
                row.delivered = True

    def worker_run(self, run_id: str) -> dict:
        with self.sessions() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                raise not_found()
            documents = list(db.scalars(select(DocumentVersion.document_id).where(
                DocumentVersion.id.in_(run.input_versions), DocumentVersion.owner_id == run.owner_id,
            ))) if run.input_versions else []
            action_rows = {action.id: action for action in db.scalars(select(ExternalAction).where(
                ExternalAction.id.in_(run.action_ids), ExternalAction.owner_id == run.owner_id,
            ))} if run.action_ids else {}
            return {
                "id": run.id, "owner_id": run.owner_id, "goal": run.goal,
                "output_language": run.output_language, "document_ids": documents,
                "actions": [{"id": action_rows[action_id].id, "kind": action_rows[action_id].kind,
                             "state": action_rows[action_id].state}
                            for action_id in run.action_ids if action_id in action_rows],
                "state": run.state, "phase": run.phase, "cancel_requested": run.cancel_requested,
            }

    def invocation_for_step(self, run_id: str, ordinal: int) -> dict:
        with self.sessions() as db:
            row = db.execute(select(ToolInvocation, AgentStep).join(
                AgentStep, AgentStep.id == ToolInvocation.step_id,
            ).where(
                ToolInvocation.run_id == run_id,
                AgentStep.ordinal == ordinal,
            )).first()
            if row is None:
                raise CoworkerError("agent_step_missing", "The planned agent step could not be recovered.", 409)
            invocation, step = row
            return {
                "id": invocation.id, "run_id": invocation.run_id, "step_id": step.id,
                "ordinal": step.ordinal, "tool": invocation.tool_name,
                "arguments": invocation.arguments, "state": invocation.state,
                "consequential": invocation.consequential,
                "approval_required": invocation.approval_required,
            }

    def begin_invocation(self, run_id: str, ordinal: int):
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            step = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal == ordinal,
            ).with_for_update())
            invocation = db.scalar(select(ToolInvocation).where(
                ToolInvocation.step_id == step.id,
            ).with_for_update()) if step is not None else None
            if step is None or invocation is None:
                raise CoworkerError("agent_step_missing", "The planned agent step could not be recovered.", 409)
            if invocation.state == "completed":
                return
            if invocation.consequential or invocation.approval_required:
                raise CoworkerError("approval_required", "This agent runtime cannot execute consequential tools yet.", 409)
            now = utcnow()
            invocation.state = "running"
            invocation.started_at = invocation.started_at or now
            step.state = "running"
            step.started_at = step.started_at or now
            self._event(db, run, "running", f"step_{ordinal}", f"Running agent step {ordinal}.")

    def step_resource(self, run_id: str, ordinal: int) -> dict | None:
        with self.sessions() as db:
            step = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal == ordinal,
            ))
            return dict(step.output) if step is not None and step.output else None

    def link_invocation_resource(self, run_id: str, ordinal: int, resource_type: str, resource_id: str):
        with self.sessions.begin() as db:
            step = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal == ordinal,
            ).with_for_update())
            if step is None:
                raise CoworkerError("agent_step_missing", "The planned agent step could not be recovered.", 409)
            step.output = {"resource_type": resource_type, "resource_id": resource_id}

    def action_waiting(self, run_id: str, ordinal: int, action_id: str, action_state: str):
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            step = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal == ordinal,
            ).with_for_update())
            invocation = db.scalar(select(ToolInvocation).where(
                ToolInvocation.step_id == step.id,
            ).with_for_update()) if step is not None else None
            if run is None or step is None or invocation is None:
                raise CoworkerError("agent_step_missing", "The planned agent step could not be recovered.", 409)
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            action = db.scalar(select(ExternalAction).where(
                ExternalAction.id == action_id,
                ExternalAction.owner_id == run.owner_id,
            ).with_for_update())
            if action is None or action.agent_run_id != run_id or action_id not in set(run.action_ids):
                raise CoworkerError("action_scope", "This action is not bound to the agent run.", 409)
            action.agent_ready = True
            step.output = {"resource_type": "action", "resource_id": action_id}
            if action_state == "awaiting_approval":
                changed = invocation.state != "awaiting_approval" or run.state != "awaiting_approval"
                invocation.state = "awaiting_approval"
                step.state = "awaiting_approval"
                if changed:
                    self._event(db, run, "awaiting_approval", f"step_{ordinal}", "Review and approve the attached action to continue.")
            elif action_state in {"queued", "executing"}:
                changed = invocation.state != "running" or run.state != "running"
                invocation.state = "running"
                step.state = "running"
                invocation.started_at = invocation.started_at or utcnow()
                step.started_at = step.started_at or utcnow()
                if changed:
                    self._event(db, run, "running", f"step_{ordinal}", "Approved action is executing.")

    def finish_invocation(self, run_id: str, ordinal: int, resource_type: str, resource_id: str, summary: dict):
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            step = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.ordinal == ordinal,
            ).with_for_update())
            invocation = db.scalar(select(ToolInvocation).where(
                ToolInvocation.step_id == step.id,
            ).with_for_update()) if step is not None else None
            if run is None or step is None or invocation is None:
                raise CoworkerError("agent_step_missing", "The planned agent step could not be recovered.", 409)
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            if db.get(ToolReceipt, invocation.id) is None:
                db.add(ToolReceipt(
                    invocation_id=invocation.id, run_id=run_id, owner_id=run.owner_id,
                    tool_name=invocation.tool_name, status="completed",
                    resource_type=resource_type, resource_id=resource_id, summary=summary,
                ))
            now = utcnow()
            invocation.state = "completed"
            invocation.finished_at = now
            step.state = "completed"
            step.finished_at = now
            step.output = {"resource_type": resource_type, "resource_id": resource_id}
            self._event(db, run, "running", f"step_{ordinal}", f"Agent step {ordinal} completed.")

    def fail_run(self, run_id: str, code: str, message: str):
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None or run.state in {"completed", "failed", "cancelled"}:
                return
            run.error_code = code
            now = utcnow()
            for action in db.scalars(select(ExternalAction).where(
                ExternalAction.agent_run_id == run_id,
                ExternalAction.state.in_({"awaiting_approval", "queued"}),
            ).with_for_update()):
                action.state, action.finished_at = "cancelled", now
                self._audit(db, run.owner_id, action.id, "action.cancelled_agent_failure")
            for invocation, step in db.execute(select(ToolInvocation, AgentStep).join(
                AgentStep, AgentStep.id == ToolInvocation.step_id,
            ).where(
                ToolInvocation.run_id == run_id,
                ToolInvocation.state.in_({"prepared", "running", "awaiting_approval"}),
            )):
                invocation.state = "failed"
                invocation.finished_at = now
                step.state = "failed"
                step.error_code = code
                step.finished_at = now
            self._event(db, run, "failed", run.phase, message[:300])
            self._audit(db, run.owner_id, run.id, "agent_run_failed")

    def complete_run(self, run_id: str):
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None or run.state == "completed":
                return
            if run.cancel_requested or run.state == "cancelled":
                return
            remaining = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run_id, ToolInvocation.state != "completed",
            ))
            if remaining:
                raise CoworkerError("agent_incomplete", "The agent run still has unfinished steps.", 409)
            self._event(db, run, "completed", "complete", "Agent run completed.")
            self._audit(db, run.owner_id, run.id, "agent_run_completed")
