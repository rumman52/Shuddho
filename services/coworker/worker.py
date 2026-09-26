"""Run separately from the interactive writing API: python -m services.coworker.worker."""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timedelta

from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.worker import Worker

from .config import Settings
from .container import Container
from .drafting import DraftFailure
from .errors import CoworkerError
from .repository import TERMINAL
from .agent_runtime import AgentRuntime
from .automation_scheduler import AutomationScheduleReconciler
from .runner import DocumentRunner
from .workflow import AgentWorkflow, AgentWorkflowV2, AgentWorkflowV3, ApprovedActionWorkflow, AutomationOccurrenceWorkflow, ReportEmailWorkflow, ResearchWorkflow, WorkServicesWorkflow

logger = logging.getLogger("shuddho.coworker")
TRANSIENT_CAPACITY_ERRORS = {"provider_capacity_busy", "workspace_provider_busy"}


class ActionActivities:
    def __init__(self, service):
        self.service = service

    @activity.defn(name="shuddho_execute_action_v1")
    async def execute(self, action_id: str):
        try:
            await self.service.execute(action_id)
        except Exception:
            # Never serialize OAuth tokens or recipient/content into failures.
            raise ApplicationError("The action worker was interrupted.", type="action_interrupted") from None

    @activity.defn(name="shuddho_action_interrupted_v1")
    async def interrupted(self, action_id: str):
        try:
            await asyncio.to_thread(self.service.repo.finish, action_id, "outcome_unknown", error_code="worker_interrupted")
        except Exception:
            raise ApplicationError("Could not record action status.", type="action_status_unavailable") from None


class AutomationActivities:
    def __init__(self, repository):
        self.repository = repository

    @activity.defn(name="shuddho_accept_automation_occurrence_v1")
    async def accept(self, value: dict):
        try:
            due_at = datetime.fromisoformat(str(value["due_at"]).replace("Z", "+00:00"))
            return await asyncio.to_thread(
                self.repository.accept_occurrence,
                str(value["automation_id"]),
                int(value["revision"]),
                due_at,
            )
        except CoworkerError as error:
            raise ApplicationError(error.message, type=error.code, non_retryable=True) from None
        except Exception:
            raise ApplicationError("Could not accept the scheduled occurrence.", type="automation_accept_unavailable") from None


class Activities:
    def __init__(self, runner: DocumentRunner):
        self.runner = runner

    @activity.defn(name="shuddho_document_phase_v1")
    async def phase(self, value: dict):
        return await self.run_phase(value, legacy=True)

    @activity.defn(name="shuddho_work_phase_v1")
    async def work_phase(self, value: dict):
        return await self.run_phase(value, legacy=False)

    @activity.defn(name="shuddho_research_phase_v1")
    async def research_phase(self, value: dict):
        return await self.run_phase(value, legacy=False, research=True)

    async def checked_phase(self, value: dict, legacy: bool, research: bool = False):
        task = await asyncio.to_thread(self.runner.repo.worker_task, value["task_id"], False)
        if (task["workflow_version"] == "report_email_v1") != legacy or (task["skill_id"] == "research") != research:
            raise CoworkerError("workflow_version", "The task was routed to an incompatible workflow. Please contact support.")
        await self.runner.phase(value["task_id"], value["phase"])

    async def run_phase(self, value: dict, *, legacy: bool, research: bool = False):
        task_id = value["task_id"]
        operation = asyncio.create_task(self.checked_phase(value, legacy, research))
        try:
            while True:
                activity.heartbeat()
                done, _ = await asyncio.wait({operation}, timeout=1)
                if done:
                    await operation
                    return
                task = await asyncio.to_thread(self.runner.repo.worker_task, task_id, False)
                if task["state"] not in {"completed", "needs_input"}:
                    await asyncio.to_thread(self.runner.repo.worker_task, task_id)
        except CoworkerError as error:
            retryable = (
                error.code in TRANSIENT_CAPACITY_ERRORS
                or isinstance(error, DraftFailure) and error.retryable
            )
            raise ApplicationError(
                error.message, type=error.code, non_retryable=not retryable
            ) from None
        except asyncio.CancelledError:
            raise
        except Exception:
            # Keep SQL parameters, source text, object keys, and provider bodies
            # out of Temporal failures and application logs.
            logger.error("Coworker phase failed task=%s phase=%s", task_id, value["phase"])
            raise ApplicationError("A task service was unavailable. Please try again.", type="task_service_unavailable") from None
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)

    @activity.defn(name="shuddho_document_failed_v1")
    async def failed(self, value: dict):
        try:
            await asyncio.to_thread(self.runner.repo.fail, value["task_id"], value["code"], value["message"])
        except Exception:
            raise ApplicationError("Could not update task status.", type="status_unavailable") from None


