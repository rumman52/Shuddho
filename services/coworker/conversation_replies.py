"""Text-only, owner-scoped replies with a single durable inference claim."""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from services.api.shuddho_api.llm_deepseek import DEEPSEEK_ENDPOINT, _post_review
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
MAX_OUTPUT_BYTES = 16000
MAX_STREAM_RESPONSE_BYTES = 1_048_576


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
        """Yield validated text deltas from a bounded, tool-free DeepSeek SSE response."""
        timeout_seconds = min(60, self.settings.model_timeout_seconds)
        payload = {
            "model": self.settings.deepseek_model, "messages": messages,
            "stream": True, "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUTPUT_TOKENS, "temperature": 0.4,
        }
        response_bytes = 0
        output_bytes = 0
        finished = False
        done = False
        data_lines = []
        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
                    transport=self.transport, follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "POST", DEEPSEEK_ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                            "Accept": "text/event-stream",
                        },
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            raise ValueError("Provider unavailable")
                        if "text/event-stream" not in response.headers.get("content-type", "").lower():
                            raise ValueError("Unexpected provider stream")
                        async for line in response.aiter_lines():
                            response_bytes += len(line.encode("utf-8")) + 1
                            if response_bytes > MAX_STREAM_RESPONSE_BYTES:
                                raise ValueError("Provider stream too large")
                            if line.startswith("data:"):
                                data_lines.append(line[5:].lstrip())
                                continue
                            if line or not data_lines:
                                continue
                            data = "\n".join(data_lines)
                            data_lines.clear()
                            if data == "[DONE]":
                                done = True
                                break
                            try:
                                envelope = json.loads(data)
                            except (TypeError, ValueError, UnicodeError) as error:
                                raise ValueError("Malformed provider stream") from error
                            if not isinstance(envelope, dict):
                                raise ValueError("Malformed provider stream")
                            choices = envelope.get("choices")
                            if not isinstance(choices, list) or len(choices) not in (0, 1):
                                raise ValueError("Malformed provider stream")
                            if not choices:  # Optional usage-only frame.
                                continue
                            if finished:
                                raise ValueError("Provider emitted content after its terminal choice")
                            choice = choices[0]
                            if not isinstance(choice, dict):
                                raise ValueError("Malformed provider stream")
                            delta = choice.get("delta") or {}
                            if not isinstance(delta, dict) or delta.get("tool_calls") or delta.get("refusal"):
                                raise ValueError("Unsafe provider stream")
                            content = delta.get("content")
                            if content is not None:
                                if not isinstance(content, str):
                                    raise ValueError("Malformed provider delta")
                                if content:
                                    output_bytes += len(content.encode("utf-8"))
                                    if output_bytes > MAX_OUTPUT_BYTES:
                                        raise ValueError("Provider output too large")
                                    yield content
                            finish_reason = choice.get("finish_reason")
                            if finish_reason is not None:
                                if finish_reason != "stop":
                                    raise ValueError("Incomplete provider output")
                                finished = True
        except (TimeoutError, httpx.TimeoutException, httpx.RequestError) as error:
            raise ValueError("Provider unavailable") from error
        if not done or not finished:
            raise ValueError("Provider stream did not complete")


