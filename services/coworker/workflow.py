"""Deterministic Temporal definition. History carries IDs and safe status only."""
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError


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
