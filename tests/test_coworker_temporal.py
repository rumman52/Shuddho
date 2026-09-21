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
from services.coworker.errors import CoworkerError
from services.coworker.runner import DocumentRunner
from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate
from services.coworker.worker import ActionActivities, Activities, AgentActivities, Dispatcher
from services.coworker.workflow import AgentWorkflow, AgentWorkflowV2, ApprovedActionWorkflow, ReportEmailWorkflow, ResearchWorkflow, WorkServicesWorkflow


def make_worker(env, runner, agent_runtime=None):
    activities = Activities(runner)
    actions = ActionActivities(runner.container.actions)
    agent = AgentActivities(agent_runtime or AgentRuntime(runner.container, runner))
    return Worker(env.client, task_queue=runner.container.settings.task_queue,
                  workflows=[ReportEmailWorkflow, WorkServicesWorkflow, ResearchWorkflow, ApprovedActionWorkflow, AgentWorkflow, AgentWorkflowV2],
                  activities=[activities.phase, activities.work_phase, activities.research_phase, activities.failed, actions.execute, actions.interrupted,
                              agent.plan, agent.replan, agent.readiness, agent.step, agent.complete, agent.failed],
                  max_cached_workflows=0,
                  graceful_shutdown_timeout=timedelta(seconds=2))


@pytest.mark.parametrize("capability", ["email", "calendar"])
def test_action_worker_restart_after_provider_acceptance_never_resends(container, capability):
    from action_samples import enable_actions, approved
    from services.coworker.google_actions import SEND_URL, EVENTS_URL
    async def scenario():
        provider = enable_actions(container)
        repo = container.actions.repo
        owner = account(container)
        value = approved(repo, owner, capability)
        accepted = asyncio.Event()
        execute = container.actions.provider.execute
        async def interrupted(action, token):
            await execute(action, token)
            accepted.set()
            # Lose both the response and the activity acknowledgement.
            await asyncio.Event().wait()
        container.actions.provider.execute = interrupted
        async with await WorkflowEnvironment.start_time_skipping() as env:
            first = make_worker(env, DocumentRunner(container, FakeModel()))
            first_run = asyncio.create_task(first.run())
            await Dispatcher(container, env.client).tick()
            await asyncio.wait_for(accepted.wait(), 30)
            await first.shutdown()
            await first_run
            assert repo.get(owner, value["id"])["state"] == "executing"
            container.actions.provider.execute = execute
            async with make_worker(env, DocumentRunner(container, FakeModel())):
                handle = env.client.get_workflow_handle("shuddho-action-" + value["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
            result = repo.get(owner, value["id"])
            assert result["state"] == ("succeeded" if capability == "calendar" else "outcome_unknown")
            assert len([r for r in provider.requests if r.method == "POST" and str(r.url).split("?")[0] in {SEND_URL, EVENTS_URL}]) == 1
            history = (await handle.fetch_history()).to_json()
            for private in ["simulated-refresh-token", "simulated-access-token", "recipient@example.org", "guest@example.org", "alice@example.test", "Review twelve items"]:
                assert private not in history
    asyncio.run(scenario())


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



def test_agent_workflow_executes_bounded_email_draft_once(container):
    async def scenario():
        enabled = replace(container.settings, agent_runtime_enabled=True, work_services_enabled=True)
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Draft a professional follow-up email to the team.",
            output_language="en",
        ), "agent-temporal-email")
        model = WorkModel()
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, DocumentRunner(container, model)):
                await Dispatcher(container, env.client).tick()
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
            saved = container.agent.get(owner, run["id"])
            assert saved["state"] == "completed"
            assert [step["tool"] for step in saved["steps"]] == ["email.draft"]
            assert saved["tool_invocations"][0]["state"] == "completed"
            assert saved["tool_invocations"][0]["receipt"]["resource_type"] == "task"
            assert model.calls == 1
            history = (await handle.fetch_history()).to_json()
            assert "Draft a professional follow-up email to the team." not in history
    asyncio.run(scenario())