class ConversationReplyService:
    def __init__(self, conversations, settings, model=None):
        self.conversations, self.settings = conversations, settings
        if model is not None:
            self.model = model
        elif settings.chat_provider == "gemma":
            from .conversation_gemma import GemmaReplyModel
            self.model = GemmaReplyModel(settings)
        elif settings.chat_provider == "deepseek":
            self.model = DeepSeekReplyModel(settings)
        else:
            self.model = None  # Unsupported configuration is refused at admission.
        self.sessions = conversations.sessions
        self._stream_tasks = {}

    def claim(self, owner, conversation_id, message_id, expected_sequence, request_key=None):
        self.conversations.enabled()
        if not isinstance(expected_sequence, int) or expected_sequence < 1:
            raise CoworkerError("invalid_message_revision", "The conversation changed. Refresh it before asking for a reply.", 409)
        with self.sessions.begin() as db:
            self.conversations._lock_account(db, owner)
            conversation = self.conversations._conversation(db, owner, conversation_id, lock=True)
            row = db.scalar(select(ConversationMessage).where(
                ConversationMessage.id == message_id,
                ConversationMessage.owner_id == owner,
                ConversationMessage.conversation_id == conversation_id,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.sequence != expected_sequence:
                raise CoworkerError("conversation_revision_conflict", "The conversation changed. Refresh it before asking for a reply.", 409)
            attempt = 1
            if row.assistant_reply:
                prior = dict(row.assistant_reply)
                if prior.get("state") == "generating":
                    started = datetime.fromisoformat(prior["started_at"])
                    if utcnow() - started > timedelta(seconds=120):
                        prior.update(state="interrupted", error="The reply was interrupted. Send a new message to try again.")
                        row.assistant_reply = prior
                state = prior.get("state")
                if state in {"completed", "generating"}:
                    return prior, None
                if state not in {"failed", "interrupted", "cancelled"} or not request_key or request_key == prior.get("request_key"):
                    return prior, None
                if conversation.message_sequence != expected_sequence:
                    raise CoworkerError("conversation_revision_conflict", "The conversation changed. Refresh it before retrying the reply.", 409)
                attempt = max(1, int(prior.get("attempt", 1))) + 1
            elif conversation.message_sequence != expected_sequence:
                raise CoworkerError("conversation_revision_conflict", "The conversation changed. Refresh it before asking for a reply.", 409)
            if row.selected_sources:
                raise CoworkerError("direct_reply_source_conflict", "Use Start task to work with attached files. Direct chat replies do not read file attachments.", 409)
            history = self.conversations.messages(owner, conversation_id, limit=30)["items"]
            messages, truncated = build_reply_messages(history, expected_sequence=expected_sequence)
            reservation = self._reserve_daily_budget(db, owner, messages)
            self.conversations.acquire_provider_lease(
                db, owner, "conversation_reply", message_id, sequence=attempt,
                lease_seconds=120, max_concurrent=self.settings.max_concurrent_provider_calls,
            )
            row.assistant_reply = {
                "state": "generating", "text": "", "error": None, "started_at": iso(utcnow()),
                "context_truncated": truncated, "attempt": attempt, "request_key": request_key,
            }
            self.conversations._audit(db, owner, "conversation.reply_started", conversation_id, {
                "message_id": message_id, "sequence": expected_sequence, "attempt": attempt,
                "allocated_tokens": reservation,
            })
            return dict(row.assistant_reply), messages

    def release(self, message_id, attempt=1):
        with self.sessions.begin() as db:
            self.conversations.release_provider_lease(db, "conversation_reply", message_id, sequence=attempt)

    def finish(self, owner, conversation_id, message_id, result):
        with self.sessions.begin() as db:
            self.conversations._lock_account(db, owner)
            self.conversations._conversation(db, owner, conversation_id, lock=True)
            row = db.scalar(select(ConversationMessage).where(
                ConversationMessage.id == message_id,
                ConversationMessage.owner_id == owner,
                ConversationMessage.conversation_id == conversation_id,
            ).with_for_update())
            if row is None:
                raise not_found()
            current = dict(row.assistant_reply or {})
            if (
                current.get("state") != "generating"
                or int(current.get("attempt", 1)) != int(result.get("attempt", 1))
                or current.get("request_key") != result.get("request_key")
                or result.get("state") == "generating"
            ):
                return current
            row.assistant_reply = result
            self.conversations._audit(db, owner, f"conversation.reply_{result['state']}", conversation_id, {
                "message_id": message_id, "sequence": row.sequence, "attempt": result.get("attempt", 1),
            })
            return dict(row.assistant_reply)

    def current_reply(self, owner, conversation_id, message_id):
        with self.sessions() as db:
            row = db.scalar(select(ConversationMessage).where(
                ConversationMessage.id == message_id,
                ConversationMessage.owner_id == owner,
                ConversationMessage.conversation_id == conversation_id,
            ))
            return dict(row.assistant_reply) if row is not None and row.assistant_reply is not None else None

    def is_current_attempt(self, owner, conversation_id, message_id, attempt, request_key):
        current = self.current_reply(owner, conversation_id, message_id)
        return bool(current and current.get("state") == "generating"
            and int(current.get("attempt", 1)) == int(attempt)
            and current.get("request_key") == request_key)

    def _cancel_claim(self, owner, conversation_id, message_id, expected_sequence, request_key):
        self.conversations.enabled()
        with self.sessions.begin() as db:
            self.conversations._lock_account(db, owner)
            self.conversations._conversation(db, owner, conversation_id, lock=True)
            row = db.scalar(select(ConversationMessage).where(
                ConversationMessage.id == message_id,
                ConversationMessage.owner_id == owner,
                ConversationMessage.conversation_id == conversation_id,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.sequence != expected_sequence:
                raise CoworkerError("conversation_revision_conflict", "The conversation changed. Refresh it before stopping the reply.", 409)
            if not row.assistant_reply:
                raise CoworkerError("conversation_reply_not_found", "There is no AI reply to stop.", 409)
            prior = dict(row.assistant_reply)
            if prior.get("request_key") != request_key or prior.get("state") != "generating":
                return prior
            stopped = {**prior, "state": "cancelled", "error": "You stopped this reply.", "completed_at": iso(utcnow())}
            row.assistant_reply = stopped
            self.conversations._audit(db, owner, "conversation.reply_cancelled", conversation_id, {
                "message_id": message_id, "sequence": row.sequence, "attempt": prior.get("attempt", 1),
            })
            return dict(row.assistant_reply)

    async def cancel_reply(self, owner, conversation_id, message_id, expected_sequence, request_key):
        stopped = await run_in_threadpool(self._cancel_claim, owner, conversation_id, message_id, expected_sequence, request_key)
        if stopped.get("state") == "cancelled" and stopped.get("request_key") == request_key:
            task = self._stream_tasks.get((message_id, int(stopped.get("attempt", 1))))
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        return stopped

    async def prepare_stream(self, owner, conversation_id, message_id, expected_sequence, request_key=None):
        claim_result, messages = await run_in_threadpool(self.claim, owner, conversation_id, message_id, expected_sequence, request_key)
        if messages is None:
            return claim_result, None
        queue = asyncio.Queue()
        attempt = int(claim_result.get("attempt", 1))

        async def produce():
            parts, output_bytes, result = [], 0, None
            try:
                stream_method = getattr(self.model, "stream", None)
                if callable(stream_method):
                    async for part in stream_method(messages):
                        if not await run_in_threadpool(self.is_current_attempt, owner, conversation_id, message_id, attempt, request_key):
                            break
                        if not isinstance(part, str):
                            raise ValueError("invalid model stream")
                        output_bytes += len(part.encode("utf-8"))
                        if output_bytes > MAX_OUTPUT_BYTES:
                            raise ValueError("reply exceeded output limit")
                        if part:
                            parts.append(part)
                            await queue.put(("delta", {"delta": part}))
                else:
                    part = await self.model.generate(messages)
                    if await run_in_threadpool(self.is_current_attempt, owner, conversation_id, message_id, attempt, request_key):
                        if not isinstance(part, str) or len(part.encode("utf-8")) > MAX_OUTPUT_BYTES:
                            raise ValueError("invalid model response")
                        parts.append(part)
                if await run_in_threadpool(self.is_current_attempt, owner, conversation_id, message_id, attempt, request_key):
                    text = "".join(parts).strip()
                    if not text:
                        raise ValueError("empty model response")
                    result = {**claim_result, "state": "completed", "text": text, "error": None, "completed_at": iso(utcnow())}
                else:
                    result = await run_in_threadpool(self.current_reply, owner, conversation_id, message_id) or {
                        **claim_result, "state": "interrupted", "text": "",
                        "error": "The reply was interrupted. Send a new message to try again.", "completed_at": iso(utcnow()),
                    }
            except asyncio.CancelledError:
                result = await run_in_threadpool(self.current_reply, owner, conversation_id, message_id) or {
                    **claim_result, "state": "interrupted", "text": "",
                    "error": "The reply was interrupted. Send a new message to try again.", "completed_at": iso(utcnow()),
                }
                if result.get("state") == "generating" and int(result.get("attempt", 1)) == attempt:
                    result = {**result, "state": "interrupted", "error": "The reply was interrupted. Send a new message to try again.", "completed_at": iso(utcnow())}
            except Exception:
                result = {**claim_result, "state": "failed", "text": "", "error": "Rukh could not complete this reply. Try again.", "completed_at": iso(utcnow())}
            finally:
                try:
                    await run_in_threadpool(self.release, message_id, attempt)
                except Exception:
                    pass
            try:
                stored = await run_in_threadpool(self.finish, owner, conversation_id, message_id, result)
            except CoworkerError as error:
                await queue.put(("error", {"error": error.message}))
                return
            await queue.put(("final", stored))

        producer_task = asyncio.create_task(produce())
        key = (message_id, attempt)
        self._stream_tasks[key] = producer_task

        def cleanup(task):
            if self._stream_tasks.get(key) is task:
                self._stream_tasks.pop(key, None)

        producer_task.add_done_callback(cleanup)
        return claim_result, queue

    async def stream_events(self, claim_result, queue):
        """Yield the snapshot and queued deltas; the producer survives client disconnect."""
        yield "snapshot", claim_result
        if queue is None:
            if claim_result.get("state") != "generating":
                yield "final", claim_result
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield "keepalive", {}
                continue
            yield event
            if event[0] in {"final", "error"}:
                break

    async def reply(self, owner, conversation_id, message_id, expected_sequence, request_key=None):
        result, messages = await run_in_threadpool(self.claim, owner, conversation_id, message_id, expected_sequence, request_key)
        if messages is None:
            return result
        attempt = int(result.get("attempt", 1))
        try:
            text = await self.model.generate(messages)
            if await run_in_threadpool(self.is_current_attempt, owner, conversation_id, message_id, attempt, request_key):
                result = {**result, "state": "completed", "text": text, "error": None, "completed_at": iso(utcnow())}
            else:
                result = await run_in_threadpool(self.current_reply, owner, conversation_id, message_id) or result
        except Exception:
            result = {**result, "state": "failed", "text": "", "error": "Rukh could not complete this reply. Try again.", "completed_at": iso(utcnow())}
        finally:
            await run_in_threadpool(self.release, message_id, attempt)
        return await run_in_threadpool(self.finish, owner, conversation_id, message_id, result)
