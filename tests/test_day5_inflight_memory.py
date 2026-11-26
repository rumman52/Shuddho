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


@pytest.mark.parametrize("change", ["corrected", "deleted"])
def test_corrected_or_deleted_pin_during_planner_inference_rejects_new_decision(container, change):
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
            if change == "corrected":
                corrected = container.memory.update(
                    alice, selected["id"],
                    MemoryFactUpdate(
                        expected_version=selected["version"],
                        value="The corrected customer report must be in Bangla.",
                    ),
                )
                assert corrected["version"] == selected["version"] + 1
            else:
                assert container.memory.delete(alice, selected["id"])["deleted"] is True
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


def test_persisted_v3_decision_replays_after_pin_correction_but_new_call_fails(container):
    """An already-committed decision retains historical replay; new output does not."""
    alice, _, conversation, conversations, dispatch, selected, _, _ = seeded(container)
    item = message(conversations, alice, conversation, "Create a customer report for the project release.")
    admitted, _ = dispatch.dispatch(
        alice, conversation["id"], item["id"], expected_sequence=1,
        memory_pins=[pin(selected)],
    )
    decision = AgentV3Decision(decision="wait", wait_seconds=1)
    receipt = {
        "planner_call": 1,
        "model": "fixed-synthetic-planner",
        "prompt_sha256": "a" * 64,
        "tool_schema_sha256": "b" * 64,
        "observation_count": 0,
        "total_tokens": 24,
        "cost_microusd": None,
    }
    container.agent.record_v3_decision(admitted["run_id"], decision, **receipt)
    corrected = container.memory.update(
        alice, selected["id"],
        MemoryFactUpdate(expected_version=1, value="Use Bangla for this customer report."),
    )
    assert corrected["version"] == 2
    # Historical result must not be invalidated by a later correction.
    container.agent.record_v3_decision(admitted["run_id"], decision, **receipt)
    with pytest.raises(CoworkerError) as denied:
        container.agent.record_v3_decision(
            admitted["run_id"], decision, **(receipt | {"planner_call": 2}),
        )
    assert denied.value.code == "memory_pins_changed"
    with dispatch.sessions() as db:
        decisions = db.scalars(select(AgentDecision).where(
            AgentDecision.run_id == admitted["run_id"],
        )).all()
    assert len(decisions) == 1 and decisions[0].planner_call == 1


def test_three_arm_fixed_input_synthetic_output_scoring_and_owner_denial(container, record_property):
    """Exercise preview/dispatch/worker context through three held-constant arms.

    The renderer below is a NON-LLM deterministic probe. Its outputs demonstrate
    context propagation, not staged model quality or a successful golden run.
    """
    import hashlib
    from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
    from services.coworker.memory_schemas import MemoryFactCreate
    from services.coworker.models import AgentRun, Workspace

    alice, bob, _, conversations, dispatch, unselected_a, unselected_b, foreign = seeded(container)
    chosen = container.memory.create(
        alice, MemoryFactCreate(
            namespace="project", key="release_tag",
            value="Approved release tag: GREEN HARBOR.",
        ),
    )
    fixed_prompt = "Create a customer report for twelve verified project release checks."
    fixed_source = "Twelve synthetic project checks passed verification."
    fixed_brief = TaskBrief(objective=fixed_prompt, deliverables=["A customer report"])
    fixed_model = "deterministic-non-llm-output-probe-v1"
    fixed_budget = dispatch.settings.max_agent_context_bytes
    selected_service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)

    with dispatch.sessions() as db:
        a_workspace = db.scalar(select(Workspace.id).where(Workspace.owner_id == alice))
        b_workspace = db.scalar(select(Workspace.id).where(Workspace.owner_id == bob))
        assert a_workspace is not None and b_workspace is not None and a_workspace != b_workspace

    def render(context):
        # The only varying input is the validated pinned fact content.
        tags = [
            fact["value"].removeprefix("Approved release tag: ").rstrip(".")
            for fact in context["explicit_memory"]
            if fact["key"] == "release_tag"
        ]
        assert len(tags) <= 1
        return f"Verified customer release: {fixed_source}" + (
            f" Tag: {tags[0]}." if tags else ""
        )

    outcomes = []
    for arm, selected_version, required_tag in (
        ("without_memory", None, "GREEN HARBOR"),
        ("selected_v1", 1, "GREEN HARBOR"),
        ("corrected_v2", 2, "GOLDEN KITE"),
    ):
        if arm == "corrected_v2":
            corrected = container.memory.update(
                alice, chosen["id"],
                MemoryFactUpdate(
                    expected_version=1,
                    value="Approved release tag: GOLDEN KITE.",
                ),
            )
            assert corrected["version"] == 2
        pins = [] if selected_version is None else [
            pin(chosen if selected_version == 1 else corrected)
        ]
        conversation, _ = conversations.create(
            alice, ConversationCreate(title="Synthetic Day 5 arm"),
            f"day5-golden-{arm}",
        )
        item, _ = conversations.append_message(
            alice, conversation["id"],
            MessageCreate(text=fixed_prompt, client_request_key=f"day5-message-{arm}"),
        )
        preview = selected_service.validate(
            alice, conversation["id"], item["id"], expected_sequence=1,
            brief=fixed_brief, memory_pins=pins,
        )
        normalized_pins = [value.model_dump(mode="json") for value in pins]
        assert preview["memory_pins"] == normalized_pins
        accepted, created = dispatch.dispatch(
            alice, conversation["id"], item["id"], expected_sequence=1,
            reviewed_brief=fixed_brief, expected_digest=preview["canonical_digest"],
            memory_pins=pins,
        )
        assert created
        context, _ = container.context.planner_context(alice, accepted["run_id"])
        with dispatch.sessions() as db:
            run = db.get(AgentRun, accepted["run_id"])
            assert run.memory_namespaces == []
            assert run.project_context["memory_pins"] == normalized_pins
            assert run.reviewed_brief["canonical_digest"] == preview["canonical_digest"]
        assert context["memory_provenance"] == (
            [{"id": chosen["id"], "version": selected_version}] if selected_version else []
        )
        assert "BLUE PARROT" not in str(context)
        assert unselected_a["value"] not in str(context)
        assert unselected_b["value"] not in str(context)
        assert foreign["value"] not in str(context)
        # B uses the real owner-scoped read method, rather than an admin SQL query.
        with pytest.raises(CoworkerError) as denied:
            container.context.for_run(bob, accepted["run_id"])
        assert denied.value.status_code == 404
        assert chosen["value"] not in str(denied.value)
        assert chosen["id"] not in {fact["id"] for fact in container.memory.list(bob)}

        output = render(context)
        score = int(required_tag in output)
        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        record_property(f"{arm}_output_sha256", digest)
        record_property(f"{arm}_score", score)
        outcomes.append((arm, output, score))
        container.agent.cancel(alice, accepted["run_id"])
        assert dispatch.settings.max_agent_context_bytes == fixed_budget

    assert fixed_model == "deterministic-non-llm-output-probe-v1"
    assert [result[2] for result in outcomes] == [0, 1, 1]
    assert "GREEN HARBOR" not in outcomes[0][1]
    assert "GOLDEN KITE" in outcomes[2][1] and "GREEN HARBOR" not in outcomes[2][1]


