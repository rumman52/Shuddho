"""C-01: terminal Runtime v3 runs must not be completed or replanned later."""
import asyncio

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra")
pytest.importorskip("temporalio", reason="Install the coworker extra")

from services.coworker.agent_schemas import AgentPlanStep
from services.coworker.errors import CoworkerError
from tests.test_agent_v3_decision_recovery import setup
from tests.test_context_memory import container


@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_complete_run_cannot_override_terminal_v3_result(container, terminal):
    actor, run_id, _runtime, planner = setup(container)
    container.agent.v3_terminal(run_id, terminal, "Final outcome already committed.")
    saved = container.agent.get(actor, run_id)
    with pytest.raises(CoworkerError) as caught:
        container.agent.complete_run(run_id)
    assert caught.value.code == "agent_run_closed"
    after = container.agent.get(actor, run_id)
    assert after["state"] == saved["state"] == terminal
    assert after["event_sequence"] == saved["event_sequence"]
    assert planner.calls == 0


@pytest.mark.parametrize("terminal", ["needs_input", "blocked"])
def test_replan_cannot_replace_prepared_v3_step_after_terminal(container, terminal):
    actor, run_id, runtime, planner = setup(container)
    admitted = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/step"))
    assert admitted["ordinal"] == 1
    original = container.agent.get(actor, run_id)
    container.agent.v3_terminal(run_id, terminal, "Final outcome already committed.")
    saved = container.agent.get(actor, run_id)
    with pytest.raises(CoworkerError) as caught:
        container.agent.replace_remaining_plan(actor, run_id, 1, [
            AgentPlanStep(tool="email.draft", arguments={
                "instruction": "Prepare the next update.",
                "notes": "", "document_ids": [], "output_language": "en",
            }),
        ])
    assert caught.value.code == "agent_run_closed"
    after = container.agent.get(actor, run_id)
    assert after["state"] == saved["state"] == terminal
    assert after["event_sequence"] == saved["event_sequence"]
    assert after["steps"] == saved["steps"]
    assert planner.calls == 1


def test_unfinished_v3_run_cannot_report_success_without_verified_steps(container):
    actor, run_id, runtime, planner = setup(container)
    admitted = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/step"))
    assert admitted["ordinal"] == 1
    with pytest.raises(CoworkerError) as caught:
        container.agent.complete_run(run_id)
    assert caught.value.code == "agent_incomplete"
    assert container.agent.get(actor, run_id)["state"] not in {"completed", "failed", "cancelled"}
    assert planner.calls == 1


def test_v3_final_completion_requires_at_least_one_verified_tool(container):
    actor, run_id, runtime, planner = setup(container)
    before = container.agent.get(actor, run_id)
    checkpoints = container.agent.checkpoints(actor, run_id)
    with pytest.raises(CoworkerError) as caught:
        runtime.complete(run_id)
    assert caught.value.code == "agent_unverified_completion"
    after = container.agent.get(actor, run_id)
    assert after["state"] == before["state"]
    assert after["event_sequence"] == before["event_sequence"]
    assert container.agent.checkpoints(actor, run_id) == checkpoints
    assert planner.calls == 0


@pytest.mark.parametrize("resource_type, summary", [
    ("task", {"task_state": "needs_input", "has_missing_information": True}),
    ("action", {"action_state": "outcome_unknown", "provider_confirmed": False}),
])
def test_v3_final_completion_rechecks_receipt_quality(container, resource_type, summary):
    actor, run_id, runtime, planner = setup(container)
    ordinal = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/step"))["ordinal"]
    # Synthetic receipt fixture isolates finalization, not provider qualification.
    container.agent.begin_invocation(run_id, ordinal)
    container.agent.finish_invocation(run_id, ordinal, resource_type, "synthetic-result", summary)
    assert container.agent.v3_can_complete(run_id) is False
    before = container.agent.get(actor, run_id)
    checkpoints = container.agent.checkpoints(actor, run_id)
    with pytest.raises(CoworkerError) as caught:
        runtime.complete(run_id)
    assert caught.value.code == "agent_unverified_completion"
    after = container.agent.get(actor, run_id)
    assert after["state"] == before["state"]
    assert after["event_sequence"] == before["event_sequence"]
    assert container.agent.checkpoints(actor, run_id) == checkpoints
    assert planner.calls == 1


def test_v3_verified_completion_and_completed_replay_preserve_one_result(container):
    from tests.test_agent_v3_decision_recovery import _commit_synthetic_completed_step, _expire_run_deadline

    actor, run_id, runtime, planner = setup(container)
    ordinal = asyncio.run(runtime.decide_v3(run_id, activity_key="workflow/step"))["ordinal"]
    _commit_synthetic_completed_step(container, run_id, ordinal)
    runtime.complete(run_id)
    saved = container.agent.get(actor, run_id)
    checkpoints = container.agent.checkpoints(actor, run_id)
    assert saved["state"] == "completed"
    _expire_run_deadline(container, run_id)
    runtime.complete(run_id)
    after = container.agent.get(actor, run_id)
    assert after["state"] == "completed"
    assert after["event_sequence"] == saved["event_sequence"]
    assert container.agent.checkpoints(actor, run_id) == checkpoints
    assert planner.calls == 1


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_final_completion_keeps_empty_run_behavior(container, version):
    from services.coworker.models import AgentRun

    actor, run_id, runtime, _planner = setup(container)
    with container.repository.sessions.begin() as db:
        db.get(AgentRun, run_id).runtime_version = version
    runtime.complete(run_id)
    assert container.agent.get(actor, run_id)["state"] == "completed"
