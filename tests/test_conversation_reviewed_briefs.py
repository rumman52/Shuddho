"""Day 4 reviewed task briefs: authoritative digest, conversation constraints and atomic admission."""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

# The general baseline job intentionally does not install coworker extras.
# The mandatory Day 4 gate runs with those extras and must execute these tests.
pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import select, func
from test_coworker import account, container, signed_client
from services.coworker.agent_runtime import AgentRuntime
from services.coworker.conversation_dispatch import ConversationDispatchService
from services.coworker.conversation_repository import ConversationRepository
from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
from services.coworker.conversation_task_briefs import ConversationTaskBriefService
from services.coworker.task_brief_schemas import TaskBrief, TaskBriefSuggestion
from services.coworker.errors import CoworkerError
from services.coworker.models import AgentRun, AgentOutbox, Artifact, utcnow


def setup(container, key="brief"):
    settings = replace(container.settings, conversations_enabled=True, agent_runtime_enabled=True,
                       agent_runtime_v3_enabled=True, work_services_enabled=True)
    owner = account(container, key)
    messages = ConversationRepository(container.repository.sessions, settings)
    conversation, _ = messages.create(owner, ConversationCreate(title="Brief"), key + "-conversation")
    service = ConversationTaskBriefService(container.repository.sessions, settings)
    dispatch = ConversationDispatchService(container.repository.sessions, settings, container.agent)
    return owner, conversation, messages, service, dispatch


def append(messages, owner, conversation, text, key):
    return messages.append_message(owner, conversation["id"], MessageCreate(
        text=text, client_request_key="task-" + key))[0]


def brief():
    return TaskBrief(objective="Create a detailed report about quarterly sales",
                     constraints=["Maximum two pages", "Use British English"],
                     deliverables=["A concise report"], source_ids=[], output_language="en-GB")


def test_canonical_preview_digest_changes_on_edit(container):
    owner, conversation, messages, service, _ = setup(container, "digest")
    item = append(messages, owner, conversation, "Prepare a two-page report in British English.", "msg-one")
    first = service.validate(owner, conversation["id"], item["id"], expected_sequence=1, brief=brief())
    assert first["brief"]["constraints"] == ["Maximum two pages", "Use British English"]
    assert service.validate(owner, conversation["id"], item["id"], expected_sequence=1, brief=brief())["canonical_digest"] == first["canonical_digest"]
    changed = brief().model_copy(update={"constraints": ["One page"]})
    assert service.validate(owner, conversation["id"], item["id"], expected_sequence=1, brief=changed)["canonical_digest"] != first["canonical_digest"]


def test_ambiguous_second_option_asks_for_input(container):
    owner, conversation, messages, service, _ = setup(container, "ambiguous")
    item = append(messages, owner, conversation, "Use the second option, please.", "msg-one")
    result = asyncio.run(service.propose(owner, conversation["id"], item["id"], expected_sequence=1))
    assert result["state"] == "needs_input" and result["question"]
    assert result["brief"] is None


def test_model_invented_source_id_fails_without_ledger(container):
    owner, conversation, messages, service, dispatch = setup(container, "invented")
    item = append(messages, owner, conversation, "Draft a report.", "msg-one")
    class InventingModel:
        async def propose_task_brief(self, history, source_ids):
            return TaskBriefSuggestion(state="ready", brief=brief().model_copy(
                update={"source_ids": [uuid4()]})), 42
    service.model = InventingModel()
    with pytest.raises(CoworkerError) as failure:
        asyncio.run(service.propose(owner, conversation["id"], item["id"], expected_sequence=1))
    assert failure.value.code == "task_brief_source_invalid"
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_stale_revision_fails_without_run_or_outbox(container):
    owner, conversation, messages, service, dispatch = setup(container, "stale")
    first = append(messages, owner, conversation, "Prepare a report.", "msg-one")
    preview = service.validate(owner, conversation["id"], first["id"], expected_sequence=1, brief=brief())
    append(messages, owner, conversation, "British English only.", "msg-two")
    with pytest.raises(CoworkerError) as failure:
        service.validate(owner, conversation["id"], first["id"], expected_sequence=1, brief=brief())
    assert failure.value.code == "conversation_revision_conflict"
    with pytest.raises(CoworkerError) as failure:
        dispatch.dispatch(owner, conversation["id"], first["id"], expected_sequence=1,
            output_language="en-GB", reviewed_brief=brief(), expected_digest=preview["canonical_digest"])
    assert failure.value.code == "conversation_revision_conflict"
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 0


