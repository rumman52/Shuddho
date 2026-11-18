"""Day 5: reject uncommitted planner output after selected memory changes.

These tests use synthetic local identities and a fixed, non-billed planner.
They do not claim operated staging or live model quality evidence.
"""
import asyncio

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import select

from test_conversation_dispatch import container, message
from test_conversation_task_briefs import seeded, pin
from test_coworker import FakeModel
from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentV3Decision
from services.coworker.conversation_task_briefs import ConversationTaskBriefService
from services.coworker.errors import CoworkerError
from services.coworker.memory_schemas import MemoryFactUpdate
from services.coworker.models import AgentDecision, ToolInvocation
from services.coworker.runner import DocumentRunner
from services.coworker.task_brief_schemas import TaskBrief


def test_corrected_pin_during_planner_inference_rejects_new_decision(container):
    alice, _, conversation, conversations, dispatch, selected, unselected, _ = seeded(container)
    item = message(conversations, alice, conversation, "Create a customer report for the project release.")
    brief = TaskBrief(objective=item["text"], deliverables=["A customer report"])
    selection = [pin(selected)]
    preview = ConversationTaskBriefService(dispatch.sessions, dispatch.settings).validate(
        alice, conversation["id"], item["id"], expected_sequence=1,
        brief=brief, memory_pins=selection,
    )
    admitted, created = dispatch.dispatch(
        alice, conversation["id"], item["id"], expected_sequence=1,
        reviewed_brief=brief, expected_digest=preview["canonical_digest"],
        memory_pins=selection,
    )
    assert created

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        class DelayedPlanner:
            async def decide(self, _goal, _tools, _observations, **kwargs):
                context = kwargs["dependencies"]["context"]
                assert context["memory_provenance"] == [
                    {"id": selected["id"], "version": selected["version"]}
                ]
                assert "BLUE PARROT" not in str(context)
                entered.set()
                await release.wait()
                return AgentV3Decision(
                    decision="wait", wait_seconds=1,
                ), 24, 1, {
                    "model": "fixed-synthetic-planner",
                    "prompt_sha256": "a" * 64,
                    "tool_schema_sha256": "b" * 64,
                }

        runtime = AgentRuntime(container, DocumentRunner(container, FakeModel()), planner=DelayedPlanner())
        pending = asyncio.create_task(runtime.decide_v3(admitted["run_id"]))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            corrected = container.memory.update(
                alice, selected["id"],
                MemoryFactUpdate(
                    expected_version=selected["version"],
                    value="The corrected customer report must be in Bangla.",
                ),
            )
            assert corrected["version"] == selected["version"] + 1
            release.set()
            with pytest.raises(CoworkerError) as denied:
                await pending
            assert denied.value.code == "memory_pins_changed"
        finally:
            release.set()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())
    with dispatch.sessions() as db:
        assert db.scalars(select(AgentDecision).where(
            AgentDecision.run_id == admitted["run_id"],
        )).all() == []
        assert db.scalars(select(ToolInvocation).where(
            ToolInvocation.run_id == admitted["run_id"],
        )).all() == []