def test_agent_worker_restart_reuses_child_task_checkpoint(container):
    async def scenario():
        enabled = replace(container.settings, agent_runtime_enabled=True, work_services_enabled=True)
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Draft a professional email update.",
            output_language="en",
        ), "agent-temporal-restart")
        model = WorkModel()
        checkpoint = asyncio.Event()

        class LostAfterDraft(DocumentRunner):
            async def draft(self, task):
                await super().draft(task)
                checkpoint.set()
                await asyncio.Event().wait()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            first = make_worker(env, LostAfterDraft(container, model))
            first_run = asyncio.create_task(first.run())
            await Dispatcher(container, env.client).tick()
            await asyncio.wait_for(checkpoint.wait(), 30)
            await first.shutdown()
            await first_run

            saved = container.agent.get(owner, run["id"])
            task_id = saved["steps"][0]["state"] == "running" and container.agent.step_resource(run["id"], 1)["resource_id"]
            assert task_id
            assert container.repository.step(task_id, "draft") is not None

            async with make_worker(env, DocumentRunner(container, model)):
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
            final = container.agent.get(owner, run["id"])
            assert final["state"] == "completed"
            assert model.calls == 1
    asyncio.run(scenario())



def test_agent_action_waits_for_exact_approval_then_resumes_once(container):
    from action_samples import enable_actions, connected, action_request
    async def scenario():
        provider = enable_actions(container)
        enabled = replace(container.settings, agent_runtime_enabled=True, work_services_enabled=True)
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        container.actions.repo.settings = enabled
        owner = account(container)
        connection = connected(container.actions.repo, owner)
        action = container.actions.repo.prepare(owner, action_request(connection), "agent-temporal-action-preview")
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Complete the attached external action.",
            action_ids=[action["id"]],
            output_language="en",
        ), "agent-temporal-action-run")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, DocumentRunner(container, WorkModel())):
                await Dispatcher(container, env.client).tick()
                for _ in range(100):
                    if container.agent.get(owner, run["id"])["state"] == "awaiting_approval":
                        break
                    await asyncio.sleep(0.05)
                waiting = container.agent.get(owner, run["id"])
                assert waiting["state"] == "awaiting_approval"
                assert waiting["steps"][0]["tool"] == "email.send"
                assert waiting["tool_invocations"][0]["state"] == "awaiting_approval"
                assert provider.sent == []

                approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
                assert approved["state"] == "queued"
                await Dispatcher(container, env.client).tick()

                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)

            final = container.agent.get(owner, run["id"])
            assert final["state"] == "completed"
            assert final["tool_invocations"][0]["state"] == "completed"
            receipt = final["tool_invocations"][0]["receipt"]
            assert receipt["resource_type"] == "action"
            assert receipt["resource_id"] == action["id"]
            assert receipt["summary"]["provider_confirmed"] is True
            assert len(provider.sent) == 1
            history = (await handle.fetch_history()).to_json()
            for private in ["recipient@example.org", "private@example.org", "প্রকল্পের অগ্রগতি", "simulated-access-token"]:
                assert private not in history
    asyncio.run(scenario())


def test_agent_action_cancel_before_approval_never_dispatches(container):
    from action_samples import enable_actions, connected, action_request
    provider = enable_actions(container)
    enabled = replace(container.settings, agent_runtime_enabled=True, work_services_enabled=True)
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    container.actions.repo.settings = enabled
    owner = account(container)
    connection = connected(container.actions.repo, owner)
    action = container.actions.repo.prepare(owner, action_request(connection), "agent-cancel-action-preview")
    run, _ = container.agent.create(owner, AgentRunCreate(
        goal="Complete the attached external action.",
        action_ids=[action["id"]],
        output_language="en",
    ), "agent-cancel-action-run")
    container.agent.save_plan(owner, run["id"], [
        __import__("services.coworker.agent_schemas", fromlist=["AgentPlanStep"]).AgentPlanStep(
            tool="email.send", arguments={"action_id": action["id"]}
        )
    ])
    container.agent.action_waiting(run["id"], 1, action["id"], "awaiting_approval")
    cancelled = container.agent.cancel(owner, run["id"])
    assert cancelled["state"] == "cancelled"
    assert container.actions.repo.get(owner, action["id"])["state"] == "cancelled"
    assert container.actions.repo.claim_outbox() == []
    assert provider.sent == []



