"""CW-06 admission tests: one atomic ledger identity, no external mutation."""
from dataclasses import replace
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import select

from test_coworker import account, container
from services.coworker.conversation_dispatch import ConversationDispatchService
from services.coworker.conversation_repository import ConversationRepository
from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import AgentOutbox, AgentRun, ConversationMessage


def setup(container, *, key="cw06"):
    settings = replace(container.settings, conversations_enabled=True, agent_runtime_enabled=True)
    conversations = ConversationRepository(container.repository.sessions, settings)
    dispatch = ConversationDispatchService(container.repository.sessions, settings, container.agent)
    owner = account(container, key)
    conv, _ = conversations.create(owner, ConversationCreate(title="Reports"), f"{key}-conversation")
    return owner, conv, conversations, dispatch


def message(conversations, owner, conversation, text="Create a detailed report about quarterly sales"):
    value, _ = conversations.append_message(
        owner, conversation["id"], MessageCreate(text=text, client_request_key="message-one"),
    )
    return value


def test_no_implicit_dispatch_on_message_append(container):
    owner, conv, conversations, dispatch = setup(container)
    msg = message(conversations, owner, conv)
    assert msg["resource_links"] == []
    with dispatch.sessions() as db:
        assert db.scalars(select(AgentRun).where(AgentRun.owner_id == owner)).all() == []


def test_explicit_dispatch_is_atomic_and_idempotent(container):
    owner, conv, conversations, dispatch = setup(container)
    msg = message(conversations, owner, conv)
    first, created = dispatch.dispatch(owner, conv["id"], msg["id"], expected_sequence=1)
    assert created and first["replayed"] is False
    second, created = dispatch.dispatch(owner, conv["id"], msg["id"], expected_sequence=1)
    assert not created and second["run_id"] == first["run_id"]
    with dispatch.sessions() as db:
        rows = db.scalars(select(AgentRun).where(AgentRun.owner_id == owner)).all()
        assert len(rows) == 1
        assert rows[0].action_ids == []
        assert rows[0].connector_read_grant_ids == []
        assert db.get(AgentOutbox, rows[0].id) is not None
        saved = db.get(ConversationMessage, msg["id"])
        assert saved.resource_links == [{"resource_type": "agent_run", "resource_id": rows[0].id}]
    activity = dispatch.activity(owner, conv["id"])["items"]
    assert len(activity) == 1 and activity[0]["run_id"] == first["run_id"]


def test_stale_message_revision_is_rejected_without_orphan_run(container):
    owner, conv, conversations, dispatch = setup(container)
    first = message(conversations, owner, conv)
    conversations.append_message(
        owner, conv["id"], MessageCreate(text="Second message", client_request_key="message-two"),
    )
    with pytest.raises(CoworkerError) as failure:
        dispatch.dispatch(owner, conv["id"], first["id"], expected_sequence=1)
    assert failure.value.code == "conversation_revision_conflict"
    with dispatch.sessions() as db:
        assert db.scalars(select(AgentRun).where(AgentRun.owner_id == owner)).all() == []


@pytest.mark.parametrize("text", ["Send this email now", "How are you?", "Pay this invoice"])
def test_unqualified_routes_do_not_create_agent_runs(container, text):
    owner, conv, conversations, dispatch = setup(container, key="route-" + str(len(text)))
    msg = message(conversations, owner, conv, text)
    with pytest.raises(CoworkerError) as denied:
        dispatch.dispatch(owner, conv["id"], msg["id"], expected_sequence=1)
    assert denied.value.code == "conversation_route_unavailable"
    with dispatch.sessions() as db:
        assert db.scalars(select(AgentRun).where(AgentRun.owner_id == owner)).all() == []


def test_owner_isolation_and_deleted_conversation(container):
    owner, conv, conversations, dispatch = setup(container)
    other = account(container, "foreign")
    msg = message(conversations, owner, conv)
    with pytest.raises(CoworkerError) as hidden:
        dispatch.dispatch(other, conv["id"], msg["id"], expected_sequence=1)
    assert hidden.value.code == "not_found"
    with pytest.raises(CoworkerError):
        dispatch.activity(other, conv["id"])
    conversations.delete(owner, conv["id"])
    with pytest.raises(CoworkerError):
        dispatch.dispatch(owner, conv["id"], msg["id"], expected_sequence=1)


def test_runtime_flags_stay_default_off(container):
    owner = account(container)
    service = ConversationDispatchService(container.repository.sessions, container.settings, container.agent)
    with pytest.raises(CoworkerError) as failure:
        service.dispatch(owner, "invalid", "invalid", expected_sequence=1)
    assert failure.value.code == "conversation_dispatch_unavailable"
