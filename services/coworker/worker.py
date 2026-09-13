"""Run separately from the interactive writing API: python -m services.coworker.worker."""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import timedelta

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
from .runner import DocumentRunner
from .workflow import ReportEmailWorkflow

logger = logging.getLogger("shuddho.coworker")


class Activities:
    def __init__(self, runner: DocumentRunner):
        self.runner = runner

    @activity.defn(name="shuddho_document_phase_v1")
    async def phase(self, value: dict):
        task_id = value["task_id"]
        operation = asyncio.create_task(self.runner.phase(task_id, value["phase"]))
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
            raise ApplicationError(error.message, type=error.code,
                                   non_retryable=not isinstance(error, DraftFailure) or not error.retryable) from None
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


class Dispatcher:
    def __init__(self, container: Container, client):
        self.container, self.client = container, client

    async def tick(self):
        repo = self.container.repository
        await asyncio.to_thread(repo.expire_tasks)
        for task_id in await asyncio.to_thread(repo.claim_outbox):
            task = await asyncio.to_thread(repo.worker_task, task_id, False)
            if task["state"] not in TERMINAL:
                try:
                    await self.client.start_workflow(
                        ReportEmailWorkflow.run, task_id, id="shuddho-task-" + task_id,
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
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(name, stop.set)
        except NotImplementedError:
            pass
    async with Worker(client, task_queue=settings.task_queue, workflows=[ReportEmailWorkflow],
                      activities=[activities.phase, activities.failed],
                      # Four short deterministic steps: replay is inexpensive.
                      # Avoid affinity to a departed worker during rollouts.
                      max_cached_workflows=0, max_concurrent_activities=4,
                      graceful_shutdown_timeout=timedelta(seconds=20)):
        await Dispatcher(container, client).run(stop)
    container.repository.sessions.kw["bind"].dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
