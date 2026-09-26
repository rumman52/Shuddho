from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select

from .agent_schemas import AgentActionProposal, AgentPlanStep, AgentRunCreate, AgentV3Decision, action_proposal_hash
from .agent_tools import available_tools, tool
from .config import Settings
from .errors import CoworkerError
from .models import Account, ActionProposal, AgentDecision, AgentEvent, AgentOutbox, AgentRun, AgentStep, AuditEvent, DailyUsage, Document, DocumentVersion, ExternalAction, PersonalGoal, Step, Task, ToolInvocation, ToolReceipt, Workspace, utcnow
from .repository import aware, iso, not_found
from .provider_capacity import acquire_provider_lease, release_provider_lease, settle_provider_lease

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

    def create(
        self,
        owner: str,
        request: AgentRunCreate,
        idempotency_key: str,
        *,
        persistent_goal_id: str | None = None,
        persistent_goal_revision: int | None = None,
    ) -> tuple[dict, bool]:
        if not self.settings.agent_runtime_enabled:
            raise CoworkerError("agent_runtime_unavailable", "Agent runs are not enabled in this workspace yet.", 409)
        if request.memory_namespaces and not self.settings.agent_memory_enabled:
            raise CoworkerError("agent_memory_unavailable", "Structured memory is not enabled in this workspace yet.", 409)
        payload = request.model_dump(mode="json")
        if persistent_goal_id is not None:
            payload = payload | {
                "persistent_goal_id": persistent_goal_id,
                "persistent_goal_revision": persistent_goal_revision,
            }
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

            if persistent_goal_id is not None:
                if not self.settings.personal_goals_enabled:
                    raise CoworkerError("personal_goals_unavailable", "Persistent goals are not enabled in this workspace yet.", 409)
                goal_row = db.scalar(select(PersonalGoal).where(
                    PersonalGoal.id == persistent_goal_id,
                    PersonalGoal.owner_id == owner,
                ).with_for_update())
                if goal_row is None:
                    raise not_found()
                if persistent_goal_revision != goal_row.revision:
                    raise CoworkerError("goal_revision_conflict", "This goal changed. Review the latest revision before starting more work.", 409)
                if goal_row.state != "active":
                    raise CoworkerError("goal_not_active", "Only an active goal can start a new bounded run.", 409)
                if request.goal != goal_row.objective:
                    raise CoworkerError("goal_revision_conflict", "The run objective no longer matches this goal revision.", 409)
                max_runs = int((goal_row.budget if isinstance(goal_row.budget, dict) else {}).get("max_runs", 20))
                used_runs = db.scalar(select(func.count()).select_from(AgentRun).where(
                    AgentRun.owner_id == owner,
                    AgentRun.goal_id == persistent_goal_id,
                ))
                if used_runs >= max_runs:
                    raise CoworkerError("goal_run_budget", "This goal reached its configured bounded-run budget.", 409)

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
                if action.kind not in {"email_send", "calendar_create"}:
                    raise CoworkerError(
                        "action_not_agent_selectable",
                        "This action type must remain under direct user review and cannot be attached to an Agent run.",
                        409,
                    )
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
                goal_id=persistent_goal_id,
                goal_revision=persistent_goal_revision,
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
                runtime_version=(
                    3 if self.settings.agent_runtime_v3_enabled
                    else 2 if (
                        self.settings.agent_dependency_graph_enabled
                        and self.settings.agent_parallel_execution_enabled
                    )
                    else 1
                ),
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

    @staticmethod
    def _proposal_dto(row: ActionProposal) -> dict:
        display_state = (
            "expired"
            if row.state == "suggested" and aware(row.expires_at) <= utcnow()
            else row.state
        )
        return {
            "id": row.id,
            "kind": row.kind,
            "payload": row.payload,
            "rationale": row.rationale,
            "proposal_hash": row.proposal_hash,
            "state": display_state,
            "promoted_action_id": row.promoted_action_id,
            "created_at": iso(row.created_at),
            "expires_at": iso(row.expires_at),
            "promoted_at": iso(row.promoted_at) if row.promoted_at else None,
            "dismissed_at": iso(row.dismissed_at) if row.dismissed_at else None,
        }

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
        proposals = db.scalars(select(ActionProposal).where(
            ActionProposal.agent_run_id == run.id,
            ActionProposal.owner_id == run.owner_id,
        ).order_by(ActionProposal.created_at)).all()
        decisions = db.scalars(select(AgentDecision).where(
            AgentDecision.run_id == run.id,
            AgentDecision.owner_id == run.owner_id,
        ).order_by(AgentDecision.sequence)).all()
        documents = list(db.scalars(select(DocumentVersion.document_id).where(
            DocumentVersion.id.in_(run.input_versions), DocumentVersion.owner_id == run.owner_id,
        ))) if run.input_versions else []
        return {
            "id": run.id,
            "persistent_goal_id": run.goal_id,
            "persistent_goal_revision": run.goal_revision,
            "goal": run.goal,
            "output_language": run.output_language,
            "document_ids": documents,
            "action_ids": list(run.action_ids),
            "action_proposals": [self._proposal_dto(item) for item in proposals],
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
            "runtime_version": run.runtime_version,
            "planner_actual_tokens": run.planner_actual_tokens,
            "planner_cost_microusd": run.planner_cost_microusd,
            "decisions": [{
                "sequence": item.sequence,
                "planner_call": item.planner_call,
                "decision": item.decision_type,
                "payload": item.payload,
                "model": item.model,
                "prompt_sha256": item.prompt_sha256,
                "tool_schema_sha256": item.tool_schema_sha256,
                "observation_count": item.observation_count,
                "total_tokens": item.total_tokens,
                "cost_microusd": item.cost_microusd,
                "created_at": iso(item.created_at),
            } for item in decisions],
            "created_at": iso(run.created_at),
            "updated_at": iso(run.updated_at),
            "deadline_at": iso(run.deadline_at),
            "steps": [{
                "id": step.id,
                "ordinal": step.ordinal,
                "tool": step.tool_name,
                "state": step.state,
                "error_code": step.error_code,
                "depends_on": list(step.depends_on_ordinals),
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
                "terminal": run.state in {"completed", "failed", "cancelled", "needs_input", "blocked"},
                "sequence": run.event_sequence,
            }

    def reserve_planner(self, run_id: str, reserve_tokens: int) -> dict:
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            max_calls = (
                self.settings.max_agent_v3_planner_calls
                if run.runtime_version == 3 else self.settings.max_agent_planner_calls
            )
            token_budget = (
                self.settings.agent_v3_planner_token_budget
                if run.runtime_version == 3 else self.settings.agent_planner_token_budget
            )
            if run.planner_calls >= max_calls:
                raise CoworkerError("planner_call_limit", "This agent run reached its planner call limit.", 429)
            if reserve_tokens < 1 or run.planner_tokens + reserve_tokens > token_budget:
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
            call = run.planner_calls + 1
            acquire_provider_lease(
                db, self.settings, owner_id=run.owner_id, kind="planner",
                resource_id=run.id, sequence=call, reserved_tokens=reserve_tokens,
            )
            daily.allocated_tokens += reserve_tokens
            run.planner_calls = call
            run.planner_tokens += reserve_tokens
            run.planner_mode = "intelligent"
            self._audit(db, run.owner_id, run.id, "agent_planner_budget_reserved")
            return {"call": run.planner_calls, "reserved_tokens": reserve_tokens, "day": day}

    def settle_planner_capacity(
        self,
        run_id: str,
        call: int,
        actual_tokens: int | None,
        cost_microusd: int | None = None,
    ) -> None:
        with self.sessions.begin() as db:
            settle_provider_lease(
                db, kind="planner", resource_id=run_id, sequence=call,
                actual_tokens=actual_tokens,
            )
            run = db.get(AgentRun, run_id)
            if run is not None and actual_tokens is not None:
                run.planner_actual_tokens += max(0, int(actual_tokens))
                if cost_microusd is not None:
                    run.planner_cost_microusd += max(0, int(cost_microusd))

    def release_planner_capacity(self, run_id: str, call: int) -> None:
        self.settle_planner_capacity(run_id, call, None)

    def set_planner_mode(self, run_id: str, mode: str):
        if mode not in {"deterministic", "intelligent", "fallback", "replanned", "v3"}:
            raise CoworkerError("planner_mode", "Unsupported planner mode.", 422)
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            run.planner_mode = mode
            run.updated_at = utcnow()

    def _dependency_ordinals(self, db, run_id: str, owner: str, ordinal: int,
                             planned: AgentPlanStep) -> list[int]:
        """Derive a bounded dependency edge without trusting model-selected IDs."""
        if not self.settings.agent_dependency_graph_enabled or ordinal <= 1:
            return []
        spec = tool(planned.tool)
        # Consequential actions retain their explicit approval/action binding and do
        # not gain implicit content dependencies in this increment.
        if spec.kind == "approved_action" or spec.consequential or spec.approval_required:
            return []
        # Research is an upstream source producer, not a consumer of generated
        # task content. A later task depends on the nearest prior non-consequential
        # task step, skipping independent research/action nodes when necessary.
        if spec.skill_id == "research":
            return []
        prior = db.scalars(select(AgentStep).where(
            AgentStep.run_id == run_id,
            AgentStep.owner_id == owner,
            AgentStep.ordinal < ordinal,
        ).order_by(AgentStep.ordinal.desc())).all()
        research_fan_in: list[int] = []
        for candidate in prior:
            if candidate.tool_name is None:
                continue
            candidate_spec = tool(candidate.tool_name)
            if candidate_spec.kind != "task" or candidate_spec.consequential or candidate_spec.approval_required:
                continue
            if candidate_spec.skill_id == "research":
                research_fan_in.append(candidate.ordinal)
                continue
            if research_fan_in:
                return sorted(research_fan_in)
            return [candidate.ordinal]
        return sorted(research_fan_in)

    def dependency_state(self, owner: str, run_id: str, ordinal: int) -> dict:
        with self.sessions() as db:
            run = self._run(db, owner, run_id)
            current = db.scalar(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.owner_id == owner, AgentStep.ordinal == ordinal,
            ))
            if current is None:
                raise not_found()
            dependencies = list(current.depends_on_ordinals or [])
            if not dependencies:
                return {"ready": True, "depends_on": [], "blocked_by": []}
            rows = db.scalars(select(AgentStep).where(
                AgentStep.run_id == run.id,
                AgentStep.owner_id == owner,
                AgentStep.ordinal.in_(dependencies),
            )).all()
            states = {step.ordinal: step.state for step in rows}
            if len(states) != len(dependencies):
                raise CoworkerError("dependency_invalid", "An agent step dependency is missing.", 409)
            blocked = [value for value in dependencies if states.get(value) != "completed"]
            return {"ready": not blocked, "depends_on": dependencies, "blocked_by": blocked}

    def runnable_steps(self, run_id: str, limit: int) -> dict:
        """Return a deterministic server-owned scheduling snapshot for AgentWorkflow v2."""
        bounded = max(1, min(int(limit), self.settings.max_agent_parallel_steps))
        with self.sessions() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                raise not_found()
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            rows = db.execute(select(AgentStep, ToolInvocation).join(
                ToolInvocation, ToolInvocation.step_id == AgentStep.id,
            ).where(
                AgentStep.run_id == run.id,
                AgentStep.owner_id == run.owner_id,
                ToolInvocation.owner_id == run.owner_id,
            ).order_by(AgentStep.ordinal)).all()
            states = {step.ordinal: step.state for step, _invocation in rows}
            completed = [ordinal for ordinal, state in states.items() if state == "completed"]
            runnable = []
            blocked = {}
            replan_ordinal = None
            for step, invocation in rows:
                if invocation.state == "completed":
                    continue
                dependencies = list(step.depends_on_ordinals or [])
                if any(value >= step.ordinal for value in dependencies):
                    raise CoworkerError("dependency_invalid", "Agent dependencies must point to earlier steps.", 409)
                if any(value not in states for value in dependencies):
                    raise CoworkerError("dependency_invalid", "An agent step dependency is missing.", 409)
                failed = [value for value in dependencies if states[value] in {"failed", "cancelled"}]
                if failed:
                    blocked[step.ordinal] = failed
                    continue
                waiting = [value for value in dependencies if states[value] != "completed"]
                if waiting:
                    blocked[step.ordinal] = waiting
                    continue
                spec = tool(invocation.tool_name)
                if (spec.kind == "task" and not spec.enabled(self.settings)
                        and self.settings.intelligent_planner_enabled
                        and invocation.state == "prepared"):
                    replan_ordinal = step.ordinal
                    break
                runnable.append({
                    "ordinal": step.ordinal,
                    "approved_action": bool(
                        spec.kind == "approved_action" or invocation.consequential or invocation.approval_required
                    ),
                })
            if replan_ordinal is not None:
                return {
                    "runnable": [], "completed": completed, "blocked": blocked,
                    "replan_ordinal": replan_ordinal, "cancelled": False,
                }
            if not runnable:
                return {"runnable": [], "completed": completed, "blocked": blocked, "replan_ordinal": None, "cancelled": False}
            runnable.sort(key=lambda item: item["ordinal"])
            first_action = next((item for item in runnable if item["approved_action"]), None)
            if first_action is not None:
                before = [item for item in runnable if not item["approved_action"] and item["ordinal"] < first_action["ordinal"]]
                chosen = before[:bounded] if before else [first_action]
            else:
                chosen = runnable[:bounded]
            if self.settings.agent_outcome_replan_enabled:
                chosen = chosen[:1]
            return {
                "runnable": [item["ordinal"] for item in chosen],
                "completed": completed,
                "blocked": blocked,
                "replan_ordinal": None,
                "cancelled": False,
            }

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
                    # There is intentionally no ORM relationship here. Flush the
                    # FK child before deleting its AgentStep parent.
                    db.flush()
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
                    depends_on_ordinals=self._dependency_ordinals(db, run.id, owner, ordinal, planned),
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

    def save_plan(
        self,
        owner: str,
        run_id: str,
        steps: list[AgentPlanStep],
        action_proposals: list[AgentActionProposal] | None = None,
    ) -> dict:
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
                    depends_on_ordinals=self._dependency_ordinals(db, run.id, owner, ordinal, planned),
                )
                db.add(step)
                db.flush()
                db.add(ToolInvocation(
                    id=str(uuid4()), run_id=run.id, step_id=step.id, owner_id=owner,
                    tool_name=spec.name, tool_version=spec.version,
                    arguments=validated.model_dump(mode="json"), state="prepared",
                    consequential=spec.consequential, approval_required=spec.approval_required,
                ))
            proposals = list(action_proposals or [])
            if proposals and not self.settings.agent_action_proposals_enabled:
                raise CoworkerError(
                    "action_proposals_disabled",
                    "Agent action proposals are not enabled in this deployment.",
                    409,
                )
            if len(proposals) > 2:
                raise CoworkerError(
                    "action_proposal_limit",
                    "An agent run may suggest at most two action proposals.",
                    422,
                )
            for proposed in proposals:
                payload = proposed.payload.model_dump(mode="json")
                if (
                    payload.get("kind") == "social_publish_linkedin"
                    and not self.settings.agent_linkedin_proposals_enabled
                ):
                    raise CoworkerError(
                        "linkedin_action_proposals_disabled",
                        "LinkedIn Agent proposals are not enabled in this deployment.",
                        409,
                    )
                proposal_id = str(uuid4())
                db.add(ActionProposal(
                    id=proposal_id,
                    owner_id=owner,
                    agent_run_id=run.id,
                    kind=payload["kind"],
                    payload=payload,
                    rationale=proposed.rationale,
                    proposal_hash=action_proposal_hash(
                        run.id,
                        payload,
                        proposed.rationale,
                    ),
                    state="suggested",
                    expires_at=utcnow() + timedelta(hours=24),
                ))
                self._audit(
                    db,
                    owner,
                    proposal_id,
                    "agent_action_proposal_suggested",
                )
            self._event(db, run, "planning", "planned", f"Plan saved with {len(steps)} bounded steps.")
            self._audit(db, owner, run.id, "agent_plan_saved")
            return self._dto(db, run)


    def release_unselected_actions(self, run_id: str) -> list[str]:
        """Detach only still-unapproved bound actions that the saved plan did not select."""
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            referenced: set[str] = set()
            rows = db.scalars(select(ToolInvocation).where(
                ToolInvocation.run_id == run.id,
                ToolInvocation.owner_id == run.owner_id,
                ToolInvocation.consequential.is_(True),
                ToolInvocation.approval_required.is_(True),
            )).all()
            for invocation in rows:
                action_id = invocation.arguments.get("action_id") if isinstance(invocation.arguments, dict) else None
                if isinstance(action_id, str):
                    referenced.add(action_id)

            kept: list[str] = []
            released: list[str] = []
            for action_id in list(run.action_ids):
                action = db.scalar(select(ExternalAction).where(
                    ExternalAction.id == action_id,
                    ExternalAction.owner_id == run.owner_id,
                ).with_for_update())
                if action is None:
                    continue
                if (
                    action.id not in referenced
                    and action.state == "awaiting_approval"
                    and action.agent_run_id == run.id
                    and not action.agent_ready
                ):
                    action.agent_run_id = None
                    action.agent_ready = False
                    released.append(action.id)
                    self._audit(db, run.owner_id, action.id, "action.released_unselected")
                    continue
                kept.append(action.id)
            if released:
                run.action_ids = kept
                run.updated_at = utcnow()
                self._audit(db, run.owner_id, run.id, "agent_action_selection_pruned")
            return released

    def dismiss_action_proposal(
        self,
        owner: str,
        run_id: str,
        proposal_id: str,
        proposal_hash: str,
    ) -> dict:
        with self.sessions.begin() as db:
            self._run(db, owner, run_id)
            row = db.scalar(select(ActionProposal).where(
                ActionProposal.id == proposal_id,
                ActionProposal.owner_id == owner,
                ActionProposal.agent_run_id == run_id,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.proposal_hash != proposal_hash:
                raise CoworkerError(
                    "proposal_changed",
                    "This proposal changed. Review it again.",
                    409,
                )
            if row.state == "suggested" and aware(row.expires_at) <= utcnow():
                row.state = "expired"
            if row.state == "dismissed":
                return self._proposal_dto(row)
            if row.state != "suggested":
                raise CoworkerError(
                    "proposal_unavailable",
                    "This proposal can no longer be dismissed.",
                    409,
                )
            row.state = "dismissed"
            row.dismissed_at = utcnow()
            self._audit(
                db,
                owner,
                row.id,
                "agent_action_proposal_dismissed",
            )
            return self._proposal_dto(row)

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
                "persistent_goal_id": run.goal_id, "persistent_goal_revision": run.goal_revision,
                "output_language": run.output_language, "document_ids": documents,
                "actions": [{"id": action_rows[action_id].id, "kind": action_rows[action_id].kind,
                             "state": action_rows[action_id].state}
                            for action_id in run.action_ids if action_id in action_rows],
                "state": run.state, "phase": run.phase, "cancel_requested": run.cancel_requested,
                "runtime_version": run.runtime_version,
            }

    def handoff_context(self, owner: str, run_id: str, step_id: str) -> dict:
        if not self.settings.agent_handoffs_enabled:
            return {"sources": [], "provenance": []}
        with self.sessions() as db:
            current = db.scalar(select(AgentStep).where(
                AgentStep.id == step_id,
                AgentStep.run_id == run_id,
                AgentStep.owner_id == owner,
            ))
            if current is None:
                raise CoworkerError("handoff_scope", "The agent handoff step is not available.", 409)
            prior_steps = db.scalars(select(AgentStep).where(
                AgentStep.run_id == run_id,
                AgentStep.owner_id == owner,
                AgentStep.ordinal < current.ordinal,
                AgentStep.state == "completed",
            ).order_by(AgentStep.ordinal.desc())).all()
            source_limit = (
                min(self.settings.max_agent_handoff_sources, 2)
                if self.settings.agent_multi_handoffs_enabled else 1
            )
            remaining = self.settings.max_agent_handoff_bytes
            sources = []
            provenance = []
            for prior in prior_steps:
                if len(sources) >= source_limit or remaining <= 0:
                    break
                invocation = db.scalar(select(ToolInvocation).where(
                    ToolInvocation.step_id == prior.id,
                    ToolInvocation.owner_id == owner,
                    ToolInvocation.state == "completed",
                    ToolInvocation.consequential.is_(False),
                    ToolInvocation.approval_required.is_(False),
                ))
                if invocation is None:
                    continue
                receipt = db.scalar(select(ToolReceipt).where(
                    ToolReceipt.invocation_id == invocation.id,
                    ToolReceipt.owner_id == owner,
                    ToolReceipt.status == "completed",
                    ToolReceipt.resource_type == "task",
                ))
                if receipt is None or not receipt.resource_id:
                    continue
                task = db.scalar(select(Task).where(
                    Task.id == receipt.resource_id,
                    Task.owner_id == owner,
                    Task.agent_run_id == run_id,
                    Task.agent_step_id == prior.id,
                ))
                if task is None or task.state not in {"completed", "needs_input"}:
                    raise CoworkerError("handoff_scope", "The upstream agent task could not be verified.", 409)
                draft = db.get(Step, (task.id, "draft"))
                if draft is None or not isinstance(draft.output.get("draft"), dict):
                    raise CoworkerError("handoff_missing", "The upstream agent result could not be recovered.", 409)
                raw = json.dumps(
                    draft.output["draft"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                truncated = len(raw) > remaining
                text_value = raw[:remaining].decode("utf-8", errors="ignore")
                if not text_value:
                    break
                if truncated:
                    marker = "\n[handoff truncated]"
                    marker_bytes = marker.encode("utf-8")
                    if len(text_value.encode("utf-8")) + len(marker_bytes) <= remaining:
                        text_value += marker
                text_bytes = text_value.encode("utf-8")
                remaining -= len(text_bytes)
                source_id = "agent-step-" + invocation.id
                sources.append({
                    "id": source_id,
                    "label": f"Prior {invocation.tool_name} result",
                    "text": text_value,
                    "sha256": hashlib.sha256(text_bytes).hexdigest(),
                    "upstream_sha256": hashlib.sha256(raw).hexdigest(),
                    "agent_invocation_id": invocation.id,
                    "task_id": task.id,
                    "tool": invocation.tool_name,
                })
                provenance.append({
                    "invocation_id": invocation.id,
                    "task_id": task.id,
                    "tool": invocation.tool_name,
                    "ordinal": prior.ordinal,
                    "truncated": truncated,
                })
            sources.reverse()
            provenance.reverse()
            return {"sources": sources, "provenance": provenance}

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

    def verified_observations(self, owner: str, run_id: str) -> list[dict]:
        """Return bounded, owner-scoped evidence from persisted receipts only."""
        with self.sessions() as db:
            run = self._run(db, owner, run_id)
            rows = db.execute(select(AgentStep, ToolInvocation, ToolReceipt).join(
                ToolInvocation, ToolInvocation.step_id == AgentStep.id,
            ).join(
                ToolReceipt, ToolReceipt.invocation_id == ToolInvocation.id,
            ).where(
                AgentStep.run_id == run.id,
                AgentStep.owner_id == owner,
                ToolInvocation.owner_id == owner,
                ToolReceipt.owner_id == owner,
                ToolReceipt.status == "completed",
            ).order_by(AgentStep.ordinal)).all()
            result = []
            for step, invocation, receipt in rows[:8]:
                summary = receipt.summary if isinstance(receipt.summary, dict) else {}
                safe_summary = {
                    key: summary[key]
                    for key in (
                        "task_state", "artifact_count", "has_missing_information",
                        "action_state", "provider_confirmed",
                    )
                    if key in summary and isinstance(summary[key], (str, int, bool, type(None)))
                }
                if receipt.resource_type == "task" and receipt.resource_id:
                    task = db.scalar(select(Task).where(
                        Task.id == receipt.resource_id,
                        Task.owner_id == owner,
                        Task.agent_run_id == run.id,
                        Task.agent_step_id == step.id,
                    ))
                    draft = db.get(Step, (task.id, "draft")) if task is not None else None
                    if task is not None and draft is not None and isinstance(draft.output.get("draft"), dict):
                        encoded = json.dumps(
                            draft.output["draft"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        )
                        safe_summary["result_excerpt"] = encoded[:1800]
                status = (
                    "provider_confirmed"
                    if receipt.resource_type == "action" and safe_summary.get("provider_confirmed") is True
                    else "needs_input"
                    if safe_summary.get("has_missing_information") is True
                    else "completed"
                )
                result.append({
                    "ordinal": step.ordinal,
                    "tool": invocation.tool_name,
                    "status": status,
                    "resource_type": receipt.resource_type,
                    "summary": safe_summary,
                })
            return result

    def assert_v3_within_deadline(self, run_id: str) -> None:
        with self.sessions() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                raise not_found()
            if aware(run.deadline_at) <= utcnow():
                raise CoworkerError(
                    "agent_deadline",
                    "This bounded Agent Runtime v3 run reached its active-runtime deadline.",
                    409,
                )

    def v3_remaining_budget(self, run_id: str) -> dict:
        with self.sessions() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                raise not_found()
            step_count = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run.id,
            ))
            return {
                "tool_steps_remaining": max(0, 8 - int(step_count or 0)),
                "planner_calls_remaining": max(
                    0, self.settings.max_agent_v3_planner_calls - run.planner_calls
                ),
                "planner_tokens_remaining": max(
                    0, self.settings.agent_v3_planner_token_budget - run.planner_tokens
                ),
            }

    def append_v3_step(self, owner: str, run_id: str, tool_name: str, objective: str) -> int:
        """Translate one model-selected registered tool into server-owned arguments."""
        from .agent_planner import action_selection_candidates, intelligent_tool_names

        with self.sessions.begin() as db:
            run = self._run(db, owner, run_id, lock=True)
            if run.runtime_version != 3:
                raise CoworkerError("runtime_version", "This run is not assigned to Agent Runtime v3.", 409)
            if run.cancel_requested or run.state == "cancelled":
                raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
            existing = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run.id,
            ))
            if existing >= 8:
                raise CoworkerError("agent_step_limit", "This agent run reached its tool-step limit.", 429)
            action_rows = {action.id: action for action in db.scalars(select(ExternalAction).where(
                ExternalAction.id.in_(run.action_ids), ExternalAction.owner_id == owner,
            ))} if run.action_ids else {}
            actions = [{
                "id": action_rows[action_id].id,
                "kind": action_rows[action_id].kind,
                "state": action_rows[action_id].state,
            } for action_id in run.action_ids if action_id in action_rows]
            allowed = set(intelligent_tool_names(self.settings, actions))
            if tool_name not in allowed:
                raise CoworkerError("planner_tool_scope", "The planner selected a tool outside the allowed registry.", 409)

            candidates = action_selection_candidates(actions) if self.settings.agent_action_selection_enabled else {}
            selected = candidates.get(tool_name)
            if selected is not None:
                actual_name = "email.send" if selected["kind"] == "email_send" else "calendar.create"
                arguments = {"action_id": selected["id"]}
            else:
                actual_name = tool_name
                run_docs = list(self._run_document_ids(db, run))
                arguments = {
                    "instruction": objective,
                    "notes": run.goal if actual_name == "report.create" else "",
                    "document_ids": run_docs,
                    "output_language": run.output_language,
                }
                if actual_name == "research.search":
                    arguments["query"] = objective[:400]
                    arguments["time_range"] = "any"

            spec = tool(actual_name)
            if not spec.enabled(self.settings):
                raise CoworkerError("tool_unavailable", "A required agent tool is not enabled.", 409)
            validated = spec.validate(arguments)
            ordinal = int(existing or 0) + 1
            planned = AgentPlanStep(tool=actual_name, arguments=validated.model_dump(mode="json"))
            step = AgentStep(
                id=str(uuid4()), run_id=run.id, owner_id=owner, ordinal=ordinal,
                tool_name=spec.name, state="planned",
                input={"arguments": validated.model_dump(mode="json"), "v3_objective": objective},
                output={},
                depends_on_ordinals=self._dependency_ordinals(db, run.id, owner, ordinal, planned),
            )
            db.add(step); db.flush()
            db.add(ToolInvocation(
                id=str(uuid4()), run_id=run.id, step_id=step.id, owner_id=owner,
                tool_name=spec.name, tool_version=spec.version,
                arguments=validated.model_dump(mode="json"), state="prepared",
                consequential=spec.consequential, approval_required=spec.approval_required,
            ))
            self._event(db, run, "planning", "v3_decision", f"Runtime v3 selected bounded step {ordinal}.")
            return ordinal

    def record_v3_decision(
        self,
        run_id: str,
        decision: AgentV3Decision,
        *,
        planner_call: int,
        model: str,
        prompt_sha256: str,
        tool_schema_sha256: str,
        observation_count: int,
        total_tokens: int | None,
        cost_microusd: int | None,
    ) -> None:
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            if run.runtime_version != 3:
                raise CoworkerError("runtime_version", "This run is not assigned to Agent Runtime v3.", 409)
            existing = db.scalar(select(AgentDecision).where(
                AgentDecision.run_id == run.id,
                AgentDecision.planner_call == planner_call,
            ))
            if existing is not None:
                return
            sequence = db.scalar(select(func.count()).select_from(AgentDecision).where(
                AgentDecision.run_id == run.id,
            )) + 1
            db.add(AgentDecision(
                run_id=run.id, sequence=sequence, owner_id=run.owner_id,
                planner_call=planner_call, decision_type=decision.decision,
                payload=decision.model_dump(mode="json", exclude_none=True),
                model=model[:120], prompt_sha256=prompt_sha256,
                tool_schema_sha256=tool_schema_sha256,
                observation_count=observation_count,
                total_tokens=total_tokens, cost_microusd=cost_microusd,
            ))
            self._audit(db, run.owner_id, run.id, "agent_v3_decision_recorded")

    def v3_can_complete(self, run_id: str) -> bool:
        with self.sessions() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                raise not_found()
            invocations = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run.id,
            ))
            if not invocations:
                return False
            incomplete = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run.id, ToolInvocation.state != "completed",
            ))
            receipt_rows = db.scalars(select(ToolReceipt).where(
                ToolReceipt.run_id == run.id, ToolReceipt.status == "completed",
            )).all()
            if len(receipt_rows) != invocations:
                return False
            for receipt in receipt_rows:
                summary = receipt.summary if isinstance(receipt.summary, dict) else {}
                if summary.get("has_missing_information") is True:
                    return False
                if receipt.resource_type == "action" and summary.get("provider_confirmed") is not True:
                    return False
            return incomplete == 0

    def v3_terminal(self, run_id: str, state: str, message: str) -> None:
        if state not in {"needs_input", "blocked"}:
            raise CoworkerError("agent_state", "Unsupported Runtime v3 terminal state.", 422)
        with self.sessions.begin() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
            if run is None:
                raise not_found()
            if run.state in {"completed", "failed", "cancelled", "needs_input", "blocked"}:
                return
            self._event(db, run, state, state, message[:300])
            self._audit(db, run.owner_id, run.id, f"agent_run_{state}")

    def v3_approval_waiting(self, run_id: str) -> bool:
        with self.sessions() as db:
            return db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run_id,
                ToolInvocation.state == "awaiting_approval",
            )) > 0

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
            completed_invocations = db.scalar(select(func.count()).select_from(ToolInvocation).where(
                ToolInvocation.run_id == run_id, ToolInvocation.state == "completed",
            ))
            verified_receipts = db.scalar(select(func.count()).select_from(ToolReceipt).where(
                ToolReceipt.run_id == run_id, ToolReceipt.status == "completed",
            ))
            if completed_invocations != verified_receipts:
                raise CoworkerError(
                    "agent_unverified_completion",
                    "The agent run cannot complete without one verified receipt per completed tool.",
                    409,
                )
            self._event(db, run, "completed", "complete", "Agent run completed.")
            self._audit(db, run.owner_id, run.id, "agent_run_completed")