def test_reviewed_brief_replay_and_changed_brief_conflicts_without_extra_outbox(container):
    owner, conversation, messages, service, dispatch = setup(container, "replay")
    item = append(messages, owner, conversation, "Please write a report.", "msg-one")
    reviewed = brief()
    digest = service.validate(owner, conversation["id"], item["id"],
                              expected_sequence=1, brief=reviewed)["canonical_digest"]
    opts = dict(expected_sequence=1, output_language="en-GB", reviewed_brief=reviewed, expected_digest=digest)
    first, created = dispatch.dispatch(owner, conversation["id"], item["id"], **opts)
    assert created
    second, created = dispatch.dispatch(owner, conversation["id"], item["id"], **opts)
    assert not created and first["run_id"] == second["run_id"]
    with dispatch.sessions() as db:
        run = db.get(AgentRun, first["run_id"])
        assert run.reviewed_brief["brief"]["constraints"] == ["Maximum two pages", "Use British English"]
        assert run.reviewed_brief["brief"]["deliverables"] == ["A concise report"]
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 1
    changed = brief().model_copy(update={"constraints": ["Three pages"]})
    other = service.validate(owner, conversation["id"], item["id"], expected_sequence=1, brief=changed)
    with pytest.raises(CoworkerError) as failure:
        dispatch.dispatch(owner, conversation["id"], item["id"], expected_sequence=1, output_language="en-GB",
                          reviewed_brief=changed, expected_digest=other["canonical_digest"])
    assert failure.value.code == "idempotency_conflict"
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 1


def test_identical_concurrent_replay_one_run(container):
    owner, conversation, messages, service, dispatch = setup(container, "concurrent")
    item = append(messages, owner, conversation, "Produce a report.", "msg-one")
    reviewed = brief()
    digest = service.validate(owner, conversation["id"], item["id"], expected_sequence=1, brief=reviewed)["canonical_digest"]
    def submit(_):
        return dispatch.dispatch(owner, conversation["id"], item["id"], expected_sequence=1,
                                 output_language="en-GB", reviewed_brief=reviewed, expected_digest=digest)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0][0]["run_id"] == results[1][0]["run_id"]
    assert sorted(created for _, created in results) == [False, True]
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 1


def test_multiturn_followup_retains_prior_constraints_in_reviewed_run(container):
    owner, conversation, messages, service, dispatch = setup(container, "multi-turn")
    append(messages, owner, conversation,
           "Write a two-page pricing report in British English.", "msg-one")
    latest = append(messages, owner, conversation,
                    "Create a detailed quarterly sales report with a comparison table.", "msg-two")
    class IncompleteModel:
        async def propose_task_brief(self, history, source_ids):
            assert len(history) == 2
            return TaskBriefSuggestion(state="ready", brief=TaskBrief(
                objective="Create a detailed report about quarterly sales",
                constraints=[], deliverables=["Sales report with comparison table"],
                output_language="en-GB")), 54
    service.model = IncompleteModel()
    preview = asyncio.run(service.propose(
        owner, conversation["id"], latest["id"], expected_sequence=2))
    assert preview["state"] == "ready"
    assert preview["brief"]["constraints"] == ["Maximum two pages", "Use British English"]
    reviewed = TaskBrief.model_validate(preview["brief"])
    result, created = dispatch.dispatch(
        owner, conversation["id"], latest["id"], expected_sequence=2,
        reviewed_brief=reviewed, expected_digest=preview["canonical_digest"],
        output_language="en-GB")
    assert created
    dependencies = container.agent.worker_run(result["run_id"])
    assert dependencies["reviewed_brief"]["brief"]["constraints"] == preview["brief"]["constraints"]
    planner_goal = AgentRuntime._goal_with_project_context(dependencies)
    assert "Maximum two pages" in planner_goal and "Use British English" in planner_goal
    assert "Sales report with comparison table" in planner_goal