class AgentActivities:
    def __init__(self, runtime: AgentRuntime):
        self.runtime = runtime

    @activity.defn(name="shuddho_agent_plan_v1")
    async def plan(self, run_id: str):
        try:
            return await self.runtime.plan_for_worker(run_id)
        except CoworkerError as error:
            raise ApplicationError(
                error.message, type=error.code,
                non_retryable=error.code not in TRANSIENT_CAPACITY_ERRORS,
            ) from None
        except Exception:
            logger.error("Agent planning failed run=%s", run_id)
            raise ApplicationError("Agent planning is temporarily unavailable.", type="agent_planning_unavailable") from None

    @activity.defn(name="shuddho_agent_replan_v1")
    async def replan(self, value: dict):
        try:
            return await self.runtime.replan(
                value["run_id"], int(value["from_ordinal"]), str(value.get("reason", "capability_changed"))
            )
        except CoworkerError as error:
            raise ApplicationError(
                error.message, type=error.code,
                non_retryable=error.code not in TRANSIENT_CAPACITY_ERRORS,
            ) from None
        except Exception:
            logger.error("Agent replanning failed run=%s", value.get("run_id"))
            raise ApplicationError("Agent replanning is temporarily unavailable.", type="agent_replanning_unavailable") from None

    @activity.defn(name="shuddho_agent_decide_v3")
    async def decide_v3(self, run_id: str):
        try:
            return await self.runtime.decide_v3(run_id)
        except CoworkerError as error:
            raise ApplicationError(
                error.message, type=error.code,
                non_retryable=error.code not in TRANSIENT_CAPACITY_ERRORS,
            ) from None
        except Exception:
            logger.error("Agent Runtime v3 decision failed run=%s", run_id)
            raise ApplicationError(
                "Agent Runtime v3 planning is temporarily unavailable.",
                type="agent_v3_planning_unavailable",
            ) from None

    @activity.defn(name="shuddho_agent_readiness_v2")
    async def readiness(self, value: dict):
        try:
            return await asyncio.to_thread(
                self.runtime.repo.runnable_steps, str(value["run_id"]), int(value["limit"])
            )
        except CoworkerError as error:
            raise ApplicationError(error.message, type=error.code, non_retryable=True) from None
        except Exception:
            logger.error("Agent readiness failed run=%s", value.get("run_id"))
            raise ApplicationError("Agent scheduling is temporarily unavailable.", type="agent_scheduling_unavailable") from None

    @activity.defn(name="shuddho_agent_step_v1")
    async def step(self, value: dict):
        run_id, ordinal = value["run_id"], int(value["ordinal"])
        operation = asyncio.create_task(self.runtime.execute_step(run_id, ordinal))
        try:
            while True:
                activity.heartbeat()
                done, _ = await asyncio.wait({operation}, timeout=1)
                if done:
                    return await operation
        except CoworkerError as error:
            retryable = (
                error.code in TRANSIENT_CAPACITY_ERRORS
                or isinstance(error, DraftFailure) and error.retryable
            )
            raise ApplicationError(
                error.message, type=error.code, non_retryable=not retryable
            ) from None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Agent step failed run=%s ordinal=%s", run_id, ordinal)
            raise ApplicationError("An agent tool was unavailable. Please try again.", type="agent_tool_unavailable") from None
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)

    @activity.defn(name="shuddho_agent_complete_v1")
    async def complete(self, run_id: str):
        try:
            await asyncio.to_thread(self.runtime.complete, run_id)
        except CoworkerError as error:
            raise ApplicationError(error.message, type=error.code, non_retryable=True) from None
        except Exception:
            raise ApplicationError("Could not finalize the agent run.", type="agent_status_unavailable") from None

    @activity.defn(name="shuddho_agent_failed_v1")
    async def failed(self, value: dict):
        try:
            await asyncio.to_thread(self.runtime.fail, value["run_id"], value["code"], value["message"])
        except Exception:
            raise ApplicationError("Could not record agent status.", type="agent_status_unavailable") from None


