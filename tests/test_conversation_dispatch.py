"""CW-06 admission tests: one atomic ledger identity, no external mutation."""
from dataclasses import replace
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import select

from test_coworker import account, container, signed_client
from services.coworker.conversation_dispatch import ConversationDispatchService
from services.coworker.conversation_repository import ConversationRepository
from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import AgentOutbox, AgentRun, ConversationMessage


def setup(container, *, key="cw06"):
    settings = replace(container.settings, conversations_enabled=True, agent_runtime_enabled=True, work_services_enabled=True)
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


def test_revision_checked_cancel_disarms_outbox_and_allows_deletion(container):
    owner, conv, conversations, dispatch = setup(container, key="cw06-cancel")
    msg = message(conversations, owner, conv)
    admitted, _ = dispatch.dispatch(owner, conv["id"], msg["id"], expected_sequence=1)
    before = dispatch.activity(owner, conv["id"])["items"][0]
    with pytest.raises(CoworkerError) as stale:
        dispatch.cancel(owner, conv["id"], msg["id"], expected_sequence=1,
                        expected_event_sequence=before["event_sequence"] + 1)
    assert stale.value.code == "agent_revision_conflict"
    with pytest.raises(CoworkerError) as active:
        conversations.delete(owner, conv["id"])
    assert active.value.code == "conversation_active_work"
    cancelled = dispatch.cancel(owner, conv["id"], msg["id"], expected_sequence=1,
                                expected_event_sequence=before["event_sequence"])
    assert cancelled["state"] == "cancelled"
    assert dispatch.cancel(owner, conv["id"], msg["id"], expected_sequence=1,
                           expected_event_sequence=before["event_sequence"])["state"] == "cancelled"
    with dispatch.sessions() as db:
        run = db.get(AgentRun, admitted["run_id"])
        assert run.cancel_requested
        assert db.get(AgentOutbox, run.id).delivered is True
    assert conversations.delete(owner, conv["id"])["deleted"] is True


def test_cancel_wrong_owner_is_hidden(container):
    owner, conv, conversations, dispatch = setup(container, key="cw06-owner-cancel")
    msg = message(conversations, owner, conv)
    dispatch.dispatch(owner, conv["id"], msg["id"], expected_sequence=1)
    foreign = account(container, "cw06-foreign")
    with pytest.raises(CoworkerError) as denied:
        dispatch.cancel(foreign, conv["id"], msg["id"],
                        expected_sequence=1, expected_event_sequence=1)
    assert denied.value.code == "not_found"


def test_http_conversation_dispatch_and_activity_contract(container, signed_client):
    container.settings = replace(container.settings, conversations_enabled=True, agent_runtime_enabled=True, work_services_enabled=True)
    container.conversations.settings = container.settings
    container.conversation_dispatch.settings = container.settings
    client, headers = signed_client
    auth = headers() | {"Idempotency-Key": "cw06-http-conversation-key"}
    created = client.post("/api/v1/conversations", json={"title": "Reports"}, headers=auth)
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    path = f"/api/v1/conversations/{conversation_id}"
    added = client.post(path + "/messages", json={
        "text": "Create a detailed report about quarterly sales",
        "client_request_key": "cw06-http-message-key",
    }, headers=headers())
    assert added.status_code == 201, added.text
    msg = added.json()
    endpoint = path + "/messages/" + msg["id"] + "/dispatch"
    admitted = client.post(endpoint, json={"expected_sequence": 1}, headers=headers())
    assert admitted.status_code == 202, admitted.text
    assert admitted.json()["run_id"]
    replay = client.post(endpoint, json={"expected_sequence": 1}, headers=headers())
    assert replay.status_code == 200 and replay.json()["run_id"] == admitted.json()["run_id"]
    activity = client.get(path + "/activity", headers=headers())
    assert activity.status_code == 200
    event = activity.json()["items"][0]
    assert event["run_id"] == admitted.json()["run_id"]
    cancel = client.post(path + "/messages/" + msg["id"] + "/cancel", json={
        "expected_sequence": 1, "expected_event_sequence": event["event_sequence"],
    }, headers=headers())
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["state"] == "cancelled"
    assert client.post("/api/v1/agent-runs", json={"goal": msg["text"]}, headers={
        **headers(), "Idempotency-Key": "conversation:" + msg["id"],
    }).status_code == 409


