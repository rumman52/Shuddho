"""Deterministic Temporal definition. History carries IDs and safe status only."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError


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
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=3),
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
                    if status == "replan_required":
                        if replanned:
                            raise ApplicationError("The agent already used its one replan.", type="replan_limit")
                        replacement_count = await workflow.execute_activity(
                            "shuddho_agent_replan_v1", {"run_id": run_id, "from_ordinal": ordinal},
                            start_to_close_timeout=timedelta(seconds=45),
                            schedule_to_close_timeout=timedelta(minutes=2),
                            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=2),
                        )
                        count = ordinal - 1 + replacement_count
                        replanned = True
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