def test_agent_workflow_replans_once_when_capability_changes(container):
    from services.coworker.agent_schemas import AgentPlannerProposal
    async def scenario():
        enabled = replace(container.settings, agent_runtime_enabled=True, intelligent_planner_enabled=True,
                          work_services_enabled=True, max_agent_planner_calls=2,
                          agent_planner_token_budget=16000)
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Draft a professional follow-up email.", output_language="en"
        ), "temporal-intelligent-replan")

        class Planner:
            def __init__(self):
                self.calls = 0
            async def propose(self, *_args, **kwargs):
                self.calls += 1
                tool = "email.draft" if self.calls == 1 else "report.create"
                return AgentPlannerProposal.model_validate({
                    "steps": [{"tool": tool, "objective": "Prepare the requested professional update."}]
                }), 50, 1

        gate = asyncio.Event()
        planner = Planner()
        runner = DocumentRunner(container, FakeModel())

        class GatedRuntime(AgentRuntime):
            async def execute_step(self, run_id, ordinal):
                if planner.calls == 1:
                    gate.set()
                    await asyncio.sleep(0.1)
                return await super().execute_step(run_id, ordinal)

        runtime = GatedRuntime(container, runner, planner=planner)
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, runner, runtime):
                await Dispatcher(container, env.client).tick()
                await asyncio.wait_for(gate.wait(), 30)
                changed = replace(enabled, work_services_enabled=False)
                container.settings = changed
                container.repository.settings = changed
                container.agent.settings = changed
                runtime.container.settings = changed
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
                history = (await handle.fetch_history()).to_json()
        saved = container.agent.get(owner, run["id"])
        assert saved["state"] == "completed"
        assert saved["planner_mode"] == "replanned"
        assert saved["planner_calls"] == 2
        assert planner.calls == 2
        assert [step["tool"] for step in saved["steps"]] == ["report.create"]
        assert "Draft a professional follow-up email." not in history
    asyncio.run(scenario())



def test_agent_workflow_chains_prior_task_output_without_temporal_payload_leak(container):
    from services.coworker.agent_schemas import AgentPlannerProposal

    async def scenario():
        enabled = replace(
            container.settings,
            agent_runtime_enabled=True,
            intelligent_planner_enabled=True,
            agent_handoffs_enabled=True,
            work_services_enabled=True,
        )
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Create a project document and then draft a follow-up email.",
            output_language="en",
        ), "temporal-agent-handoff")

        class Planner:
            async def propose(self, *_args, **_kwargs):
                return AgentPlannerProposal.model_validate({
                    "steps": [
                        {"tool": "document.create", "objective": "Create the project document."},
                        {"tool": "email.draft", "objective": "Draft the follow-up email."},
                    ]
                }), 40, 1

        runner = DocumentRunner(container, WorkModel())
        runtime = AgentRuntime(container, runner, planner=Planner())
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, runner, runtime):
                await Dispatcher(container, env.client).tick()
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
                history = (await handle.fetch_history()).to_json()

        saved = container.agent.get(owner, run["id"])
        assert saved["state"] == "completed"
        assert [step["tool"] for step in saved["steps"]] == ["document.create", "email.draft"]
        handoff = saved["tool_invocations"][1]["receipt"]["summary"]["handoff"]
        assert len(handoff) == 1
        assert handoff[0]["tool"] == "document.create"
        assert handoff[0]["ordinal"] == 1
        assert "The team completed 12 reviews." not in history
        assert "Project update" not in history

    asyncio.run(scenario())


