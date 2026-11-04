"""Real repository, ownership and provider-admission boundary regressions."""
import asyncio
from dataclasses import replace
from uuid import uuid4
import pytest
pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")
from test_coworker import account, container, signed_client
from services.coworker.conversation_replies import ConversationReplyService, build_reply_messages
from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import ConversationMessage, DailyUsage, ProviderLease
from sqlalchemy import select

class Model:
    def __init__(self): self.calls = 0; self.history = None; self.callback = None
    async def generate(self, history):
        self.calls += 1; self.history = history
        if self.callback: self.callback()
        return "আপনার প্রশ্নের উত্তর।"

def setup(container):
    settings = replace(container.settings, conversations_enabled=True, conversation_replies_enabled=True, deepseek_api_key="test-only")
    container.settings = settings; container.conversations.settings = settings
    model = Model()
    service = ConversationReplyService(container.conversations, settings, model)
    container.conversation_replies = service
    owner = account(container)
    conversation, _ = container.conversations.create(owner, ConversationCreate(title="Chat"), "conversation-key")
    message, _ = container.conversations.append_message(owner, conversation["id"], MessageCreate(text="Explain recursion in Bangla", client_request_key="message-key"))
    return service, model, owner, conversation, message

def reply(data):
    service, _, owner, conversation, message = data
    return asyncio.run(service.reply(owner, conversation["id"], message["id"], 1))

def test_reply_is_durable_and_duplicate_request_does_not_infer_twice(container):
    data = setup(container)
    result = reply(data)
    assert result["state"] == "completed" and result["text"] == "আপনার প্রশ্নের উত্তর।"
    assert reply(data) == result
    assert data[1].calls == 1
    stored = container.conversations.messages(data[2], data[3]["id"])["items"][0]
    assert stored["assistant_reply"] == result
    with container.repository.sessions() as db:
        assert db.scalar(select(ProviderLease)) is None
        assert db.scalar(select(DailyUsage)).allocated_tokens > 0

def test_foreign_owner_and_stale_revision_do_not_call_model(container):
    data = setup(container); service, model, owner, conversation, message = data
    with pytest.raises(CoworkerError) as error:
        asyncio.run(service.reply(account(container, "other"), conversation["id"], message["id"], 1))
    assert error.value.status_code == 404
    with pytest.raises(CoworkerError):
        asyncio.run(service.reply(owner, conversation["id"], message["id"], 2))
    assert model.calls == 0

def test_reply_default_off(container):
    container.conversations.settings = replace(container.settings, conversations_enabled=True)
    with pytest.raises(CoworkerError) as error:
        asyncio.run(container.conversation_replies.reply(account(container), str(uuid4()), str(uuid4()), 1))
    assert error.value.code == "conversation_replies_unavailable"

def test_budget_failure_has_no_claim_or_provider_call(container):
    data = setup(container); service, model, *_ = data
    service.settings = replace(service.settings, daily_token_budget=1)
    with pytest.raises(CoworkerError): reply(data)
    assert model.calls == 0
    with container.repository.sessions() as db:
        assert db.get(ConversationMessage, data[4]["id"]).assistant_reply is None

def test_deletion_during_inference_discards_output(container):
    data = setup(container)
    data[1].callback = lambda: container.conversations.delete(data[2], data[3]["id"])
    with pytest.raises(CoworkerError): reply(data)
    with container.repository.sessions() as db:
        assert db.get(ConversationMessage, data[4]["id"]).assistant_reply is None

def test_model_failure_is_visible_and_not_silently_retried(container):
    data = setup(container)
    def fail(): raise RuntimeError("sensitive provider details")
    data[1].callback = fail
    result = reply(data)
    assert result["state"] == "failed"
    assert "sensitive" not in str(result)
    assert reply(data) == result and data[1].calls == 1

def test_same_claim_in_flight_does_not_start_a_second_request(container):
    data = setup(container)
    observed = []
    data[1].callback = lambda: observed.append(data[0].claim(data[2], data[3]["id"], data[4]["id"], 1)[0])
    reply(data)
    assert observed[0]["state"] == "generating" and data[1].calls == 1

def test_context_is_bounded_and_preserves_latest_user_message():
    history = [{"text": "old" * 1000, "assistant_reply": {"state": "completed", "text": "answer" * 1000}} for _ in range(50)]
    history.append({"text": "নতুন প্রশ্ন", "assistant_reply": None})
    messages, truncated = build_reply_messages(history)
    import json
    assert len(json.dumps(messages, ensure_ascii=False).encode()) <= 32000
    assert messages[-1] == {"role": "user", "content": "নতুন প্রশ্ন"}
    assert truncated