class Dispatcher:
    def __init__(self, container: Container, client):
        self.container, self.client = container, client
        self.automation_schedules = AutomationScheduleReconciler(client, container.settings.task_queue)

    async def dispatch_agent_run(self, run_id: str):
        agent = self.container.agent
        run = await asyncio.to_thread(agent.worker_run, run_id)
        if run["state"] not in {"completed", "failed", "cancelled"}:
            try:
                runtime_version = int(run.get("runtime_version", 0))
                if runtime_version == 3:
                    workflow_entry = AgentWorkflowV3.run
                    workflow_input = {"run_id": run_id}
                elif runtime_version == 2:
                    workflow_entry = AgentWorkflowV2.run
                    workflow_input = {
                        "run_id": run_id,
                        "max_parallel_steps": self.container.settings.max_agent_parallel_steps,
                    }
                elif runtime_version == 1:
                    workflow_entry = AgentWorkflow.run
                    workflow_input = run_id
                else:
                    # Migration-safe legacy behavior: rows created before PA-03
                    # retain the old deployment-time v1/v2 routing rule.
                    parallel = (
                        self.container.settings.agent_dependency_graph_enabled
                        and self.container.settings.agent_parallel_execution_enabled
                    )
                    workflow_entry = AgentWorkflowV2.run if parallel else AgentWorkflow.run
                    workflow_input = (
                        {"run_id": run_id, "max_parallel_steps": self.container.settings.max_agent_parallel_steps}
                        if parallel else run_id
                    )
                await self.client.start_workflow(
                    workflow_entry, workflow_input, id="shuddho-agent-" + run_id,
                    task_queue=self.container.settings.task_queue,
                    execution_timeout=timedelta(seconds=self.container.settings.agent_run_timeout_seconds),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    rpc_timeout=timedelta(seconds=10),
                )
            except WorkflowAlreadyStartedError:
                pass
        await asyncio.to_thread(agent.delivered, run_id)

    async def tick(self):
        repo = self.container.repository
        actions = self.container.actions.repo
        agent = self.container.agent
        automations = self.container.automations
        # Reconciliation runs even while the feature kill switch is off so
        # previously active Temporal Schedules are paused and remain recoverable.
        for desired in await asyncio.to_thread(automations.claim_reconciliation):
            try:
                enabled = await self.automation_schedules.apply(desired)
                await asyncio.to_thread(
                    automations.reconciliation_applied,
                    desired["id"],
                    int(desired["desired_revision"]),
                    enabled,
                )
            except Exception:
                logger.exception("Automation schedule reconciliation failed.")
                await asyncio.to_thread(
                    automations.reconciliation_failed,
                    desired["id"],
                    int(desired["desired_revision"]),
                    "temporal_schedule_unavailable",
                )
        if self.container.settings.automations_enabled:
            for buffered in await asyncio.to_thread(automations.claim_buffered_occurrences):
                try:
                    await asyncio.to_thread(
                        automations.accept_occurrence,
                        str(buffered["automation_id"]),
                        int(buffered["revision"]),
                        datetime.fromisoformat(str(buffered["due_at"]).replace("Z", "+00:00")),
                    )
                except Exception:
                    logger.exception("Buffered automation occurrence could not resume.")
        # Accepted work remains visible even after the admission kill switch is
        # disabled; notification delivery itself grants no new execution authority.
        for notification_id in await asyncio.to_thread(automations.claim_notifications):
            await asyncio.to_thread(automations.deliver_notification, notification_id)
        for action_id in await asyncio.to_thread(actions.claim_outbox):
            try:
                await self.client.start_workflow(
                    ApprovedActionWorkflow.run, action_id, id="shuddho-action-" + action_id,
                    task_queue=self.container.settings.task_queue, execution_timeout=timedelta(minutes=6),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE, rpc_timeout=timedelta(seconds=10),
                )
            except WorkflowAlreadyStartedError:
                pass
            await asyncio.to_thread(actions.delivered, action_id)
        if self.container.settings.connector_reads_enabled:
            for subscription in await asyncio.to_thread(
                self.container.connector_reads.repo.claim_renewals
            ):
                await self.container.connector_reads.renew_subscription(subscription)
            for event in await asyncio.to_thread(
                self.container.connector_reads.repo.claim_events
            ):
                await self.container.connector_reads.process_event(event)
        if self.container.settings.agent_runtime_enabled:
            for run_id in await asyncio.to_thread(agent.claim_outbox):
                await self.dispatch_agent_run(run_id)
        await asyncio.to_thread(repo.expire_tasks)
        for task_id in await asyncio.to_thread(repo.claim_outbox):
            task = await asyncio.to_thread(repo.worker_task, task_id, False)
            if task["state"] not in TERMINAL:
                try:
                    await self.client.start_workflow(
                        (ReportEmailWorkflow.run if task["skill_id"] == "report_email" else
                         ResearchWorkflow.run if task["skill_id"] == "research" else WorkServicesWorkflow.run),
                        task_id, id="shuddho-task-" + task_id,
                        task_queue=self.container.settings.task_queue,
                        execution_timeout=timedelta(seconds=self.container.settings.task_timeout_seconds),
                        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                        rpc_timeout=timedelta(seconds=10),
                    )
                except WorkflowAlreadyStartedError:
                    pass  # Crash after engine acceptance, before outbox acknowledgement.
            await asyncio.to_thread(repo.delivered, task_id)

    async def run(self, stop: asyncio.Event):
        cleanup_at = 0
        while not stop.is_set():
            try:
                await self.tick()
                now = asyncio.get_running_loop().time()
                if now >= cleanup_at:
                    for key in await asyncio.to_thread(self.container.repository.expired_uploads):
                        await asyncio.to_thread(self.container.storage.delete, key)
                        await asyncio.to_thread(self.container.repository.upload_cleaned, key)
                    cleanup_at = now + 300
            except Exception:
                logger.error("Coworker dispatch unavailable; pending tasks remain queued.")
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except TimeoutError:
                pass


