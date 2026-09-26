"""Deterministic Temporal definition. History carries IDs and safe status only."""
import asyncio
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError




@workflow.defn(name="shuddho_automation_occurrence_v1")
class AutomationOccurrenceWorkflow:
    """One finite Temporal Schedule firing; all authority stays in server activities."""

    @workflow.run
    async def run(self, value: dict):
        automation_id = str(value["automation_id"])
        revision = int(value["revision"])
        prefix = f"shuddho-automation-{automation_id}-r{revision}-"
        workflow_id = workflow.info().workflow_id
        if not workflow_id.startswith(prefix):
            raise ApplicationError("Scheduled workflow identity is invalid.", type="automation_workflow_identity")
        due_text = workflow_id[len(prefix):]
        try:
            due_at = datetime.fromisoformat(due_text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            raise ApplicationError("Scheduled occurrence time is invalid.", type="automation_occurrence_time") from None
        await workflow.execute_activity(
            "shuddho_accept_automation_occurrence_v1",
            {"automation_id": automation_id, "revision": revision, "due_at": due_at},
            start_to_close_timeout=timedelta(seconds=45),
            schedule_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=5),
        )


@workflow.defn(name="shuddho_approved_action_v1")
class ApprovedActionWorkflow:
    @workflow.run
    async def run(self, action_id: str):
        try:
            await workflow.execute_activity(
                "shuddho_execute_action_v1", action_id,
                start_to_close_timeout=timedelta(seconds=100),
                schedule_to_close_timeout=timedelta(minutes=4),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=3),
            )
        except ActivityError:
            await workflow.execute_activity(
                "shuddho_action_interrupted_v1", action_id,
                start_to_close_timeout=timedelta(seconds=20), schedule_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )


@workflow.defn(name="shuddho_report_email_v1")
class ReportEmailWorkflow:
    @workflow.run
    async def run(self, task_id: str):
        try:
            for phase in ("extract", "draft", "export", "complete"):
                await workflow.execute_activity(
                    "shuddho_document_phase_v1", {"task_id": task_id, "phase": phase},
                    start_to_close_timeout=timedelta(seconds=180),
                    schedule_to_close_timeout=timedelta(minutes=6),
                    heartbeat_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=2),
                )
        except ActivityError as error:
            cause = error.cause
            code = cause.type if isinstance(cause, ApplicationError) else "workflow_failed"
            message = str(cause.message) if isinstance(cause, ApplicationError) else "This task could not finish. Please try again."
            await workflow.execute_activity(
                "shuddho_document_failed_v1", {"task_id": task_id, "code": code, "message": message},
                start_to_close_timeout=timedelta(seconds=20),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )


@workflow.defn(name="shuddho_work_services_v1")
class WorkServicesWorkflow:
    """Separate workflow/activity identity keeps Part 2 histories replayable."""
    @workflow.run
    async def run(self, task_id: str):
        try:
            for phase in ("extract", "draft", "export", "complete"):
                await workflow.execute_activity(
                    "shuddho_work_phase_v1", {"task_id": task_id, "phase": phase},
                    start_to_close_timeout=timedelta(seconds=180),
                    schedule_to_close_timeout=timedelta(minutes=6),
                    heartbeat_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=2),
                )
        except ActivityError as error:
            cause = error.cause
            code = cause.type if isinstance(cause, ApplicationError) else "workflow_failed"
            message = str(cause.message) if isinstance(cause, ApplicationError) else "This task could not finish. Please try again."
            await workflow.execute_activity(
                "shuddho_document_failed_v1", {"task_id": task_id, "code": code, "message": message},
                start_to_close_timeout=timedelta(seconds=20),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )


@workflow.defn(name="shuddho_research_v1")
class ResearchWorkflow:
    """A new history identity; existing four-step workflows remain unchanged."""
    @workflow.run
    async def run(self, task_id: str):
        try:
            for phase in ("extract", "research", "draft", "export", "complete"):
                await workflow.execute_activity(
                    "shuddho_research_phase_v1", {"task_id": task_id, "phase": phase},
                    start_to_close_timeout=timedelta(seconds=180),
                    schedule_to_close_timeout=timedelta(minutes=6),
                    heartbeat_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=2),
                )
        except ActivityError as error:
            cause = error.cause
            code = cause.type if isinstance(cause, ApplicationError) else "workflow_failed"
            message = str(cause.message) if isinstance(cause, ApplicationError) else "This task could not finish. Please try again."
            await workflow.execute_activity(
                "shuddho_document_failed_v1", {"task_id": task_id, "code": code, "message": message},
                start_to_close_timeout=timedelta(seconds=20),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )


@workflow.defn(name="shuddho_agent_run_v1")
class AgentWorkflow:
    """Bounded agent orchestration. Temporal history contains IDs and safe status only."""

    @workflow.run
    async def run(self, run_id: str):
        try:
            count = await workflow.execute_activity(
                "shuddho_agent_plan_v1", run_id,
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            ordinal = 1
            replanned = False
            while ordinal <= count:
                while True:
                    result = await workflow.execute_activity(
                        "shuddho_agent_step_v1", {"run_id": run_id, "ordinal": ordinal},
                        start_to_close_timeout=timedelta(minutes=8),
                        schedule_to_close_timeout=timedelta(minutes=12),
                        heartbeat_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=2),
                    )
                    if not result or result.get("status") == "completed":
                        ordinal += 1
                        break
                    status = result.get("status")
                    if status in {"replan_required", "outcome_replan_required"}:
                        if replanned:
                            if status == "outcome_replan_required":
                                ordinal += 1
                                break
                            raise ApplicationError("The agent already used its one replan.", type="replan_limit")
                        from_ordinal = ordinal if status == "replan_required" else ordinal + 1
                        if from_ordinal > count:
                            ordinal += 1
                            break
                        reason = "capability_changed" if status == "replan_required" else "result_incomplete"
                        replacement_count = await workflow.execute_activity(
                            "shuddho_agent_replan_v1",
                            {"run_id": run_id, "from_ordinal": from_ordinal, "reason": reason},
                            start_to_close_timeout=timedelta(seconds=45),
                            schedule_to_close_timeout=timedelta(minutes=2),
                            retry_policy=RetryPolicy(maximum_attempts=1),
                        )
                        count = from_ordinal - 1 + replacement_count
                        replanned = True
                        if status == "outcome_replan_required":
                            ordinal += 1
                            break
                        continue
                    if status not in {"awaiting_approval", "executing"}:
                        raise ApplicationError("Agent step returned an unsupported state.", type="agent_step_state")
                    await workflow.sleep(timedelta(seconds=5))
            await workflow.execute_activity(
                "shuddho_agent_complete_v1", run_id,
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except (ActivityError, ApplicationError) as error:
            cause = error.cause if isinstance(error, ActivityError) else error
            code = cause.type if isinstance(cause, ApplicationError) else "agent_workflow_failed"
            message = str(cause.message) if isinstance(cause, ApplicationError) else "This agent run could not finish. Please try again."
            await workflow.execute_activity(
                "shuddho_agent_failed_v1", {"run_id": run_id, "code": code, "message": message},
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )


@workflow.defn(name="shuddho_agent_run_v2")
class AgentWorkflowV2:
    """Bounded fan-out/fan-in orchestration over persisted server-owned dependencies."""

    @workflow.run
    async def run(self, value: dict):
        run_id = str(value["run_id"])
        max_parallel_steps = max(1, int(value.get("max_parallel_steps", 2)))
        replanned = False
        try:
            count = await workflow.execute_activity(
                "shuddho_agent_plan_v1", run_id,
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            while True:
                snapshot = await workflow.execute_activity(
                    "shuddho_agent_readiness_v2",
                    {"run_id": run_id, "limit": max_parallel_steps},
                    start_to_close_timeout=timedelta(seconds=20),
                    schedule_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                if len(snapshot.get("completed", [])) >= count:
                    break

                replan_ordinal = snapshot.get("replan_ordinal")
                if replan_ordinal is not None:
                    if replanned:
                        raise ApplicationError("The agent already used its one replan.", type="replan_limit")
                    replacement_count = await workflow.execute_activity(
                        "shuddho_agent_replan_v1",
                        {"run_id": run_id, "from_ordinal": int(replan_ordinal), "reason": "capability_changed"},
                        start_to_close_timeout=timedelta(seconds=45),
                        schedule_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    count = int(replan_ordinal) - 1 + replacement_count
                    replanned = True
                    continue

                ordinals = [int(item) for item in snapshot.get("runnable", [])]
                if not ordinals:
                    raise ApplicationError(
                        "No runnable agent step remains for the persisted dependency graph.",
                        type="dependency_deadlock",
                    )

                handles = [
                    workflow.start_activity(
                        "shuddho_agent_step_v1", {"run_id": run_id, "ordinal": ordinal},
                        start_to_close_timeout=timedelta(minutes=8),
                        schedule_to_close_timeout=timedelta(minutes=12),
                        heartbeat_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=2),
                    )
                    for ordinal in ordinals
                ]
                results = await asyncio.gather(*handles, return_exceptions=True)
                first_error = next((item for item in results if isinstance(item, BaseException)), None)
                if first_error is not None:
                    raise first_error

                replan_request = None
                waiting = False
                for ordinal, result in zip(ordinals, results):
                    if not result or result.get("status") == "completed":
                        continue
                    status = result.get("status")
                    if status == "replan_required":
                        replan_request = (ordinal, "capability_changed")
                        break
                    if status == "outcome_replan_required":
                        replan_request = (ordinal + 1, "result_incomplete")
                        break
                    if status in {"awaiting_approval", "executing"}:
                        waiting = True
                        continue
                    raise ApplicationError("Agent step returned an unsupported state.", type="agent_step_state")

                if replan_request is not None:
                    from_ordinal, reason = replan_request
                    if from_ordinal > count:
                        continue
                    if replanned:
                        if reason == "result_incomplete":
                            continue
                        raise ApplicationError("The agent already used its one replan.", type="replan_limit")
                    replacement_count = await workflow.execute_activity(
                        "shuddho_agent_replan_v1",
                        {"run_id": run_id, "from_ordinal": from_ordinal, "reason": reason},
                        start_to_close_timeout=timedelta(seconds=45),
                        schedule_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    count = from_ordinal - 1 + replacement_count
                    replanned = True
                    continue

                if waiting:
                    await workflow.sleep(timedelta(seconds=5))

            await workflow.execute_activity(
                "shuddho_agent_complete_v1", run_id,
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except (ActivityError, ApplicationError) as error:
            cause = error.cause if isinstance(error, ActivityError) else error
            code = cause.type if isinstance(cause, ApplicationError) else "agent_workflow_failed"
            message = str(cause.message) if isinstance(cause, ApplicationError) else "This agent run could not finish. Please try again."
            await workflow.execute_activity(
                "shuddho_agent_failed_v1", {"run_id": run_id, "code": code, "message": message},
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