def _selected_memory_child_task(container):
    from services.coworker.schemas import TaskCreate

    alice, _, conversation, conversations, dispatch, selected, _, _ = seeded(container)
    item = message(conversations, alice, conversation, "Create a customer report for the project release.")
    admitted, _ = dispatch.dispatch(
        alice, conversation["id"], item["id"], expected_sequence=1,
        memory_pins=[pin(selected)],
    )
    task, _ = container.repository.create_task(
        alice, TaskCreate(
            instruction="Prepare a customer report and draft email.",
            notes="The team completed 12 reviews.", output_language="en",
        ), "day5-pinned-child-task", agent_run_id=admitted["run_id"],
    )
    return alice, selected, task


@pytest.mark.parametrize("change", ["corrected", "deleted"])
def test_child_draft_rejects_memory_revoked_during_inference(container, change):
    alice, selected, task = _selected_memory_child_task(container)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        class DelayedModel(FakeModel):
            def messages(self, task, sources):
                assert [entry["key"] for entry in task["memory"]] == [selected["key"]]
                return super().messages(task, sources)

            async def generate(self, *args):
                entered.set()
                await release.wait()
                return await super().generate(*args)

        runner = DocumentRunner(container, DelayedModel())
        pending = asyncio.create_task(runner.run_for_test(task["id"]))
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            if change == "corrected":
                container.memory.update(
                    alice, selected["id"], MemoryFactUpdate(
                        expected_version=selected["version"], value="Use Bangla instead.",
                    ),
                )
            else:
                container.memory.delete(alice, selected["id"])
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
    assert container.repository.step(task["id"], "draft") is None
    assert container.repository.step(task["id"], "export") is None
    result = container.repository.get_task(alice, task["id"])
    assert result["state"] == "failed" and result["draft"] is None
    assert result["artifacts"] == []
    assert result["usage"]["model_attempts"] == 1


def test_child_publication_revalidates_memory_after_export_checkpoint(container):
    alice, selected, task = _selected_memory_child_task(container)
    runner = DocumentRunner(container, FakeModel())

    async def scenario():
        for phase in ("extract", "draft", "export"):
            await runner.phase(task["id"], phase)
        saved = container.repository.step(task["id"], "export")
        assert saved and len(saved["artifacts"]) == 4
        # Revoke after the draft and private object writes have committed.
        # Invoke the trusted completion method directly to exercise its final
        # persistence transaction independently of the phase-entry check.
        container.memory.delete(alice, selected["id"])
        with pytest.raises(CoworkerError) as denied:
            await runner.complete(container.repository.worker_task(task["id"], check_live=False))
        assert denied.value.code == "memory_pins_changed"

    asyncio.run(scenario())
    result = container.repository.get_task(alice, task["id"])
    assert result["state"] not in {"completed", "needs_input"}
    assert result["artifacts"] == []
