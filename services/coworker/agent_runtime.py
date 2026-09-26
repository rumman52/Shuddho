from __future__ import annotations

from .agent_planner import deterministic_plan, intelligent_tool_names, proposal_to_plan
from .agent_tools import tool
from .agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from .errors import CoworkerError
from .runner import DocumentRunner
from .schemas import ResearchOptions, TaskCreate


REPLAN_REASONS = {"capability_changed", "result_incomplete"}


class AgentRuntime:
    def __init__(self, container, runner: DocumentRunner, planner=None):
        self.container = container
        self.runner = runner
        self.repo = container.agent
        self.planner = planner or DeepSeekAgentPlanner(container.settings)

    def plan(self, run_id: str) -> int:
        run = self.repo.worker_run(run_id)
        if run["cancel_requested"] or run["state"] == "cancelled":
            raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
        current = self.repo.get(run["owner_id"], run_id)
        if current["tool_invocations"]:
            return len(current["tool_invocations"])
        steps = deterministic_plan(
            run["goal"], run["document_ids"], run["output_language"], self.container.settings, run["actions"]
        )
        self.repo.set_planner_mode(run_id, "deterministic")
        saved = self.repo.save_plan(run["owner_id"], run_id, steps)
        return len(saved["tool_invocations"])

    def _planner_reservation(self) -> int:
        per_call = max(1, self.container.settings.agent_planner_token_budget // self.container.settings.max_agent_planner_calls)
        return min(per_call, self.container.settings.agent_planner_token_budget)

    async def plan_for_worker(self, run_id: str) -> int:
        if not self.container.settings.intelligent_planner_enabled:
            return self.plan(run_id)
        run = self.repo.worker_run(run_id)
        current = self.repo.get(run["owner_id"], run_id)
        if current["tool_invocations"]:
            return len(current["tool_invocations"])
        tools = intelligent_tool_names(self.container.settings, run["actions"])
        if not tools:
            return self.plan(run_id)
        reservation = self.repo.reserve_planner(run_id, self._planner_reservation())
        actual_tokens = None
        try:
            proposal, actual_tokens, _latency = await self.planner.propose(
                run["goal"],
                tools,
                reason="initial",
                allow_action_proposals=self.container.settings.agent_action_proposals_enabled,
                allow_linkedin_action_proposals=self.container.settings.agent_linkedin_proposals_enabled,
            )
            steps = proposal_to_plan(
                proposal, run["goal"], run["document_ids"], run["output_language"],
                self.container.settings, run["actions"],
            )
            saved = self.repo.save_plan(
                run["owner_id"],
                run_id,
                steps,
                action_proposals=proposal.action_proposals,
            )
            if self.container.settings.agent_action_selection_enabled:
                self.repo.release_unselected_actions(run_id)
            self.repo.set_planner_mode(run_id, "intelligent")
            return len(saved["tool_invocations"])
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            self.repo.set_planner_mode(run_id, "fallback")
            steps = deterministic_plan(
                run["goal"], run["document_ids"], run["output_language"], self.container.settings, run["actions"]
            )
            saved = self.repo.save_plan(run["owner_id"], run_id, steps)
            return len(saved["tool_invocations"])
        finally:
            self.repo.settle_planner_capacity(
                run_id, reservation["call"], actual_tokens,
            )

    async def replan(self, run_id: str, from_ordinal: int, reason: str = "capability_changed") -> int:
        if reason not in REPLAN_REASONS:
            raise CoworkerError("invalid_replan_reason", "The agent replan reason is not supported.", 422)
        if not self.container.settings.intelligent_planner_enabled:
            raise CoworkerError("replan_unavailable", "Intelligent replanning is not enabled.", 409)
        run = self.repo.worker_run(run_id)
        current = self.repo.get(run["owner_id"], run_id)
        if current["planner_calls"] >= self.container.settings.max_agent_planner_calls:
            raise CoworkerError("planner_call_limit", "This agent run reached its planner call limit.", 429)
        completed_actions = {
            receipt["resource_id"] for receipt in (
                item.get("receipt") for item in current["tool_invocations"] if item.get("receipt")
            ) if receipt and receipt.get("resource_type") == "action"
        }
        remaining_actions = [action for action in run["actions"] if action["id"] not in completed_actions]
        tools = intelligent_tool_names(self.container.settings, remaining_actions)
        if not tools:
            raise CoworkerError("no_agent_tool", "No suitable agent tool is currently enabled.", 409)
        reservation = self.repo.reserve_planner(run_id, self._planner_reservation())
        actual_tokens = None
        try:
            proposal, actual_tokens, _latency = await self.planner.propose(
                run["goal"],
                tools,
                reason=reason,
                allow_action_proposals=False,
                allow_linkedin_action_proposals=False,
            )
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            raise
        finally:
            self.repo.settle_planner_capacity(
                run_id, reservation["call"], actual_tokens,
            )
        steps = proposal_to_plan(
            proposal, run["goal"], run["document_ids"], run["output_language"],
            self.container.settings, remaining_actions,
        )
        saved = self.repo.replace_remaining_plan(run["owner_id"], run_id, from_ordinal, steps)
        if self.container.settings.agent_action_selection_enabled:
            self.repo.release_unselected_actions(run_id)
        self.repo.set_planner_mode(run_id, "replanned")
        return len([step for step in saved["steps"] if step["ordinal"] >= from_ordinal])

    def _v3_planner_reservation(self) -> int:
        per_call = max(
            1,
            self.container.settings.agent_v3_planner_token_budget
            // self.container.settings.max_agent_v3_planner_calls,
        )
        return min(per_call, self.container.settings.agent_v3_planner_token_budget)

    async def decide_v3(self, run_id: str) -> dict:
        run = self.repo.worker_run(run_id)
        if run["runtime_version"] != 3:
            raise CoworkerError("runtime_version", "This run is not assigned to Agent Runtime v3.", 409)
        if run["cancel_requested"] or run["state"] == "cancelled":
            raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)

        current = self.repo.get(run["owner_id"], run_id)
        observations = self.repo.verified_observations(run["owner_id"], run_id)
        tools = intelligent_tool_names(self.container.settings, run["actions"])
        remaining = self.repo.v3_remaining_budget(run_id)
        dependencies = {
            "steps": [{
                "ordinal": step["ordinal"],
                "state": step["state"],
                "depends_on": step["depends_on"],
            } for step in current["steps"] if step["ordinal"] > 0],
            "consequential_actions_require_explicit_approval": True,
        }
        if not tools and not self.repo.v3_can_complete(run_id):
            self.repo.v3_terminal(
                run_id,
                "blocked",
                "No registered tool is currently available for this bounded run.",
            )
            return {"decision": "blocked"}

        reservation = self.repo.reserve_planner(run_id, self._v3_planner_reservation())
        actual_tokens = None
        cost_microusd = None
        try:
            decision, actual_tokens, _latency, evidence = await self.planner.decide(
                run["goal"],
                tools,
                observations,
                remaining_budget=remaining,
                dependencies=dependencies,
            )
            if actual_tokens is not None and self.container.settings.agent_v3_planner_cost_microusd_per_1k_tokens > 0:
                cost_microusd = (
                    actual_tokens * self.container.settings.agent_v3_planner_cost_microusd_per_1k_tokens + 999
                ) // 1000
            self.repo.record_v3_decision(
                run_id,
                decision,
                planner_call=reservation["call"],
                model=evidence["model"],
                prompt_sha256=evidence["prompt_sha256"],
                tool_schema_sha256=evidence["tool_schema_sha256"],
                observation_count=len(observations),
                total_tokens=actual_tokens,
                cost_microusd=cost_microusd,
            )
            self.repo.set_planner_mode(run_id, "v3")

            if decision.decision == "next_step":
                ordinal = self.repo.append_v3_step(
                    run["owner_id"], run_id, decision.tool, decision.objective
                )
                return {"decision": "next_step", "ordinal": ordinal}
            if decision.decision == "complete":
                if not self.repo.v3_can_complete(run_id):
                    raise CoworkerError(
                        "agent_unverified_completion",
                        "Runtime v3 requested completion without verified tool receipts.",
                        409,
                    )
                return {"decision": "complete"}
            if decision.decision == "needs_input":
                self.repo.v3_terminal(run_id, "needs_input", decision.message)
                return {"decision": "needs_input"}
            if decision.decision == "blocked":
                self.repo.v3_terminal(run_id, "blocked", decision.message)
                return {"decision": "blocked"}
            if decision.decision == "awaiting_approval":
                if not self.repo.v3_approval_waiting(run_id):
                    raise CoworkerError(
                        "approval_state_unverified",
                        "Runtime v3 cannot claim an approval wait without a persisted waiting action.",
                        409,
                    )
                return {"decision": "awaiting_approval"}
            return {"decision": "wait", "wait_seconds": int(decision.wait_seconds)}
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            raise
        finally:
            self.repo.settle_planner_capacity(
                run_id,
                reservation["call"],
                actual_tokens,
                cost_microusd,
            )

    async def execute_step(self, run_id: str, ordinal: int) -> dict:
        run = self.repo.worker_run(run_id)
        invocation = self.repo.invocation_for_step(run_id, ordinal)
        if invocation["state"] == "completed":
            return {"status": "completed"}
        dependency = self.repo.dependency_state(run["owner_id"], run_id, ordinal)
        if not dependency["ready"]:
            raise CoworkerError("dependency_blocked", "This agent step is waiting for its required prior step.", 409)
        spec = tool(invocation["tool"])
        if not spec.enabled(self.container.settings) and spec.kind == "task":
            if self.container.settings.intelligent_planner_enabled and invocation["state"] == "prepared":
                return {"status": "replan_required"}
            raise CoworkerError("tool_unavailable", "A required agent tool is not enabled.", 409)
        args = spec.validate(invocation["arguments"])
        if spec.kind == "approved_action":
            action = self.container.actions.repo.get(run["owner_id"], str(args.action_id))
            state = action["state"]
            if state == "succeeded":
                summary = {"action_state": state, "provider_confirmed": True}
                self.repo.finish_invocation(run_id, ordinal, "action", action["id"], summary)
                return {"status": "completed"}
            if state == "outcome_unknown":
                raise CoworkerError("action_outcome_unknown", "The provider result is uncertain. Check the connected service before continuing.", 409)
            if state in {"failed", "cancelled", "expired"}:
                raise CoworkerError("action_" + state, "The attached action did not complete successfully.", 409)
            if state not in {"awaiting_approval", "queued", "executing"}:
                raise CoworkerError("action_state", "The attached action is not in a resumable state.", 409)
            self.repo.action_waiting(run_id, ordinal, action["id"], state)
            return {"status": "awaiting_approval" if state == "awaiting_approval" else "executing"}
        if spec.consequential or spec.approval_required:
            raise CoworkerError("approval_required", "This consequential tool must use the approved-action path.", 409)
        if spec.kind != "task" or not spec.skill_id:
            raise CoworkerError("unsupported_agent_tool", "This agent tool is not executable in this runtime.", 409)

        self.repo.begin_invocation(run_id, ordinal)
        research = None
        if spec.skill_id == "research":
            research = ResearchOptions(query=args.query, time_range=args.time_range)
        request = TaskCreate(
            skill_id=spec.skill_id,
            instruction=args.instruction,
            notes=args.notes,
            document_ids=args.document_ids,
            output_language=args.output_language,
            research=research,
        )
        task, _ = self.container.repository.create_task(
            run["owner_id"], request, f"agent:{run_id}:{ordinal}", enqueue=False,
            agent_run_id=run_id, agent_step_id=invocation["step_id"]
        )
        self.repo.link_invocation_resource(run_id, ordinal, "task", task["id"])
        worker_task = self.container.repository.worker_task(task["id"], False)
        phases = ["extract"] + (["research"] if worker_task["skill_id"] == "research" else []) + ["draft", "export", "complete"]
        for phase in phases:
            await self.runner.phase(task["id"], phase)
        result = self.container.repository.get_task(run["owner_id"], task["id"])
        if result["state"] not in {"completed", "needs_input"}:
            raise CoworkerError("agent_tool_failed", "An agent tool did not complete successfully.", 409)
        draft_step = self.container.repository.step(task["id"], "draft") or {}
        summary = {
            "task_state": result["state"],
            "artifact_count": len(result["artifacts"]),
            "has_missing_information": result["state"] == "needs_input",
            "memory": draft_step.get("memory_provenance", []),
            "handoff": draft_step.get("handoff_provenance", []),
        }
        self.repo.finish_invocation(run_id, ordinal, "task", task["id"], summary)
        if (result["state"] == "needs_input"
                and self.container.settings.agent_outcome_replan_enabled
                and self.container.settings.intelligent_planner_enabled):
            current = self.repo.get(run["owner_id"], run_id)
            if current["planner_mode"] in {"intelligent", "replanned"}:
                return {"status": "outcome_replan_required"}
        return {"status": "completed"}

    def complete(self, run_id: str):
        self.repo.complete_run(run_id)

    def fail(self, run_id: str, code: str, message: str):
        run = self.repo.worker_run(run_id)
        for ordinal in range(1, 9):
            try:
                invocation = self.repo.invocation_for_step(run_id, ordinal)
            except CoworkerError:
                break
            step = self.repo.step_resource(run_id, ordinal)
            if step and step.get("resource_type") == "task":
                self.container.repository.fail(step["resource_id"], code, message)
        self.repo.fail_run(run_id, code, message)
