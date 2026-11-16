"""Day 5: exact owner/version memory pins for reviewed conversation tasks."""
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from pydantic import ValidationError
from sqlalchemy import func, select

from test_context_memory import enable_pa04, owner as memory_owner
from test_conversation_dispatch import container, message, setup
from test_coworker import signed_client
from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.conversation_task_briefs import ConversationTaskBriefService
from services.coworker.errors import CoworkerError
from services.coworker.memory_schemas import MemoryFactCreate, MemoryFactUpdate
from services.coworker.models import AgentOutbox, AgentRun, MemoryFact, Workspace, utcnow
from services.coworker.task_brief_schemas import MemoryPin, TaskBrief, TaskBriefMemorySelection


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


def test_reviewed_brief_rejects_adding_memory_after_preview(container):
    alice, _, conv, conversations, dispatch, keep, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    brief = TaskBrief(objective=msg["text"], deliverables=["A customer report"])
    service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)
    preview = service.validate(alice, conv["id"], msg["id"], expected_sequence=1, brief=brief)

    with pytest.raises(CoworkerError) as denied:
        dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1,
                          reviewed_brief=brief, expected_digest=preview["canonical_digest"],
                          memory_pins=[pin(keep)])
    assert denied.value.code == "task_brief_digest_mismatch"
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 0


def test_reviewed_memory_selection_is_rechecked_at_admission_replay_and_worker_use(container):
    alice, _, conv, conversations, dispatch, keep, omit, foreign = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    brief = TaskBrief(objective=msg["text"], deliverables=["A customer report"])
    service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)
    for unavailable in (pin(foreign), pin(keep).model_copy(update={"expected_version": 2})):
        with pytest.raises(CoworkerError) as denied:
            service.validate(alice, conv["id"], msg["id"], expected_sequence=1,
                             brief=brief, memory_pins=[unavailable])
        assert denied.value.code == "memory_pins_changed"
    preview = service.validate(alice, conv["id"], msg["id"], expected_sequence=1,
                               brief=brief, memory_pins=[pin(keep)])
    assert preview["memory_pins"] == [pin(keep).model_dump(mode="json")]
    options = dict(expected_sequence=1, reviewed_brief=brief, expected_digest=preview["canonical_digest"])
    for different in ([], [pin(omit)]):
        with pytest.raises(CoworkerError) as denied:
            dispatch.dispatch(alice, conv["id"], msg["id"], **options, memory_pins=different)
        assert denied.value.code == "task_brief_digest_mismatch"
    admitted, created = dispatch.dispatch(alice, conv["id"], msg["id"], **options, memory_pins=[pin(keep)])
    assert created
    assert container.agent.worker_run(admitted["run_id"])["id"] == admitted["run_id"]
    replayed, created = dispatch.dispatch(alice, conv["id"], msg["id"], **options, memory_pins=[pin(keep)])
    assert not created and replayed["run_id"] == admitted["run_id"]
    with dispatch.sessions.begin() as db:
        run = db.get(AgentRun, admitted["run_id"])
        run.project_context = {**run.project_context, "memory_pins": [pin(omit).model_dump(mode="json")]}
    with pytest.raises(CoworkerError) as denied:
        container.agent.worker_run(admitted["run_id"])
    assert denied.value.code == "context_sources_changed"


def test_existing_version_one_reviewed_runs_with_pins_remain_replayable(container):
    alice, _, conv, conversations, dispatch, keep, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    brief = TaskBrief(objective=msg["text"], deliverables=["A customer report"])
    service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)
    legacy = service.validate(alice, conv["id"], msg["id"], expected_sequence=1, brief=brief)
    current = service.validate(alice, conv["id"], msg["id"], expected_sequence=1,
                               brief=brief, memory_pins=[pin(keep)])
    options = dict(expected_sequence=1, reviewed_brief=brief, memory_pins=[pin(keep)])
    result, _ = dispatch.dispatch(alice, conv["id"], msg["id"], **options,
                                  expected_digest=current["canonical_digest"])
    with dispatch.sessions.begin() as db:
        run = db.get(AgentRun, result["run_id"])
        old_digest = legacy["canonical_digest"]
        run.reviewed_brief = {**run.reviewed_brief, "schema_version": 1, "canonical_digest": old_digest}
        run.fingerprint = dispatch._dispatch_fingerprint(
            AgentRunCreate(goal=brief.objective, output_language=brief.output_language),
            [], run.project_context, reviewed_digest=old_digest,
        )
    assert container.agent.worker_run(result["run_id"])["id"] == result["run_id"]
    retry, created = dispatch.dispatch(alice, conv["id"], msg["id"], **options,
                                       expected_digest=legacy["canonical_digest"])
    assert not created and retry["run_id"] == result["run_id"]


