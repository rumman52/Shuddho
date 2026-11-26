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
    implicit = client.post(msg_path + "/task-brief/preview", json={
        "expected_sequence": 1, "brief": draft,
    }, headers=headers())
    explicit_empty = client.post(msg_path + "/task-brief/preview", json={
        "expected_sequence": 1, "brief": draft, "memory_pins": [],
    }, headers=headers())
    assert implicit.status_code == 200 and explicit_empty.status_code == 200
    assert implicit.json()["canonical_digest"] != explicit_empty.json()["canonical_digest"]
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


def test_explicit_empty_reviewed_selection_has_distinct_digest_and_one_admission(container):
    alice, _, conv, conversations, dispatch, _, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    brief = TaskBrief(objective=msg["text"], deliverables=["A customer report"])
    service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)
    legacy = service.validate(alice, conv["id"], msg["id"], expected_sequence=1, brief=brief)
    empty = service.validate(alice, conv["id"], msg["id"], expected_sequence=1,
                             brief=brief, memory_pins=[])
    assert legacy["canonical_digest"] != empty["canonical_digest"]
    options = dict(expected_sequence=1, reviewed_brief=brief, memory_pins=[])

    with pytest.raises(CoworkerError) as denied:
        dispatch.dispatch(alice, conv["id"], msg["id"], **options,
                          expected_digest=legacy["canonical_digest"])
    assert denied.value.code == "task_brief_digest_mismatch"
    created, first = dispatch.dispatch(alice, conv["id"], msg["id"], **options,
                                       expected_digest=empty["canonical_digest"])
    assert first
    replay, again = dispatch.dispatch(alice, conv["id"], msg["id"], **options,
                                      expected_digest=empty["canonical_digest"])
    assert not again and replay["run_id"] == created["run_id"]
    with dispatch.sessions() as db:
        run = db.get(AgentRun, created["run_id"])
        assert run.reviewed_brief["schema_version"] == 2
        assert run.project_context["memory_pins"] == []
        assert run.memory_namespaces == []
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 1
    assert container.agent.worker_run(created["run_id"])["id"] == created["run_id"]
    assert container.memory.context_for_run(alice, created["run_id"])["facts"] == []
    with pytest.raises(CoworkerError) as denied:
        dispatch.dispatch(alice, conv["id"], msg["id"], expected_sequence=1,
                          reviewed_brief=brief, memory_pins=None,
                          expected_digest=empty["canonical_digest"])
    assert denied.value.code == "idempotency_conflict"


def test_historical_v1_empty_selection_still_replays(container):
    alice, _, conv, conversations, dispatch, _, _, _ = seeded(container)
    msg = message(conversations, alice, conv, "Create a customer report for the project release.")
    brief = TaskBrief(objective=msg["text"], deliverables=["A customer report"])
    service = ConversationTaskBriefService(dispatch.sessions, dispatch.settings)
    legacy = service.validate(alice, conv["id"], msg["id"], expected_sequence=1, brief=brief)
    admitted, _ = dispatch.dispatch(
        alice, conv["id"], msg["id"], expected_sequence=1, reviewed_brief=brief,
        expected_digest=legacy["canonical_digest"], memory_pins=None,
    )
    # Earlier code wrote v1 snapshots even when an empty selection was supplied.
    with dispatch.sessions.begin() as db:
        run = db.get(AgentRun, admitted["run_id"])
        run.project_context = {**run.project_context, "memory_pins": []}
        run.fingerprint = dispatch._dispatch_fingerprint(
            AgentRunCreate(goal=brief.objective, output_language=brief.output_language),
            [], run.project_context, reviewed_digest=legacy["canonical_digest"],
        )
    replay, created = dispatch.dispatch(
        alice, conv["id"], msg["id"], expected_sequence=1, reviewed_brief=brief,
        expected_digest=legacy["canonical_digest"], memory_pins=[],
    )
    assert not created and replay["run_id"] == admitted["run_id"]


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


