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
from research_samples import SimulatedResearch
from services.coworker.drafting import DraftFailure
from services.coworker.runner import DocumentRunner
from services.coworker.worker import Activities, Dispatcher
from services.coworker.workflow import ReportEmailWorkflow, ResearchWorkflow, WorkServicesWorkflow


def make_worker(env, runner):
    activities = Activities(runner)
    return Worker(env.client, task_queue=runner.container.settings.task_queue,
                  workflows=[ReportEmailWorkflow, WorkServicesWorkflow, ResearchWorkflow],
                  activities=[activities.phase, activities.work_phase, activities.research_phase, activities.failed],
                  max_cached_workflows=0,
                  graceful_shutdown_timeout=timedelta(seconds=2))


async def run_handle(env, task_id):
    workflow_id = "shuddho-task-" + task_id
    execution = await env.client.get_workflow_handle(workflow_id).describe()
    return env.client.get_workflow_handle(workflow_id, run_id=execution.run_id)


@pytest.mark.parametrize("skill_id", ["report_email", "social", "presentation", "spreadsheet", "research"])
def test_worker_restart_after_saved_draft_does_not_repeat_model(container, skill_id):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            container.settings = replace(container.settings, work_services_enabled=True, artifact_services_enabled=True, research_services_enabled=True)
            container.repository.settings = container.settings
            task = new_task(container, skill_id=skill_id, **({"research": {"query": "public project update"}} if skill_id == "research" else {}))
            model = FakeModel() if skill_id == "report_email" else WorkModel()
            search = SimulatedResearch(container.settings)
            checkpoint = asyncio.Event()
            class LostAcknowledgement(DocumentRunner):
                async def draft(self, value):
                    await super().draft(value)
                    checkpoint.set()
                    raise RuntimeError("simulated worker loss after checkpoint")
            first = make_worker(env, LostAcknowledgement(container, model, research=search))
            first_run = asyncio.create_task(first.run())
            await Dispatcher(container, env.client).tick()
            await asyncio.wait_for(checkpoint.wait(), 30)
            await first.shutdown()
            await first_run
            assert container.repository.step(task["id"], "draft") is not None
            async with make_worker(env, DocumentRunner(container, model, research=search)):
                handle = await run_handle(env, task["id"])
                # A reattached handle doesn't get the test environment's
                # start_workflow interceptor. Unlock its virtual retry clock.
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
            value = container.repository.get_task(account(container), task["id"])
            assert value["state"] == "completed" and len(value["artifacts"]) == 4
            assert model.calls == 1
            assert search.calls == (1 if skill_id == "research" else 0)
            history = await handle.fetch_history()
            raw = history.to_json()
            assert "Team completed 12 reviews" not in raw
            assert "report.docx" not in raw
            assert "social-posts.docx" not in raw
            assert "example.org/project-update" not in raw and "public project update" not in raw
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


def test_saved_web_evidence_survives_worker_loss_without_researching(container):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            container.settings = replace(container.settings, research_services_enabled=True)
            container.repository.settings = container.settings
            task = new_task(container, skill_id="research", research={"query": "public project update"})
            search, model, checkpoint = SimulatedResearch(container.settings), WorkModel(), asyncio.Event()
            class LostSearchAcknowledgement(DocumentRunner):
                async def research(self, task):
                    await super().research(task)
                    checkpoint.set()
                    raise RuntimeError("simulated loss after search checkpoint")
            first = make_worker(env, LostSearchAcknowledgement(container, model, research=search))
            first_run = asyncio.create_task(first.run())
            await Dispatcher(container, env.client).tick()
            await asyncio.wait_for(checkpoint.wait(), 30)
            await first.shutdown()
            await first_run
            async with make_worker(env, DocumentRunner(container, model, research=search)):
                handle = await run_handle(env, task["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
            assert container.repository.get_task(account(container), task["id"])["state"] == "completed"
            assert search.calls == model.calls == 1
    asyncio.run(scenario())


def test_cancelled_search_stops_before_model_and_retains_unknown_credit(container):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            container.settings = replace(container.settings, research_services_enabled=True)
            container.repository.settings = container.settings
            task = new_task(container, skill_id="research", research={"query": "public project update"})
            entered, stopped = asyncio.Event(), asyncio.Event()
            class SlowSearch:
                async def retrieve(self, _options):
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        stopped.set()
            model = WorkModel()
            async with make_worker(env, DocumentRunner(container, model, research=SlowSearch())):
                await Dispatcher(container, env.client).tick()
                await asyncio.wait_for(entered.wait(), 30)
                container.repository.cancel(account(container), task["id"])
                await asyncio.wait_for((await run_handle(env, task["id"])).result(), 30)
            value = container.repository.get_task(account(container), task["id"])
            assert value["state"] == "cancelled" and stopped.is_set() and model.calls == 0
            assert value["usage"]["search"]["state"] == "unknown" and value["usage"]["search"]["accounted_credits"] == 1
    asyncio.run(scenario())