def test_agent_workflow_replans_remaining_steps_after_incomplete_result(container):
    from services.coworker.agent_schemas import AgentPlannerProposal

    async def scenario():
        enabled = replace(
            container.settings,
            agent_runtime_enabled=True,
            intelligent_planner_enabled=True,
            agent_outcome_replan_enabled=True,
            work_services_enabled=True,
            max_agent_planner_calls=2,
            agent_planner_token_budget=16000,
        )
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Create a project document and then draft a follow-up email.",
            output_language="en",
        ), "temporal-outcome-replan")

        class Planner:
            def __init__(self):
                self.calls = []
            async def propose(self, *_args, **kwargs):
                self.calls.append(kwargs.get("reason"))
                steps = (
                    [
                        {"tool": "document.create", "objective": "Create the project document."},
                        {"tool": "email.draft", "objective": "Draft the follow-up email."},
                    ]
                    if len(self.calls) == 1 else
                    [{"tool": "social.draft", "objective": "Prepare a concise update despite missing details."}]
                )
                return AgentPlannerProposal.model_validate({"steps": steps}), 40, 1

        planner = Planner()
        runner = DocumentRunner(container, WorkModel(missing=True))
        runtime = AgentRuntime(container, runner, planner=planner)
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, runner, runtime):
                await Dispatcher(container, env.client).tick()
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)
                history = (await handle.fetch_history()).to_json()

        saved = container.agent.get(owner, run["id"])
        assert saved["state"] == "completed"
        assert saved["planner_calls"] == 2
        assert planner.calls == ["initial", "result_incomplete"]
        assert [step["tool"] for step in saved["steps"]] == ["document.create", "social.draft"]
        assert saved["steps"][0]["state"] == "completed"
        assert "Please provide the missing recipient." not in history
        assert "The team completed 12 reviews." not in history

    asyncio.run(scenario())


