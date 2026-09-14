"""Real engine tests, enabled in the dedicated coworker CI job."""
import asyncio
import os
from dataclasses import replace
from datetime import timedelta

import pytest

pytest.importorskip("temporalio")
pytestmark = [pytest.mark.coworker_integration, pytest.mark.skipif(os.getenv("SHUDDHO_TEMPORAL_TESTS") != "true", reason="Set SHUDDHO_TEMPORAL_TESTS=true to run the Temporal test server")]

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from test_coworker import container, account, new_task, FakeModel
from coworker_samples import WorkModel
from services.coworker.drafting import DraftFailure
from services.coworker.runner import DocumentRunner
from services.coworker.worker import Activities, Dispatcher
from services.coworker.workflow import ReportEmailWorkflow, WorkServicesWorkflow


def make_worker(env, runner):
    activities = Activities(runner)
    return Worker(env.client, task_queue=runner.container.settings.task_queue,
                  workflows=[ReportEmailWorkflow, WorkServicesWorkflow], activities=[activities.phase, activities.work_phase, activities.failed],
                  max_cached_workflows=0,
                  graceful_shutdown_timeout=timedelta(seconds=2))


async def run_handle(env, task_id):
    workflow_id = "shuddho-task-" + task_id
    execution = await env.client.get_workflow_handle(workflow_id).describe()
    return env.client.get_workflow_handle(workflow_id, run_id=execution.run_id)


@pytest.mark.parametrize("skill_id", ["report_email", "social"])
def test_worker_restart_after_saved_draft_does_not_repeat_model(container, skill_id):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            container.settings = replace(container.settings, work_services_enabled=True)
            container.repository.settings = container.settings
            task = new_task(container, skill_id=skill_id)
            model = FakeModel() if skill_id == "report_email" else WorkModel()
            checkpoint = asyncio.Event()
            class LostAcknowledgement(DocumentRunner):
                async def draft(self, value):
                    await super().draft(value)
                    checkpoint.set()
                    raise RuntimeError("simulated worker loss after checkpoint")
            first = make_worker(env, LostAcknowledgement(container, model))
            first_run = asyncio.create_task(first.run())
            await Dispatcher(container, env.client).tick()
            await asyncio.wait_for(checkpoint.wait(), 30)
            await first.shutdown()
            await first_run
            assert container.repository.step(task["id"], "draft") is not None
            async with make_worker(env, DocumentRunner(container, model)):
                handle = await run_handle(env, task["id"])
                # A reattached handle doesn't get the test environment's
                # start_workflow interceptor. Unlock its virtual retry clock.
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
            value = container.repository.get_task(account(container), task["id"])
            assert value["state"] == "completed" and len(value["artifacts"]) == 4
            assert model.calls == 1
            history = await handle.fetch_history()
            raw = history.to_json()
            assert "Team completed 12 reviews" not in raw
            assert "report.docx" not in raw
            assert "social-posts.docx" not in raw
    asyncio.run(scenario())


def test_cancellation_stops_inflight_step_and_preserves_unknown_usage(container):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            owner = account(container)
            task = new_task(container, owner)
            entered = asyncio.Event()
            stopped = asyncio.Event()
            class SlowModel(FakeModel):
                async def generate(self, *_args):
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        stopped.set()
            async with make_worker(env, DocumentRunner(container, SlowModel())):
                await Dispatcher(container, env.client).tick()
                await asyncio.wait_for(entered.wait(), 30)
                container.repository.cancel(owner, task["id"])
                await asyncio.wait_for((await run_handle(env, task["id"])).result(), 30)
            value = container.repository.get_task(owner, task["id"])
            assert stopped.is_set() and value["state"] == "cancelled"
            assert value["usage"]["accounted_tokens"] > 0 and value["artifacts"] == []
    asyncio.run(scenario())


def test_provider_outage_retries_twice_then_has_terminal_error(container):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            owner = account(container)
            task = new_task(container, owner)
            class Unavailable(FakeModel):
                async def generate(self, *_args):
                    self.calls += 1
                    raise DraftFailure("model_busy", "The AI service is busy. Please retry.", retryable=True)
            model = Unavailable()
            async with make_worker(env, DocumentRunner(container, model)):
                await Dispatcher(container, env.client).tick()
                await asyncio.wait_for((await run_handle(env, task["id"])).result(), 30)
            value = container.repository.get_task(owner, task["id"])
            assert model.calls == 2 and value["state"] == "failed"
            assert value["error_code"] == "model_busy"
            assert value["usage"]["model_attempts"] == 2
    asyncio.run(scenario())


def test_wrong_workflow_entry_cannot_run_or_charge_a_service_task(container):
    async def scenario():
        container.settings = replace(container.settings, work_services_enabled=True)
        container.repository.settings = container.settings
        task = new_task(container, skill_id="email")
        model = WorkModel()
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, DocumentRunner(container, model)):
                await env.client.execute_workflow(ReportEmailWorkflow.run, task["id"], id="wrong-route-" + task["id"],
                                                  task_queue=container.settings.task_queue)
        saved = container.repository.get_task(account(container), task["id"])
        assert saved["state"] == "failed" and saved["error_code"] == "workflow_version"
        assert model.calls == 0 and saved["usage"]["model_attempts"] == 0
    asyncio.run(scenario())