def test_http_preview_carries_selected_memory_into_the_review_digest(container, signed_client):
    settings = replace(enable_pa04(container), conversations_enabled=True)
    container.settings = settings
    container.conversations.settings = settings
    container.conversation_task_briefs.settings = settings
    container.conversation_dispatch.settings = settings
    client, headers = signed_client
    started = client.post("/api/v1/conversations", json={"title": "Memory review"},
                          headers={**headers(), "Idempotency-Key": "day5-http-conv"})
    assert started.status_code == 201, started.text
    path = "/api/v1/conversations/" + started.json()["id"]
    text = "Create a customer report for the project release."
    added = client.post(path + "/messages", json={"text": text, "client_request_key": "day5-http-turn"},
                        headers=headers())
    assert added.status_code == 201, added.text
    saved = client.post("/api/v1/memory", json={"namespace": "preferences", "key": "reports",
                                             "value": "Keep reports concise."}, headers=headers())
    assert saved.status_code == 201, saved.text
    facts = [pin(saved.json()).model_dump(mode="json")]
    msg_path = path + "/messages/" + added.json()["id"]
    draft = TaskBrief(objective=text, deliverables=["A customer report"]).model_dump(mode="json")
    preview = client.post(msg_path + "/task-brief/preview", json={
        "expected_sequence": 1, "brief": draft, "memory_pins": facts,
    }, headers=headers())
    assert preview.status_code == 200, preview.text
    assert preview.json()["memory_pins"] == facts
    result = client.post(msg_path + "/dispatch", json={
        "expected_sequence": 1, "reviewed_brief": draft, "memory_pins": facts,
        "expected_digest": preview.json()["canonical_digest"],
    }, headers=headers())
    assert result.status_code == 202, result.text


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


def test_selected_memory_rejects_a_workspace_not_owned_by_the_run_owner(container):
    alice, bob, conv, conversations, dispatch, keep, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    accepted, _ = dispatch.dispatch(
        alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[pin(keep)],
    )

    # Simulate inconsistent persisted scope: both the run and the owner's fact
    # point at Bob's workspace. A fact owner check alone would not catch this.
    with dispatch.sessions.begin() as db:
        foreign_workspace_id = db.scalar(
            select(Workspace.id).where(Workspace.owner_id == bob)
        )
        assert foreign_workspace_id is not None
        db.get(MemoryFact, keep["id"]).workspace_id = foreign_workspace_id
        db.get(AgentRun, accepted["run_id"]).workspace_id = foreign_workspace_id

    with pytest.raises(CoworkerError) as denied:
        container.memory.context_for_run(alice, accepted["run_id"])
    assert denied.value.code == "memory_pins_changed"


def test_explicit_empty_selection_stays_empty_when_memory_is_disabled(container):
    alice, _, conv, conversations, dispatch, _, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    accepted, _ = dispatch.dispatch(
        alice, conv["id"], msg["id"], expected_sequence=1, memory_pins=[],
    )

    container.memory.settings = replace(
        container.memory.settings, agent_memory_enabled=False,
    )
    assert container.memory.context_for_run(alice, accepted["run_id"])["facts"] == []


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


def test_reviewed_brief_constraint_overrides_pinned_preference_without_editing_memory(container):
    alice, _, conv, conversations, dispatch, keep, _, _ = seeded(container)
    tone = container.memory.create(alice, MemoryFactCreate(
        namespace="preferences", key="writing.tone", value="Usually write formally.",
    ))
    item = message(conversations, alice, conv, "Create a customer report for the project release.")
    reviewed = TaskBrief(objective=item["text"], deliverables=["A customer report"],
                         constraints=["For this report make it casual and conversational."])
    selected_pins = [pin(tone), pin(keep)]
    service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)
    preview = service.validate(alice, conv["id"], item["id"], expected_sequence=1,
                               brief=reviewed, memory_pins=selected_pins)
    accepted, _ = dispatch.dispatch(alice, conv["id"], item["id"], expected_sequence=1,
                                    reviewed_brief=reviewed, expected_digest=preview["canonical_digest"],
                                    memory_pins=selected_pins)

    context, _ = container.context.planner_context(alice, accepted["run_id"])
    assert [fact["id"] for fact in context["memory_provenance"]] == [keep["id"]]
    saved = next(fact for fact in container.memory.list(alice) if fact["id"] == tone["id"])
    assert saved["version"] == tone["version"] and saved["value"] == tone["value"]


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