def test_previous_turn_source_is_bound_and_deletion_revokes_reviewed_run(container):
    owner, conversation, messages, service, dispatch = setup(container, "prior-source")
    settings = replace(service.settings, context_retrieval_enabled=True)
    service.settings = settings
    dispatch.settings = settings
    data = b"Reviewed milestone: 20 December."
    source = Artifact(id=str(uuid4()), owner_id=owner, filename="milestones.txt",
                      content_type="text/plain", object_key="brief-artifact",
                      sha256=sha256(data).hexdigest(), byte_size=len(data),
                      expires_at=utcnow() + timedelta(days=1))
    with dispatch.sessions.begin() as db:
        db.add(source)
    messages.append_message(owner, conversation["id"], MessageCreate(
        text="Use the uploaded milestone file for the report.",
        client_request_key="prior-source-message",
        selected_resource_ids=[UUID(source.id)]))
    latest = append(messages, owner, conversation,
                    "Create a detailed report about milestone dates.", "msg-two")
    reviewed = brief().model_copy(update={"source_ids": [UUID(source.id)]})
    preview = service.validate(owner, conversation["id"], latest["id"],
                               expected_sequence=2, brief=reviewed)
    run, created = dispatch.dispatch(
        owner, conversation["id"], latest["id"], expected_sequence=2,
        output_language="en-GB", reviewed_brief=reviewed,
        expected_digest=preview["canonical_digest"])
    assert created
    assert container.agent.worker_run(run["run_id"])["artifact_ids"] == [source.id]
    with dispatch.sessions.begin() as db:
        db.delete(db.get(Artifact, source.id))
    with pytest.raises(CoworkerError) as error:
        container.agent.worker_run(run["run_id"])
    assert error.value.code == "context_sources_changed"
    with pytest.raises(CoworkerError) as error:
        dispatch.dispatch(owner, conversation["id"], latest["id"], expected_sequence=2,
                          output_language="en-GB", reviewed_brief=reviewed,
                          expected_digest=preview["canonical_digest"])
    assert error.value.code == "context_sources_changed"
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 1


def test_http_reviewed_preview_and_dispatch_endpoint(container, signed_client):
    settings = replace(container.settings, conversations_enabled=True,
                       agent_runtime_enabled=True, agent_runtime_v3_enabled=True,
                       work_services_enabled=True)
    container.settings = settings
    container.conversations.settings = settings
    container.conversation_task_briefs.settings = settings
    container.conversation_dispatch.settings = settings
    client, headers = signed_client
    started = client.post("/api/v1/conversations", json={"title": "Day 4 review"},
                          headers={**headers(), "Idempotency-Key": "day4-http-conv"})
    assert started.status_code == 201, started.text
    path = "/api/v1/conversations/" + started.json()["id"]
    added = client.post(path + "/messages", json={
        "text": "Create a detailed report about quarterly sales",
        "client_request_key": "day4-http-message",
    }, headers=headers())
    assert added.status_code == 201, added.text
    msg_path = path + "/messages/" + added.json()["id"]
    preview = client.post(msg_path + "/task-brief/preview", json={
        "expected_sequence": 1, "brief": brief().model_dump(mode="json")}, headers=headers())
    assert preview.status_code == 200, preview.text
    digest = preview.json()["canonical_digest"]
    assert len(digest) == 64
    payload = {"expected_sequence": 1, "reviewed_brief": brief().model_dump(mode="json"),
               "expected_digest": digest, "output_language": "en-GB"}
    created = client.post(msg_path + "/dispatch", json=payload, headers=headers())
    assert created.status_code == 202, created.text
    replay = client.post(msg_path + "/dispatch", json=payload, headers=headers())
    assert replay.status_code == 200 and replay.json()["run_id"] == created.json()["run_id"]
    assert replay.headers["Idempotent-Replayed"] == "true"


def test_additive_migration_works_with_old_reader_and_default(tmp_path):
    """An existing SQL reader continues to work after the additive schema upgrade."""
    from alembic import command
    from sqlalchemy import create_engine, inspect, text
    from services.coworker.migrate import migration_config
    url = f"sqlite:///{tmp_path / 'day4-migrate.sqlite3'}"
    config = migration_config(url)
    command.upgrade(config, "0068_fly_repository_coding")
    engine = create_engine(url)
    try:
        with engine.connect() as db:
            assert "reviewed_brief" not in {
                column["name"] for column in inspect(db).get_columns("cw_agent_runs")
            }
            assert db.execute(text("SELECT id, goal, output_language FROM cw_agent_runs")).all() == []
        command.upgrade(config, "head")
        with engine.connect() as db:
            columns = {column["name"] for column in inspect(db).get_columns("cw_agent_runs")}
            assert "reviewed_brief" in columns
            assert db.execute(text("SELECT id, goal, output_language FROM cw_agent_runs")).all() == []
            assert db.execute(text("SELECT version_num FROM cw_alembic_version")).scalar() == "0069_conversation_task_briefs"
    finally:
        engine.dispose()