def test_agent_dependency_graph_is_server_owned_and_blocks_out_of_order_execution(container):
    from coworker_samples import WorkModel
    from services.coworker.agent_runtime import AgentRuntime
    from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate

    enabled = replace(
        container.settings,
        agent_runtime_enabled=True,
        agent_dependency_graph_enabled=True,
        work_services_enabled=True,
    )
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    owner = account(container)
    run, _ = container.agent.create(owner, AgentRunCreate(
        goal="Create a document and then an email draft.", output_language="en"
    ), "agent-dependency-graph")
    saved = container.agent.save_plan(owner, run["id"], [
        AgentPlanStep(tool="document.create", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
        AgentPlanStep(tool="email.draft", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
    ])
    assert saved["steps"][0]["depends_on"] == []
    assert saved["steps"][1]["depends_on"] == [1]
    runtime = AgentRuntime(container, DocumentRunner(container, WorkModel()))
    with pytest.raises(CoworkerError) as blocked:
        asyncio.run(runtime.execute_step(run["id"], 2))
    assert blocked.value.code == "dependency_blocked"
    asyncio.run(runtime.execute_step(run["id"], 1))
    assert container.agent.dependency_state(owner, run["id"], 2)["ready"] is True


def test_agent_dependency_graph_flag_off_preserves_linear_runtime_contract(container):
    from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate

    enabled = replace(
        container.settings,
        agent_runtime_enabled=True,
        agent_dependency_graph_enabled=False,
        work_services_enabled=True,
    )
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    owner = account(container)
    run, _ = container.agent.create(owner, AgentRunCreate(
        goal="Create a document and email draft.", output_language="en"
    ), "agent-dependency-graph-off")
    saved = container.agent.save_plan(owner, run["id"], [
        AgentPlanStep(tool="document.create", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
        AgentPlanStep(tool="email.draft", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
    ])
    assert all(step["depends_on"] == [] for step in saved["steps"])
    assert container.agent.dependency_state(owner, run["id"], 2)["ready"] is True


def test_agent_dependency_graph_replan_rebuilds_only_unstarted_edges(container):
    from coworker_samples import WorkModel
    from services.coworker.agent_runtime import AgentRuntime
    from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate

    enabled = replace(
        container.settings,
        agent_runtime_enabled=True,
        agent_dependency_graph_enabled=True,
        work_services_enabled=True,
    )
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    owner = account(container)
    run, _ = container.agent.create(owner, AgentRunCreate(
        goal="Create three work outputs.", output_language="en"
    ), "agent-dependency-replan")
    container.agent.save_plan(owner, run["id"], [
        AgentPlanStep(tool="document.create", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
        AgentPlanStep(tool="social.draft", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
        AgentPlanStep(tool="email.draft", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
    ])
    runtime = AgentRuntime(container, DocumentRunner(container, WorkModel()))
    asyncio.run(runtime.execute_step(run["id"], 1))
    replaced = container.agent.replace_remaining_plan(owner, run["id"], 2, [
        AgentPlanStep(tool="meeting.prepare", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
        AgentPlanStep(tool="email.draft", arguments={
            "instruction": run["goal"], "notes": "", "document_ids": [], "output_language": "en",
        }),
    ])
    assert replaced["steps"][0]["state"] == "completed"
    assert replaced["steps"][1]["depends_on"] == [1]
    assert replaced["steps"][2]["depends_on"] == [2]


def test_agent_v2_fans_out_two_research_steps_then_fans_in(container):
    async def scenario():
        enabled = replace(
            container.settings,
            agent_runtime_enabled=True,
            agent_dependency_graph_enabled=True,
            agent_parallel_execution_enabled=True,
            research_services_enabled=True,
            work_services_enabled=True,
            max_agent_parallel_steps=2,
        )
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Research two sources and create a project document.", output_language="en"
        ), "agent-parallel-fan-in")
        saved = container.agent.save_plan(owner, run["id"], [
            AgentPlanStep(tool="research.search", arguments={
                "instruction": "Research the first public update.", "notes": "", "document_ids": [],
                "output_language": "en", "query": "first public project update", "time_range": "any",
            }),
            AgentPlanStep(tool="research.search", arguments={
                "instruction": "Research the second public update.", "notes": "", "document_ids": [],
                "output_language": "en", "query": "second public project update", "time_range": "any",
            }),
            AgentPlanStep(tool="document.create", arguments={
                "instruction": "Create the combined project document.", "notes": "",
                "document_ids": [], "output_language": "en",
            }),
        ])
        assert [step["depends_on"] for step in saved["steps"]] == [[], [], [1, 2]]

        entered = set()
        finished = set()
        both_started = asyncio.Event()
        runner = DocumentRunner(container, WorkModel(), research=SimulatedResearch(enabled))

        class ObservedRuntime(AgentRuntime):
            async def execute_step(self, run_id, ordinal):
                if ordinal in {1, 2}:
                    entered.add(ordinal)
                    if entered == {1, 2}:
                        both_started.set()
                    await asyncio.wait_for(both_started.wait(), 10)
                    result = await super().execute_step(run_id, ordinal)
                    finished.add(ordinal)
                    return result
                if ordinal == 3:
                    assert finished == {1, 2}
                return await super().execute_step(run_id, ordinal)

        runtime = ObservedRuntime(container, runner)
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, runner, runtime):
                await Dispatcher(container, env.client).tick()
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)

        final = container.agent.get(owner, run["id"])
        assert final["state"] == "completed"
        assert entered == {1, 2}
        assert finished == {1, 2}
        assert all(step["state"] == "completed" for step in final["steps"])

    asyncio.run(scenario())


def test_agent_v2_failed_branch_preserves_completed_independent_work_and_blocks_fan_in(container):
    async def scenario():
        enabled = replace(
            container.settings,
            agent_runtime_enabled=True,
            agent_dependency_graph_enabled=True,
            agent_parallel_execution_enabled=True,
            research_services_enabled=True,
            work_services_enabled=True,
            max_agent_parallel_steps=2,
        )
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Research two sources and create a project document.", output_language="en"
        ), "agent-parallel-failure")
        container.agent.save_plan(owner, run["id"], [
            AgentPlanStep(tool="research.search", arguments={
                "instruction": "Research the first public update.", "notes": "", "document_ids": [],
                "output_language": "en", "query": "first public project update", "time_range": "any",
            }),
            AgentPlanStep(tool="research.search", arguments={
                "instruction": "Research the second public update.", "notes": "", "document_ids": [],
                "output_language": "en", "query": "second public project update", "time_range": "any",
            }),
            AgentPlanStep(tool="document.create", arguments={
                "instruction": "Create the combined project document.", "notes": "",
                "document_ids": [], "output_language": "en",
            }),
        ])
        runner = DocumentRunner(container, WorkModel(), research=SimulatedResearch(enabled))

        class OneBranchFails(AgentRuntime):
            async def execute_step(self, run_id, ordinal):
                if ordinal == 1:
                    await asyncio.sleep(0.05)
                    raise CoworkerError("simulated_branch_failure", "A simulated branch failed.", 409)
                return await super().execute_step(run_id, ordinal)

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with make_worker(env, runner, OneBranchFails(container, runner)):
                await Dispatcher(container, env.client).tick()
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)

        final = container.agent.get(owner, run["id"])
        assert final["state"] == "failed"
        assert final["error_code"] == "simulated_branch_failure"
        assert final["steps"][0]["state"] == "failed"
        assert final["steps"][1]["state"] == "completed"
        assert final["steps"][2]["state"] == "failed"
        assert final["tool_invocations"][1]["receipt"]["resource_type"] == "task"

    asyncio.run(scenario())


def test_agent_v2_worker_restart_does_not_duplicate_parallel_task_work(container):
    async def scenario():
        enabled = replace(
            container.settings,
            agent_runtime_enabled=True,
            agent_dependency_graph_enabled=True,
            agent_parallel_execution_enabled=True,
            research_services_enabled=True,
            work_services_enabled=True,
            max_agent_parallel_steps=2,
        )
        container.settings = enabled
        container.repository.settings = enabled
        container.agent.settings = enabled
        owner = account(container)
        run, _ = container.agent.create(owner, AgentRunCreate(
            goal="Research two sources and create a project document.", output_language="en"
        ), "agent-parallel-restart")
        container.agent.save_plan(owner, run["id"], [
            AgentPlanStep(tool="research.search", arguments={
                "instruction": "Research the first public update.", "notes": "", "document_ids": [],
                "output_language": "en", "query": "first public project update", "time_range": "any",
            }),
            AgentPlanStep(tool="research.search", arguments={
                "instruction": "Research the second public update.", "notes": "", "document_ids": [],
                "output_language": "en", "query": "second public project update", "time_range": "any",
            }),
            AgentPlanStep(tool="document.create", arguments={
                "instruction": "Create the combined project document.", "notes": "",
                "document_ids": [], "output_language": "en",
            }),
        ])
        model = WorkModel()
        search = SimulatedResearch(enabled)
        checkpoint = asyncio.Event()
        drafted = set()

        class LostAfterParallelDraft(DocumentRunner):
            async def draft(self, task):
                await super().draft(task)
                worker_task = self.container.repository.worker_task(task["id"], False)
                if worker_task["skill_id"] == "research":
                    drafted.add(task["id"])
                    if len(drafted) == 2:
                        checkpoint.set()
                    await asyncio.Event().wait()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            first_runner = LostAfterParallelDraft(container, model, research=search)
            first = make_worker(env, first_runner, AgentRuntime(container, first_runner))
            first_run = asyncio.create_task(first.run())
            await Dispatcher(container, env.client).tick()
            await asyncio.wait_for(checkpoint.wait(), 30)
            await first.shutdown()
            await first_run

            midway = container.agent.get(owner, run["id"])
            resources = [container.agent.step_resource(run["id"], ordinal) for ordinal in (1, 2)]
            assert all(resource and resource["resource_type"] == "task" for resource in resources)
            assert len({resource["resource_id"] for resource in resources}) == 2
            assert all(container.repository.step(resource["resource_id"], "draft") is not None for resource in resources)
            assert model.calls == 2
            assert midway["steps"][2]["state"] == "planned"

            runner = DocumentRunner(container, model, research=search)
            async with make_worker(env, runner, AgentRuntime(container, runner)):
                handle = env.client.get_workflow_handle("shuddho-agent-" + run["id"])
                async with env.time_skipping_unlocked():
                    await asyncio.wait_for(handle.result(), 30)

        final = container.agent.get(owner, run["id"])
        assert final["state"] == "completed"
        assert model.calls == 3
        assert search.calls == 2
        assert all(step["state"] == "completed" for step in final["steps"])

    asyncio.run(scenario())
