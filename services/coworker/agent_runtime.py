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
            run["goal"], run["document_ids"], run["output_language"], self.container.settings
        )
        saved = self.repo.save_plan(run["owner_id"], run_id, steps)
        return len(saved["tool_invocations"])

    async def execute_step(self, run_id: str, ordinal: int) -> dict:
        run = self.repo.worker_run(run_id)
        invocation = self.repo.invocation_for_step(run_id, ordinal)
        if invocation["state"] == "completed":
            return {"status": "completed"}
        spec = tool(invocation["tool"])
        if spec.consequential or spec.approval_required:
            raise CoworkerError("approval_required", "This runtime does not execute consequential tools yet.", 409)
        if spec.kind != "task" or not spec.skill_id:
            raise CoworkerError("unsupported_agent_tool", "This agent tool is not executable in this runtime.", 409)

        args = spec.validate(invocation["arguments"])
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
        try:
            await self.runner.run_for_test(task["id"])
        except CoworkerError:
            raise
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
        self.repo.fail_run(run_id, code, message)
