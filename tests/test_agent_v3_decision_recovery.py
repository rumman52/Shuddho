"""Exercise real persistence across logical activity retries; no Temporal server needed."""
import asyncio
from dataclasses import replace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for v3 recovery")
pytest.importorskip("temporalio", reason="Install the coworker extra for v3 recovery")

from sqlalchemy import select
from temporalio.testing import ActivityEnvironment

from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentRunCreate, AgentV3Decision
from services.coworker.errors import CoworkerError
from services.coworker.models import AgentDecision, MemoryProposal, ToolInvocation
from services.coworker.worker import AgentActivities
from tests.test_context_memory import container, enable_pa04, owner


class Planner:
    def __init__(self, decision="next_step"):
        self.calls = 0
        self.decision = decision

    async def decide(self, *_args, **_kwargs):
        self.calls += 1
        value = {"decision": self.decision}
        if self.decision == "next_step":
            value.update(tool="email.draft", objective="Draft a concise weekly update.", memory_proposal={
                "namespace": "preferences", "key": "update_style", "value": "Use concise updates.",
                "language": "en", "source_ids": ["goal"],
            })
        elif self.decision == "wait":
            value["wait_seconds"] = 2
        else:
            value["message"] = "Please provide the missing details."
        return AgentV3Decision.model_validate(value), 24, 1, {
            "model": "test-model", "prompt_sha256": "a" * 64, "tool_schema_sha256": "b" * 64,
        }


def setup(container, decision="next_step"):
    enable_pa04(container)
    actor = owner(container)
    run, _ = container.agent.create(actor, AgentRunCreate(goal="Create a concise weekly update.", output_language="en"), "recovery")
    planner = Planner(decision)
    return actor, run["id"], AgentRuntime(container, None, planner=planner), planner


def counts(container, run_id):
    with container.repository.sessions() as db:
        return [len(db.scalars(select(model).where(model.run_id == run_id)).all()) for model in (AgentDecision, ToolInvocation, MemoryProposal)]


def test_committed_activity_replays_without_inference_step_memory_or_charge(container):
    actor, run_id, runtime, planner = setup(container)
    first = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/decision-1"))
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/decision-1")) == first == {"decision": "next_step", "ordinal": 1}
    assert planner.calls == 1
    assert counts(container, run_id) == [1, 1, 1]
    saved = container.agent.get(actor, run_id)
    assert saved["planner_calls"] == 1
    assert saved["planner_actual_tokens"] == 24
    # A genuinely new logical decision still hits the existing loop fence.
    with pytest.raises(CoworkerError, match="identical tool"):
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/decision-2"))
    assert counts(container, run_id) == [1, 1, 1]


def test_interruption_before_step_commit_rolls_back_decision_and_memory(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    original = container.agent.append_v3_step
    def crash(*_args, **_kwargs):
        raise RuntimeError("interrupted before step commit")
    monkeypatch.setattr(container.agent, "append_v3_step", crash)
    with pytest.raises(RuntimeError, match="interrupted"):
        asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))
    assert counts(container, run_id) == [0, 0, 0]
    monkeypatch.setattr(container.agent, "append_v3_step", original)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))["ordinal"] == 1
    assert planner.calls == 2  # Both actual model attempts remain charged and bounded.
    assert container.agent.get(actor, run_id)["planner_actual_tokens"] == 48
    assert counts(container, run_id) == [1, 1, 1]


def test_lost_commit_response_replays_without_double_settlement(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    original = container.agent.commit_v3_decision
    def lost_response(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("commit response lost")
    monkeypatch.setattr(container.agent, "commit_v3_decision", lost_response)
    with pytest.raises(RuntimeError, match="response lost"):
        asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))
    monkeypatch.setattr(container.agent, "commit_v3_decision", original)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))["ordinal"] == 1
    assert planner.calls == 1
    assert container.agent.get(actor, run_id)["planner_actual_tokens"] == 24
    assert counts(container, run_id) == [1, 1, 1]


@pytest.mark.parametrize("decision", ["wait", "needs_input", "blocked"])
def test_non_tool_result_replays_for_same_activity(container, decision):
    actor, run_id, runtime, planner = setup(container, decision)
    first = asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1")) == first
    assert planner.calls == 1
    if decision == "wait":
        asyncio.run(runtime.decide_v3(run_id, activity_key="decision-2"))
        assert planner.calls == 2


