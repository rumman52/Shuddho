"""Day 5: exact owner/version memory pins for reviewed conversation tasks."""
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from pydantic import ValidationError
from sqlalchemy import select

from test_context_memory import enable_pa04, owner as memory_owner
from test_conversation_dispatch import container, message, setup
from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.errors import CoworkerError
from services.coworker.memory_schemas import MemoryFactCreate, MemoryFactUpdate
from services.coworker.models import AgentRun, MemoryFact, utcnow
from services.coworker.task_brief_schemas import MemoryPin, TaskBriefMemorySelection


def seeded(container):
    enable_pa04(container)
    alice, conversation, conversations, dispatch = setup(container, key="day5-owner")
    bob = memory_owner(container, "day5-foreign-owner")
    keep = container.memory.create(alice, MemoryFactCreate(
        namespace="project", key="release_language", value="The project's customer report must be in English.",
    ))
    omit = container.memory.create(alice, MemoryFactCreate(
        namespace="project", key="internal_code", value="The internal code name is BLUE PARROT.",
    ))
    foreign = container.memory.create(bob, MemoryFactCreate(
        namespace="project", key="private_budget", value="Private owner budget 999999.",
    ))
    return alice, bob, conversation, conversations, dispatch, keep, omit, foreign


def pin(fact):
    return MemoryPin(fact_id=UUID(fact["id"]), expected_version=fact["version"])


def test_one_selected_project_fact_enters_planner_context_unselected_never_enters(container):
    alice, _, conv, conversations, dispatch, keep, omit, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    created, new = dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(keep)])
    assert new
    context, _ = container.context.planner_context(alice, created["run_id"])
    assert [p["id"] for p in context["memory_provenance"]] == [keep["id"]]
    assert "English" in context["explicit_memory"][0]["value"]
    assert all("BLUE PARROT" not in str(value) for value in context["explicit_memory"])
    with dispatch.sessions() as db:
        run = db.get(AgentRun, created["run_id"])
        assert run.memory_namespaces == []


def test_explicit_empty_selection_never_falls_back_to_project_namespace(container):
    alice, _, conv, conversations, dispatch, keep, omit, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    accepted, _ = dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[])
    assert container.memory.context_for_run(alice, accepted["run_id"])["facts"] == []


def test_foreign_pin_is_rejected_before_creating_a_run(container):
    alice, _, conv, conversations, dispatch, _, _, foreign = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    with pytest.raises(CoworkerError) as denial:
        dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(foreign)])
    assert denial.value.status_code in (403, 404, 409)
    with dispatch.sessions() as db:
        assert db.scalars(select(AgentRun).where(AgentRun.owner_id == alice)).all() == []


@pytest.mark.parametrize("change", ["updated", "deleted", "expired", "stale"])
def test_pin_change_after_admission_rejects_worker_use(container, change):
    alice, _, conv, conversations, dispatch, keep, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    accepted, _ = dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(keep)])
    if change == "updated":
        container.memory.update(alice, keep["id"], MemoryFactUpdate(
            expected_version=keep["version"], value="Corrected customer preference.",
        ))
    elif change == "deleted":
        container.memory.delete(alice, keep["id"])
    else:
        with container.repository.sessions.begin() as db:
            row = db.get(MemoryFact, keep["id"])
            if change == "expired":
                row.expires_at = utcnow() - timedelta(seconds=1)
            else:
                row.updated_at = utcnow() - timedelta(
                    seconds=container.settings.max_memory_context_age_seconds + 1
                )
    with pytest.raises(CoworkerError) as denied:
        container.memory.context_for_run(alice, accepted["run_id"])
    assert denied.value.code == "memory_pins_changed"


def test_explicit_current_task_instruction_overrides_pinned_formal_preference(container):
    alice, _, conv, conversations, dispatch, _, _, _ = seeded(container)
    style = container.memory.create(alice, MemoryFactCreate(
        namespace="preferences", key="writing.tone", value="Usually write formally.",
    ))
    msg = message(conversations, alice, conv, "Create a customer report; for this report make it casual and conversational.")
    accepted, _ = dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(style)])
    assert container.memory.context_for_run(alice, accepted["run_id"])["facts"] == []


def test_idempotency_fingerprint_rejects_changed_or_removed_memory_selection(container):
    alice, _, conv, conversations, dispatch, keep, omit, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    first, _ = dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(keep)])
    replay, created = dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(keep)])
    assert not created and replay["run_id"] == first["run_id"]
    for changed in ([pin(omit)], [], None):
        with pytest.raises(CoworkerError) as denied:
            dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=changed)
        assert denied.value.code == "idempotency_conflict"


def test_direct_namespace_runs_keep_original_memory_behavior(container):
    alice, _, _, _, _, keep, omit, _ = seeded(container)
    run, _ = container.agent.create(alice, AgentRunCreate(
        goal="Create a customer report for the project release.",
        memory_namespaces=["project"],
    ), "day5-legacy-run")
    facts = container.memory.context_for_run(alice, run["id"])["facts"]
    assert {f["key"] for f in facts} == {keep["key"], omit["key"]}


def test_memory_selection_schema_rejects_duplicate_ids_and_nonpositive_versions(container):
    alice_id = "a15ff73a-47d1-48cb-99e4-67ad33c00ed1"
    with pytest.raises(ValidationError):
        MemoryPin(fact_id=UUID(alice_id), expected_version=0)
    with pytest.raises(ValidationError):
        TaskBriefMemorySelection(memory_pins=[
            {"fact_id": alice_id, "expected_version": 1},
            {"fact_id": alice_id, "expected_version": 2},
        ])