def test_public_reply_route_is_owned_and_not_cacheable(container, signed_client):
    data = setup(container); client, headers = signed_client
    path = f'/api/v1/conversations/{data[3]["id"]}/messages/{data[4]["id"]}/reply'
    result = client.post(path, json={"expected_sequence": 1}, headers=headers())
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["state"] == "completed"
    assert client.post(path, json={"expected_sequence": 1}, headers=headers("bob")).status_code == 404

def test_history_reports_interrupted_claim_after_process_loss(container):
    data = setup(container)
    service, _, owner, conversation, message = data
    service.claim(owner, conversation["id"], message["id"], 1)
    from datetime import timedelta
    from services.coworker.models import utcnow
    with service.sessions.begin() as db:
        row = db.get(ConversationMessage, message["id"])
        row.assistant_reply = {**row.assistant_reply, "started_at": (utcnow() - timedelta(minutes=5)).isoformat()}
    stored = container.conversations.messages(owner, conversation["id"])["items"][0]
    assert stored["assistant_reply"]["state"] == "interrupted"
    assert reply(data)["state"] == "interrupted" and data[1].calls == 0

def test_active_reply_refuses_account_erasure_cleanly(container):
    data = setup(container)
    data[0].claim(data[2], data[3]["id"], data[4]["id"], 1)
    with pytest.raises(CoworkerError) as error:
        container.retention.erase_account(data[2])
    assert error.value.code == "account_active" and error.value.status_code == 409

def test_expired_reply_lease_does_not_prevent_account_erasure(container):
    from datetime import timedelta
    from services.coworker.models import Account, ProviderDailyUsage, utcnow
    data = setup(container)
    data[0].claim(data[2], data[3]["id"], data[4]["id"], 1)
    with data[0].sessions.begin() as db:
        db.scalar(select(ProviderLease)).expires_at = utcnow() - timedelta(minutes=1)
    assert container.retention.erase_account(data[2])["database_erased"]
    with data[0].sessions() as db:
        assert db.get(Account, data[2]) is None
        assert db.get(ConversationMessage, data[4]["id"]) is None
        assert db.scalar(select(ProviderLease)) is None
        # Anonymous aggregate cost still counts; erasure must not refund usage.
        assert db.scalar(select(ProviderDailyUsage)).allocated_tokens > 0
    with pytest.raises(CoworkerError) as error:
        data[0].finish(data[2], data[3]["id"], data[4]["id"], {"state": "completed", "text": "late output"})
    assert error.value.status_code == 404

def test_completed_reply_is_removed_with_account(container):
    data = setup(container)
    reply(data)
    assert container.retention.erase_account(data[2])["database_erased"]
    with data[0].sessions() as db:
        assert db.get(ConversationMessage, data[4]["id"]) is None

@pytest.mark.parametrize("field", ["provider_daily_token_budget", "provider_max_reserved_tokens"])
def test_shared_provider_limits_prevent_claim_and_inference(container, field):
    data = setup(container)
    data[0].settings = replace(data[0].settings, **{field: 1})
    with pytest.raises(CoworkerError) as error: reply(data)
    assert error.value.status_code == 429 and data[1].calls == 0
    if field == "provider_max_reserved_tokens":
        assert "Check reply again" in str(error.value)
    with data[0].sessions() as db:
        assert db.get(ConversationMessage, data[4]["id"]).assistant_reply is None
        assert db.scalar(select(ProviderLease)) is None

def test_oversized_latest_input_is_rejected_without_silent_clipping():
    with pytest.raises(CoworkerError) as error:
        build_reply_messages([{"text": "বাংলা" * 3000}])
    assert error.value.code == "chat_context_limit"

@pytest.mark.parametrize("choice", [
    {"finish_reason": "length", "message": {"content": "partial"}},
    {"finish_reason": "stop", "message": {"content": ""}},
    {"finish_reason": "stop", "message": {"content": "fake action", "tool_calls": [{}]}},
    {"finish_reason": "stop", "message": {"content": "x" * 16001}},
])
def test_model_rejects_incomplete_or_tool_output(container, choice):
    import httpx
    from services.coworker.conversation_replies import DeepSeekReplyModel
    model = DeepSeekReplyModel(replace(container.settings, deepseek_api_key="test-only"),
        httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [choice]})))
    with pytest.raises(ValueError): asyncio.run(model.generate([{"role": "user", "content": "Hi"}]))

def test_model_transport_uses_backend_provider_and_no_tools(container):
    import httpx, json
    from services.coworker.conversation_replies import DeepSeekReplyModel
    def respond(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        body = json.loads(request.content)
        assert "tools" not in body and body["max_tokens"] == 1024
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "সঠিক উত্তর"}}]})
    model = DeepSeekReplyModel(replace(container.settings, deepseek_api_key="test-only"), httpx.MockTransport(respond))
    assert asyncio.run(model.generate([{"role": "user", "content": "Hi"}])) == "সঠিক উত্তর"