def test_activity_cursor_replays_pages_and_skips_unlaunched_messages(container):
    """Reading paginated activity must never launch or duplicate Agent work."""
    owner, conv, conversations, dispatch = setup(container, key="cw07-cursor")
    first = message(conversations, owner, conv)
    first_run, _ = dispatch.dispatch(owner, conv["id"], first["id"], expected_sequence=1)
    idle, _ = conversations.append_message(
        owner, conv["id"], MessageCreate(
            text="Keep this note without launching work", client_request_key="cw07-idle-message",
        ),
    )
    third, _ = conversations.append_message(
        owner, conv["id"], MessageCreate(
            text="Create a detailed report about annual sales", client_request_key="cw07-third-message",
        ),
    )
    last_run, _ = dispatch.dispatch(owner, conv["id"], third["id"], expected_sequence=3)

    one = dispatch.activity(owner, conv["id"], after="start", limit=1)
    assert one["has_more"] is True
    assert [item["run_id"] for item in one["items"]] == [first_run["run_id"]]
    two = dispatch.activity(owner, conv["id"], after=one["next_cursor"], limit=1)
    assert two["has_more"] is True and two["items"] == []
    three = dispatch.activity(owner, conv["id"], after=two["next_cursor"], limit=1)
    assert three["has_more"] is False
    assert [item["run_id"] for item in three["items"]] == [last_run["run_id"]]
    final = dispatch.activity(owner, conv["id"], after=three["next_cursor"], limit=1)
    assert final["items"] == [] and final["next_cursor"] == three["next_cursor"]
    assert final["has_more"] is False
    assert idle["sequence"] == 2
    with dispatch.sessions() as db:
        assert len(db.scalars(select(AgentRun).where(AgentRun.owner_id == owner)).all()) == 2

    # Without a cursor, the legacy snapshot still observes new run-state changes
    # on old messages; a message-only cursor cannot represent Agent event revisions.
    snapshot = dispatch.activity(owner, conv["id"])
    assert [item["run_id"] for item in snapshot["items"]] == [first_run["run_id"], last_run["run_id"]]
    current_event_sequence = snapshot["items"][-1]["event_sequence"]
    dispatch.cancel(owner, conv["id"], third["id"], expected_sequence=3,
                    expected_event_sequence=current_event_sequence)
    refreshed = dispatch.activity(owner, conv["id"])
    assert refreshed["items"][-1]["state"] == "cancelled"


def test_activity_cursors_reject_wrong_conversation_and_malformed_input(container):
    owner, conv, conversations, dispatch = setup(container, key="cw07-cursor-scope")
    first = message(conversations, owner, conv)
    dispatch.dispatch(owner, conv["id"], first["id"], expected_sequence=1)
    cursor = dispatch.activity(owner, conv["id"], after="start", limit=1)["next_cursor"]
    another, _ = conversations.create(
        owner, ConversationCreate(title="Other"), "cw07-cursor-other-conversation",
    )
    with pytest.raises(CoworkerError) as wrong_conversation:
        dispatch.activity(owner, another["id"], after=cursor)
    assert wrong_conversation.value.code == "invalid_cursor"

    foreign = account(container, "cw07-cursor-foreign")
    with pytest.raises(CoworkerError) as wrong_owner:
        dispatch.activity(foreign, conv["id"], after=cursor)
    assert wrong_owner.value.code == "not_found"

    for invalid in ["1", "v1:anything:1", "v1:bad:99999", "v1:bad:-1", "v1:bad:00", "a" * 128]:
        with pytest.raises(CoworkerError) as bad:
            dispatch.activity(owner, conv["id"], after=invalid)
        assert bad.value.code == "invalid_cursor"

