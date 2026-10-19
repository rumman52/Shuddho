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