@pytest.mark.parametrize("key", ["AKIA" + "A" * 16, "eyJ" + "a" * 8 + "." + "b" * 8 + "." + "c" * 8])
@pytest.mark.parametrize("selected", [False, True])
def test_sensitive_memory_key_never_enters_planner_context(container, key, selected):
    alice, _, conv, conversations, dispatch, keep, omit, _ = seeded(container)
    sensitive = container.memory.create(alice, MemoryFactCreate(
        namespace="project", key=key, value="Public metadata.",
    ))
    if selected:
        msg = message(conversations, alice, conv, "Create a customer report for the project release.")
        admitted, _ = dispatch.dispatch(
            alice, conv["id"], msg["id"], expected_sequence=1,
            memory_pins=[pin(sensitive), pin(keep)],
        )
        run_id = admitted["run_id"]
        expected = {keep["id"]}
    else:
        run, _ = container.agent.create(alice, AgentRunCreate(
            goal="Create a customer report for the project release.",
            memory_namespaces=["project"],
        ), "day5-sensitive-memory-key")
        run_id = run["id"]
        expected = {keep["id"], omit["id"]}
    memory = container.memory.context_for_run(alice, run_id)
    context, _ = container.context.planner_context(alice, run_id)
    assert key not in str(memory)
    assert key not in str(context)
    assert {p["id"] for p in memory["provenance"]} == expected
    assert {p["id"] for p in context["memory_provenance"]} == expected
    saved = next(fact for fact in container.memory.list(alice) if fact["id"] == sensitive["id"])
    assert saved["key"] == key and saved["version"] == sensitive["version"]


def _brief_provider_probe(container, *, usage=None, choice_fields=None, message_fields=None, extra=None):
    import httpx
    from services.coworker.agent_planning_model import DeepSeekAgentPlanner
    from services.coworker.task_brief_schemas import TaskBriefSuggestion

    suggestion = TaskBriefSuggestion(state="ready", brief=TaskBrief(
        objective="Make a report", deliverables=["Report"]))
    body = {"choices": [{"finish_reason": "stop", "message": {
        "content": suggestion.model_dump_json(), **(message_fields or {}),
    }, **(choice_fields or {})}], "usage": usage, **(extra or {})}
    settings = replace(container.settings, deepseek_api_key="test-only")
    model = DeepSeekAgentPlanner(settings, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=body)))
    return suggestion, model, settings


@pytest.mark.parametrize("usage,expected", [
    ({"total_tokens": -1}, None), ("unknown", None), ({"total_tokens": False}, None),
    (None, None), ({"total_tokens": 40}, 40),
])
def test_task_brief_provider_usage_is_known_or_conservatively_unknown(container, usage, expected):
    import asyncio

    suggestion, model, _ = _brief_provider_probe(container, usage=usage)
    value, tokens = asyncio.run(model.propose_task_brief(
        [{"sequence": 1, "text": "Make a report", "source_ids": []}], []))
    assert value == suggestion and tokens == expected


@pytest.mark.parametrize("kwargs", [
    {"message_fields": {"role": "user"}},
    {"choice_fields": {"index": 1}},
    {"choice_fields": {"index": False}},
    {"message_fields": {"function_call": {"name": "send_email"}}},
    {"extra": {"error": {"message": "synthetic error"}}},
])
def test_task_brief_provider_rejects_untrusted_completion_envelope(container, kwargs):
    import asyncio
    from services.coworker.agent_planning_model import PlannerFailure

    _, model, _ = _brief_provider_probe(container, usage={"total_tokens": -1}, **kwargs)
    with pytest.raises(PlannerFailure) as error:
        asyncio.run(model.propose_task_brief(
            [{"sequence": 1, "text": "Make a report", "source_ids": []}], []))
    assert error.value.code == "invalid_task_brief"
    assert error.value.total_tokens is None


def test_task_brief_accepts_explicit_assistant_single_choice(container):
    import asyncio

    suggestion, model, _ = _brief_provider_probe(container, usage={"total_tokens": 40},
        choice_fields={"index": 0}, message_fields={"role": "assistant"})
    assert asyncio.run(model.propose_task_brief(
        [{"sequence": 1, "text": "Make a report", "source_ids": []}], [])) == (suggestion, 40)


def test_task_brief_negative_usage_does_not_refund_provider_reservation(container):
    import asyncio
    from services.coworker.models import ProviderDailyUsage, ProviderLease

    alice, conv, conversations, dispatch = setup(container, key="brief-negative-usage")
    msg = message(conversations, alice, conv, "Make a report")
    _, model, _ = _brief_provider_probe(container, usage={"total_tokens": -1})
    service = ConversationTaskBriefService(dispatch.sessions,
        replace(dispatch.settings, deepseek_api_key="test-only"), planner=model)
    with dispatch.sessions() as db:
        before = db.scalar(select(func.coalesce(func.sum(ProviderDailyUsage.allocated_tokens), 0)))
    result = asyncio.run(service.propose(alice, conv["id"], msg["id"], expected_sequence=1))
    assert result["state"] == "ready"
    with dispatch.sessions() as db:
        after = db.scalar(select(func.coalesce(func.sum(ProviderDailyUsage.allocated_tokens), 0)))
        assert after > before
        assert db.scalar(select(func.count()).select_from(ProviderLease)) == 0
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 0
