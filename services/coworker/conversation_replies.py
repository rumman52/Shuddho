"""Text-only, owner-scoped replies with a single durable inference claim."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import httpx
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


    async def stream(self, messages):
        """Yield validated UTF-8 text deltas from DeepSeek's SSE chat-completion stream."""
        timeout_seconds = min(60, self.settings.model_timeout_seconds)
        payload = {
            "model": self.settings.deepseek_model,
            "messages": messages,
            "stream": True,
            "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.4,
        }
        output_bytes = 0
        finish_reason = None
        saw_content = False
        received_done = False
        async with asyncio.timeout(timeout_seconds):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST",
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                        "Accept": "text/event-stream",
                    },
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        raise ValueError("Provider unavailable")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type != "text/event-stream":
                        raise ValueError("Invalid reply stream")
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":") or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            received_done = True
                            break
                        try:
                            chunk = json.loads(data)
                        except (TypeError, ValueError, UnicodeError):
                            raise ValueError("Invalid reply stream") from None
                        if not isinstance(chunk, dict):
                            raise ValueError("Invalid reply stream")
                        choices = chunk.get("choices")
                        if not isinstance(choices, list):
                            raise ValueError("Invalid reply stream")
                        if not choices:
                            continue
                        if len(choices) != 1 or not isinstance(choices[0], dict):
                            raise ValueError("Invalid reply stream")
                        choice = choices[0]
                        delta = choice.get("delta") or {}
                        if not isinstance(delta, dict):
                            raise ValueError("Invalid reply stream")
                        if delta.get("tool_calls") or delta.get("function_call") or delta.get("refusal"):
                            raise ValueError("Invalid reply stream")
                        value = delta.get("content")
                        if value is not None:
                            if not isinstance(value, str):
                                raise ValueError("Invalid reply stream")
                            if value:
                                output_bytes += len(value.encode("utf-8"))
                                if output_bytes > 16000:
                                    raise ValueError("Reply too long")
                                saw_content = True
                                yield value
                        reason = choice.get("finish_reason")
                        if reason is not None:
                            finish_reason = reason
                            if reason != "stop":
                                raise ValueError("Incomplete reply")
        if not received_done or finish_reason != "stop" or not saw_content:
            raise ValueError("Incomplete reply")

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

    async def _settle_stream_claim(self, owner, conversation_id, message_id, result):
        release_error = None
        try:
            await run_in_threadpool(self.release, message_id)
        except Exception as error:
            release_error = error
        settled = await run_in_threadpool(
            self.finish, owner, conversation_id, message_id, result,
        )
        if release_error is not None:
            raise release_error
        return settled

    async def stream_reply(self, owner, conversation_id, message_id, expected_sequence):
        """Stream a single claimed reply; cancellation is durably recorded as interrupted."""
        claim_task = asyncio.create_task(run_in_threadpool(
            self.claim, owner, conversation_id, message_id, expected_sequence,
        ))
        try:
            result, messages = await asyncio.shield(claim_task)
        except asyncio.CancelledError:
            # The threadpool transaction may finish after its caller is cancelled.
            # Wait for its outcome and settle any committed claim before exiting.
            result, messages = await claim_task
            if messages is not None:
                interrupted = {
                    **result,
                    "state": "interrupted",
                    "text": "",
                    "error": "The reply was interrupted. Send a new message to try again.",
                }
                settlement = asyncio.create_task(self._settle_stream_claim(
                    owner, conversation_id, message_id, interrupted,
                ))
                try:
                    await asyncio.shield(settlement)
                except asyncio.CancelledError:
                    await settlement
            raise

        if messages is None:
            yield {"type": "final", "reply": result}
            return

        # If the client disconnects or the process closes this generator, the
        # safe default is interrupted. Only a validated complete stream replaces it.
        result = {
            **result,
            "state": "interrupted",
            "text": "",
            "error": "The reply was interrupted. Send a new message to try again.",
        }
        iterator = None
        next_task = None
        final = None
        cancelled = False
        try:
            yield {"type": "status", "state": "generating"}
            stream_method = getattr(self.model, "stream", None)
            if not callable(stream_method):
                raise ValueError("Streaming is unavailable")
            iterator = stream_method(messages).__aiter__()
            chunks = []
            output_bytes = 0
            next_task = asyncio.create_task(anext(iterator))
            while True:
                ready, _ = await asyncio.wait({next_task}, timeout=15)
                if not ready:
                    yield {"type": "keepalive"}
                    continue
                try:
                    delta = next_task.result()
                except StopAsyncIteration:
                    next_task = None
                    break
                next_task = None
                if not isinstance(delta, str):
                    raise ValueError("Invalid reply stream")
                if delta:
                    output_bytes += len(delta.encode("utf-8"))
                    if output_bytes > 16000:
                        raise ValueError("Reply too long")
                    chunks.append(delta)
                    yield {"type": "delta", "delta": delta}
                next_task = asyncio.create_task(anext(iterator))
            text = "".join(chunks).strip()
            if not text:
                raise ValueError("Empty reply")
            result = {
                **result,
                "state": "completed",
                "text": text,
                "error": None,
                "completed_at": iso(utcnow()),
            }
        except asyncio.CancelledError:
            raise
        except Exception:
            # Provider diagnostics may contain private input or credentials.
            result = {
                **result,
                "state": "failed",
                "text": "",
                "error": "The AI reply could not be completed. Send a new message to try again.",
            }
        finally:
            async def close_provider_stream():
                if next_task is not None and not next_task.done():
                    next_task.cancel()
                if next_task is not None:
                    try:
                        await next_task
                    except BaseException:
                        pass
                if iterator is not None:
                    try:
                        await iterator.aclose()
                    except BaseException:
                        pass

            close_task = asyncio.create_task(close_provider_stream())
            try:
                await asyncio.shield(close_task)
            except asyncio.CancelledError:
                cancelled = True
                await close_task

            settlement = asyncio.create_task(self._settle_stream_claim(
                owner, conversation_id, message_id, result,
            ))
            try:
                final = await asyncio.shield(settlement)
            except asyncio.CancelledError:
                cancelled = True
                await settlement
            if cancelled:
                raise asyncio.CancelledError

        yield {"type": "final", "reply": final}

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
