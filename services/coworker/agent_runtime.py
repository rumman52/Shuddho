from __future__ import annotations

from .agent_planner import deterministic_plan
from .agent_tools import tool
from .errors import CoworkerError
from .runner import DocumentRunner
from .schemas import ResearchOptions, TaskCreate


class AgentRuntime:
    def __init__(self, container, runner: DocumentRunner):
        self.container = container
        self.runner = runner
        self.repo = container.agent

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
        saved = self.repo.save_plan(run["owner_id"], run_id, steps)
        return len(saved["tool_invocations"])

    async def execute_step(self, run_id: str, ordinal: int) -> dict:
        run = self.repo.worker_run(run_id)
        invocation = self.repo.invocation_for_step(run_id, ordinal)
        if invocation["state"] == "completed":
            return {"status": "completed"}
        spec = tool(invocation["tool"])
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
            run["owner_id"], request, f"agent:{run_id}:{ordinal}", enqueue=False
        )
        self.repo.link_invocation_resource(run_id, ordinal, "task", task["id"])
        worker_task = self.container.repository.worker_task(task["id"], False)
        phases = ["extract"] + (["research"] if worker_task["skill_id"] == "research" else []) + ["draft", "export", "complete"]
        for phase in phases:
            await self.runner.phase(task["id"], phase)
        result = self.container.repository.get_task(run["owner_id"], task["id"])
        if result["state"] not in {"completed", "needs_input"}:
            raise CoworkerError("agent_tool_failed", "An agent tool did not complete successfully.", 409)
        summary = {
            "task_state": result["state"],
            "artifact_count": len(result["artifacts"]),
            "has_missing_information": result["state"] == "needs_input",
        }
        self.repo.finish_invocation(run_id, ordinal, "task", task["id"], summary)
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