async def main():
    from dotenv import load_dotenv
    load_dotenv()
    settings = Settings.from_env()
    container = Container.create(settings)
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace,
                                  api_key=settings.temporal_api_key or None, tls=settings.temporal_tls)
    activities = Activities(DocumentRunner(container))
    action_activities = ActionActivities(container.actions)
    agent_activities = AgentActivities(AgentRuntime(container, DocumentRunner(container)))
    automation_activities = AutomationActivities(container.automations)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(name, stop.set)
        except NotImplementedError:
            pass
    async with Worker(client, task_queue=settings.task_queue, workflows=[ReportEmailWorkflow, WorkServicesWorkflow, ResearchWorkflow, ApprovedActionWorkflow, AutomationOccurrenceWorkflow, AgentWorkflow, AgentWorkflowV2, AgentWorkflowV3],
                      activities=[activities.phase, activities.work_phase, activities.research_phase, activities.failed, action_activities.execute, action_activities.interrupted,
                                  agent_activities.plan, agent_activities.replan, agent_activities.decide_v3, agent_activities.readiness, agent_activities.step, agent_activities.complete, agent_activities.failed, automation_activities.accept],
                      # Four short deterministic steps: replay is inexpensive.
                      # Avoid affinity to a departed worker during rollouts.
                      max_cached_workflows=0, max_concurrent_activities=4,
                      graceful_shutdown_timeout=timedelta(seconds=20)):
        await Dispatcher(container, client).run(stop)
    container.repository.sessions.kw["bind"].dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
