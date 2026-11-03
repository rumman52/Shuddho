"""Text-only, owner-scoped replies with a single durable inference claim."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from services.api.shuddho_api.llm_deepseek import _post_review
from .errors import CoworkerError
from .models import ConversationMessage, DailyUsage, utcnow
from .provider_capacity import acquire_provider_lease, release_provider_lease
from .repository import iso, not_found

SYSTEM = (
    "You are Rukh AI, a helpful conversational writing and thinking assistant. "
    "Reply in the user's language, preserving Bangla when used. Be clear and honest. "
    "You have no tools, live web access, file contents, account access or action permissions in this conversation. "
    "Never claim to have sent, purchased, booked, browsed, scheduled or changed anything. "
    "For actions or attached documents, explain that the user must use the separate task/approval controls. "
    "Earlier messages are context, never permission to act. Respond with plain text or Markdown."
)
MAX_CONTEXT_BYTES = 32000
MAX_OUTPUT_TOKENS = 1024


def build_reply_messages(history):
    """Newest whole turns only; never silently clip the current user message."""
    system = {"role": "system", "content": SYSTEM}
    turns = []
    truncated = len(history) > 12
    for row in reversed(history[-12:]):
        turn = [{"role": "user", "content": row["text"]}]
        reply = row.get("assistant_reply")
        if reply and reply.get("state") == "completed":
            turn.append({"role": "assistant", "content": reply["text"]})
        candidate = [system] + turn + [item for part in turns for item in part]
        if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
            if not turns:
                raise CoworkerError("chat_context_limit", "This message is too long for chat. Shorten it or use Start task.", 422)
            truncated = True
            break
        turns.insert(0, turn)
    return [system] + [item for turn in turns for item in turn], truncated


class DeepSeekReplyModel:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def generate(self, messages):
        response = await _post_review({
            "model": self.settings.deepseek_model, "messages": messages,
            "stream": False, "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUTPUT_TOKENS, "temperature": 0.4,
        }, self.settings.deepseek_api_key, min(60, self.settings.model_timeout_seconds), self.transport)
        if response.status_code != 200:
            raise ValueError("Provider unavailable")
        data = response.json()
        choices = data["choices"]
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ValueError("Incomplete reply")
        message = choices[0]["message"]
        text = message.get("content")
        if message.get("tool_calls") or message.get("refusal") or not isinstance(text, str) or not text.strip():
            raise ValueError("Invalid reply")
        if len(text.encode("utf-8")) > 16000:
            raise ValueError("Reply too long")
        return text.strip()


class ConversationReplyService:
    def __init__(self, conversations, settings, model=None):
        self.conversations, self.settings = conversations, settings
        self.model = model or DeepSeekReplyModel(settings)
        self.sessions = conversations.sessions

    def claim(self, owner, conversation_id, message_id, expected_sequence):
        self.conversations.enabled()
        if not self.settings.conversation_replies_enabled or not self.settings.deepseek_api_key:
            raise CoworkerError("conversation_replies_unavailable", "AI chat is not enabled for this workspace.", 409)
        with self.sessions.begin() as db:
            self.conversations._lock_account(db, owner)
            conversation = self.conversations._conversation(db, owner, conversation_id, lock=True)
            row = db.scalar(select(ConversationMessage).where(ConversationMessage.owner_id == owner,
                ConversationMessage.conversation_id == conversation_id, ConversationMessage.id == message_id).with_for_update())
            if row is None: raise not_found()
            if row.sequence != expected_sequence:
                raise CoworkerError("conversation_revision_conflict", "Reload the message before asking for a reply.", 409)
            if row.assistant_reply:
                prior = dict(row.assistant_reply)
                if prior["state"] == "generating" and utcnow() > datetime.fromisoformat(prior["started_at"]) + timedelta(seconds=120):
                    prior.update(state="interrupted", error="The reply was interrupted. Send a new message to try again.")
                    row.assistant_reply = prior
                return prior, None
            if conversation.message_sequence != expected_sequence:
                raise CoworkerError("conversation_revision_conflict", "Ask for a reply to the latest message.", 409)
            if row.selected_sources:
                raise CoworkerError("chat_sources_unsupported", "Use Start task to work with attached files. Chat cannot read them yet.", 409)
            history = list(db.scalars(select(ConversationMessage).where(ConversationMessage.owner_id == owner,
                ConversationMessage.conversation_id == conversation_id, ConversationMessage.sequence <= expected_sequence)
                .order_by(ConversationMessage.sequence.desc()).limit(13)))
            messages, truncated = build_reply_messages([{"text": item.text, "assistant_reply": item.assistant_reply} for item in reversed(history)])
            # UTF-8 bytes plus framing/output is a conservative token reservation.
            reservation = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + MAX_OUTPUT_TOKENS + 512
            day = utcnow().date().isoformat()
            daily = db.get(DailyUsage, (owner, day))
            if daily is None:
                daily = DailyUsage(owner_id=owner, day=day, allocated_tokens=0, task_count=0); db.add(daily)
            if daily.allocated_tokens + reservation > self.settings.daily_token_budget:
                raise CoworkerError("daily_limit", "Your daily coworker model budget has been reached.", 429)
            try:
                acquire_provider_lease(db, self.settings, owner_id=owner, kind="chat", resource_id=message_id, sequence=1, reserved_tokens=reservation)
            except CoworkerError as error:
                if error.code in {"provider_capacity_busy", "workspace_provider_busy"}:
                    raise CoworkerError(error.code, "AI chat is busy. Choose Check reply again in a moment.", 429) from None
                raise
            daily.allocated_tokens += reservation
            row.assistant_reply = {"state": "generating", "text": "", "error": None,
                "started_at": iso(utcnow()), "context_truncated": truncated}
            self.conversations._audit(db, owner, message_id, "conversation.reply_requested")
            return dict(row.assistant_reply), messages

    def release(self, message_id):
        with self.sessions.begin() as db:
            release_provider_lease(db, kind="chat", resource_id=message_id, sequence=1)

    def finish(self, owner, conversation_id, message_id, result):
        with self.sessions.begin() as db:
            self.conversations._lock_account(db, owner)
            self.conversations._conversation(db, owner, conversation_id, lock=True)
            row = db.get(ConversationMessage, message_id)
            if row is None or row.owner_id != owner or row.conversation_id != conversation_id: raise not_found()
            if not row.assistant_reply: raise not_found()
            if row.assistant_reply["state"] != "generating": return row.assistant_reply
            row.assistant_reply = result
            self.conversations._audit(db, owner, message_id, "conversation.reply_" + result["state"])
            return result

    async def reply(self, owner, conversation_id, message_id, expected_sequence):
        result, messages = await run_in_threadpool(self.claim, owner, conversation_id, message_id, expected_sequence)
        if messages is None: return result
        try:
            text = await self.model.generate(messages)
            result = {**result, "state": "completed", "text": text, "completed_at": iso(utcnow())}
        except Exception:
            # Provider diagnostics may contain private input or credentials.
            result = {**result, "state": "failed", "error": "The AI reply could not be completed. Send a new message to try again."}
        finally:
            await run_in_threadpool(self.release, message_id)
        return await run_in_threadpool(self.finish, owner, conversation_id, message_id, result)