def test_cancelled_run_does_not_release_cached_work(container):
    actor, run_id, runtime, planner = setup(container)
    asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))
    container.agent.cancel(actor, run_id)
    with pytest.raises(CoworkerError) as error:
        asyncio.run(runtime.decide_v3(run_id, activity_key="decision-1"))
    assert error.value.code == "agent_cancelled"
    assert planner.calls == 1


def test_temporal_activity_attempts_share_stable_identity(container):
    _actor, run_id, runtime, planner = setup(container)
    activities = AgentActivities.__new__(AgentActivities)
    activities.runtime = runtime
    env = ActivityEnvironment()
    env.info = replace(env.info, workflow_run_id="workflow-run-1", activity_id="decision-1", attempt=1)
    first = asyncio.run(env.run(activities.decide_v3, run_id))
    env.info = replace(env.info, attempt=2)
    assert asyncio.run(env.run(activities.decide_v3, run_id)) == first
    assert planner.calls == 1

def test_no_tools_blocked_activity_is_durably_replayable(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    monkeypatch.setattr("services.coworker.agent_runtime.intelligent_tool_names", lambda *_a, **_k: [])
    result = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools"))
    assert result == {"decision": "blocked"}
    assert container.agent.v3_activity_result(run_id, "workflow/no-tools") == result
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools")) == result
    assert planner.calls == 0
    assert container.agent.get(actor, run_id)["state"] == "blocked"
    assert counts(container, run_id) == [0, 0, 0]


def test_no_tools_block_cannot_win_after_concurrent_cancellation(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    monkeypatch.setattr("services.coworker.agent_runtime.intelligent_tool_names", lambda *_a, **_k: [])

    def cancel_before_terminal(_run_id):
        container.agent.cancel(actor, run_id)
        return False

    monkeypatch.setattr(container.agent, "v3_can_complete", cancel_before_terminal)
    with pytest.raises(CoworkerError) as caught:
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools"))
    assert caught.value.code == "agent_cancelled"
    assert container.agent.v3_activity_result(run_id, "workflow/no-tools") is None
    assert container.agent.get(actor, run_id)["state"] == "cancelled"
    assert planner.calls == 0


def test_no_tools_block_cannot_mask_concurrent_terminal_transition(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    monkeypatch.setattr("services.coworker.agent_runtime.intelligent_tool_names", lambda *_a, **_k: [])

    def needs_input_before_block(_run_id):
        container.agent.v3_terminal(run_id, "needs_input", "Waiting for verified user input.")
        return False

    monkeypatch.setattr(container.agent, "v3_can_complete", needs_input_before_block)
    with pytest.raises(CoworkerError) as caught:
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools"))
    assert caught.value.code == "agent_run_closed"
    assert container.agent.v3_activity_result(run_id, "workflow/no-tools") is None
    assert container.agent.get(actor, run_id)["state"] == "needs_input"
    assert planner.calls == 0

def test_no_tools_commit_response_loss_replays_without_new_terminal(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    monkeypatch.setattr("services.coworker.agent_runtime.intelligent_tool_names", lambda *_a, **_k: [])
    original = container.agent.block_v3_unavailable_tools

    def lose_reply(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("no-tools commit response lost")

    monkeypatch.setattr(container.agent, "block_v3_unavailable_tools", lose_reply)
    with pytest.raises(RuntimeError, match="commit response lost"):
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools"))
    monkeypatch.setattr(container.agent, "block_v3_unavailable_tools", original)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools")) == {"decision": "blocked"}
    assert container.agent.get(actor, run_id)["state"] == "blocked"
    assert planner.calls == 0


def test_no_tools_checkpoint_failure_rolls_back_terminal(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    monkeypatch.setattr("services.coworker.agent_runtime.intelligent_tool_names", lambda *_a, **_k: [])
    original_state = container.agent.get(actor, run_id)["state"]
    original = container.agent._checkpoint

    def fail_checkpoint(*args, **kwargs):
        if len(args) > 2 and args[2] == "v3_activity_result":
            raise RuntimeError("checkpoint persistence interrupted")
        return original(*args, **kwargs)

    monkeypatch.setattr(container.agent, "_checkpoint", fail_checkpoint)
    with pytest.raises(RuntimeError, match="checkpoint persistence interrupted"):
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools"))
    assert container.agent.v3_activity_result(run_id, "workflow/no-tools") is None
    assert container.agent.get(actor, run_id)["state"] == original_state
    monkeypatch.setattr(container.agent, "_checkpoint", original)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools")) == {"decision": "blocked"}
    assert planner.calls == 0


@pytest.mark.parametrize("state", ["needs_input", "blocked"])
def test_terminal_v3_run_rejects_new_planner_reservation_without_budget_charge(container, state):
    actor, run_id, runtime, planner = setup(container)
    container.agent.v3_terminal(run_id, state, "Terminal outcome already persisted.")
    before = container.agent.get(actor, run_id)
    with pytest.raises(CoworkerError) as caught:
        container.agent.reserve_planner(run_id, runtime._v3_planner_reservation())
    assert caught.value.code == "agent_run_closed"
    after = container.agent.get(actor, run_id)
    assert after["state"] == state
    assert after["planner_calls"] == before["planner_calls"] == 0
    assert after["planner_actual_tokens"] == before["planner_actual_tokens"] == 0
    assert planner.calls == 0


@pytest.mark.parametrize("state", ["needs_input", "blocked"])
def test_terminal_v3_run_cannot_infer_new_activity(container, state):
    actor, run_id, runtime, planner = setup(container)
    container.agent.v3_terminal(run_id, state, "Terminal outcome already persisted.")
    with pytest.raises(CoworkerError) as caught:
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/new-after-terminal"))
    assert caught.value.code == "agent_run_closed"
    assert container.agent.v3_activity_result(run_id, "workflow/new-after-terminal") is None
    assert container.agent.get(actor, run_id)["planner_calls"] == 0
    assert planner.calls == 0


def test_committed_terminal_v3_result_still_replays_without_reservation(container):
    actor, run_id, runtime, planner = setup(container, decision="needs_input")
    first = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/terminal"))
    assert first == {"decision": "needs_input"}
    assert container.agent.get(actor, run_id)["state"] == "needs_input"
    before = container.agent.get(actor, run_id)["planner_calls"]
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/terminal")) == first
    assert container.agent.get(actor, run_id)["planner_calls"] == before == 1
    assert planner.calls == 1

@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_v3_cannot_append_fresh_step_after_terminal(container, terminal):
    actor, run_id, runtime, planner = setup(container)
    container.agent.v3_terminal(run_id, terminal, "Terminal state won.")
    before = counts(container, run_id)
    with pytest.raises(CoworkerError) as caught:
        container.agent.append_v3_step(actor, run_id, "email.draft", "Draft a weekly note.")
    assert caught.value.code == "agent_run_closed"
    assert counts(container, run_id) == before == [0, 0, 0]
    assert container.agent.get(actor, run_id)["state"] == terminal
    assert planner.calls == 0


@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_v3_cannot_start_queued_step_after_terminal(container, terminal):
    actor, run_id, runtime, planner = setup(container)
    decision = asyncio.run(runtime.decide_v3(run_id, activity_key="step/admit"))
    ordinal = decision["ordinal"]
    container.agent.v3_terminal(run_id, terminal, "Terminal state won.")
    with pytest.raises(CoworkerError) as caught:
        container.agent.begin_invocation(run_id, ordinal)
    assert caught.value.code == "agent_run_closed"
    state = container.agent.get(actor, run_id)
    assert state["state"] == terminal
    assert state["steps"][-1]["state"] != "running"
    assert planner.calls == 1


@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_v3_cannot_commit_late_receipt_over_terminal(container, terminal):
    actor, run_id, runtime, planner = setup(container)
    ordinal = asyncio.run(runtime.decide_v3(run_id, activity_key="step/receipt"))["ordinal"]
    container.agent.v3_terminal(run_id, terminal, "Terminal state won.")
    with pytest.raises(CoworkerError) as caught:
        container.agent.finish_invocation(
            run_id, ordinal, "task", "synthetic-task-id",
            {"verified": True, "provider_confirmed": False},
        )
    assert caught.value.code == "agent_run_closed"
    with container.repository.sessions() as db:
        from services.coworker.models import ToolReceipt
        assert db.query(ToolReceipt).filter(ToolReceipt.run_id == run_id).count() == 0
    assert container.agent.get(actor, run_id)["state"] == terminal
    assert planner.calls == 1

@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_v3_legacy_plan_api_cannot_reopen_terminal_run(container, terminal):
    from services.coworker.agent_schemas import AgentPlanStep
    actor, run_id, runtime, planner = setup(container)
    container.agent.v3_terminal(run_id, terminal, "Terminal state won.")
    with pytest.raises(CoworkerError) as caught:
        container.agent.save_plan(actor, run_id, [
            AgentPlanStep(tool="email.draft", arguments={
                "instruction": "Draft a concise weekly note.",
                "notes": "", "document_ids": [], "output_language": "en",
            }),
        ])
    assert caught.value.code == "agent_run_closed"
    assert container.agent.get(actor, run_id)["state"] == terminal
    assert counts(container, run_id) == [0, 0, 0]


@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_v3_action_waiting_cannot_rearm_after_terminal(container, terminal):
    from action_samples import enable_actions, connected, action_request
    from services.coworker.agent_schemas import AgentPlanStep
    enable_actions(container)
    enable_pa04(container)
    container.actions.repo.settings = container.settings
    actor = owner(container)
    connection = connected(container.actions.repo, actor)
    action = container.actions.repo.prepare(
        actor, action_request(connection), "v3-terminal-action-" + terminal,
    )
    run, _ = container.agent.create(actor, AgentRunCreate(
        goal="Complete the attached external action.",
        action_ids=[action["id"]],
        output_language="en",
    ), "v3-terminal-action-run-" + terminal)
    container.agent.save_plan(actor, run["id"], [
        AgentPlanStep(tool="email.send", arguments={"action_id": action["id"]}),
    ])
    container.agent.v3_terminal(run["id"], terminal, "Terminal state won.")
    with pytest.raises(CoworkerError) as caught:
        container.agent.action_waiting(run["id"], 1, action["id"], "queued")
    assert caught.value.code == "agent_run_closed"
    assert container.agent.get(actor, run["id"])["state"] == terminal
    with container.repository.sessions() as db:
        from services.coworker.models import ExternalAction
        assert db.get(ExternalAction, action["id"]).agent_ready is False


def _expire_run_deadline(container, run_id):
    from datetime import datetime, timedelta, timezone
    from services.coworker.models import AgentRun
    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        assert run is not None
        run.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=2)


def test_committed_v3_decision_replays_after_deadline_without_new_inference(container):
    actor, run_id, runtime, planner = setup(container)
    first = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/deadline-replay"))
    assert first == {"decision": "next_step", "ordinal": 1}
    before = container.agent.get(actor, run_id)
    _expire_run_deadline(container, run_id)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/deadline-replay")) == first
    after = container.agent.get(actor, run_id)
    assert counts(container, run_id) == [1, 1, 1]
    assert after["planner_calls"] == before["planner_calls"] == 1
    assert planner.calls == 1


def test_expired_v3_run_rejects_fresh_activity_without_inference(container):
    actor, run_id, runtime, planner = setup(container)
    first = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/original"))
    assert first["decision"] == "next_step"
    _expire_run_deadline(container, run_id)
    with pytest.raises(CoworkerError) as caught:
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/new-after-deadline"))
    assert caught.value.code == "agent_deadline"
    assert container.agent.v3_activity_result(run_id, "workflow/new-after-deadline") is None
    assert counts(container, run_id) == [1, 1, 1]
    assert planner.calls == 1


def test_committed_no_tool_block_replays_after_deadline(container, monkeypatch):
    actor, run_id, runtime, planner = setup(container)
    monkeypatch.setattr("services.coworker.agent_runtime.intelligent_tool_names", lambda *_a, **_k: [])
    original = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools-deadline"))
    assert original == {"decision": "blocked"}
    _expire_run_deadline(container, run_id)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/no-tools-deadline")) == original
    assert container.agent.get(actor, run_id)["state"] == "blocked"
    assert counts(container, run_id) == [0, 0, 0]
    assert planner.calls == 0


def test_cancelled_v3_activity_does_not_replay_after_deadline(container):
    actor, run_id, runtime, planner = setup(container)
    assert asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/cancelled-deadline"))["ordinal"] == 1
    container.agent.cancel(actor, run_id)
    _expire_run_deadline(container, run_id)
    with pytest.raises(CoworkerError) as caught:
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/cancelled-deadline"))
    assert caught.value.code == "agent_cancelled"
    assert container.agent.get(actor, run_id)["state"] == "cancelled"
    assert planner.calls == 1


def test_expired_v3_run_without_a_checkpoint_remains_fail_closed(container):
    actor, run_id, runtime, planner = setup(container)
    _expire_run_deadline(container, run_id)
    with pytest.raises(CoworkerError) as caught:
        asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/never-committed"))
    assert caught.value.code == "agent_deadline"
    assert container.agent.v3_activity_result(run_id, "workflow/never-committed") is None
    assert planner.calls == 0
