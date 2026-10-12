"""CW-06/07: atomic, bounded conversation admission into the existing Agent ledger.

No user text grants ExternalAction authority. PostgreSQL serializes each owner's
admissions with the same Account lock used by the other ledgers.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from .agent_repository import ACTIVE_RUN_STATES, AGENT_TERMINAL_STATES
from .agent_router import qualify_agent_goal
from .agent_schemas import AgentRunCreate
from .conversation_context import require_current_selected_sources
from .errors import CoworkerError
from .models import (
    Account, AgentEvent, AgentOutbox, AgentRun, AgentStep, Conversation,
    ConversationMessage, Workspace, utcnow,
)
from .repository import iso, not_found


class ConversationDispatchService:
    def __init__(self, sessions, settings, agent):
        self.sessions, self.settings, self.agent = sessions, settings, agent

    def _enabled(self):
        if not self.settings.conversations_enabled or not self.settings.agent_runtime_enabled:
            raise CoworkerError(
                "conversation_dispatch_unavailable",
                "Conversation work requires enabled conversations and Agent runtime.",
                409,
            )

    @staticmethod
    def _lock_account(db, owner):
        if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
            raise not_found()

    @staticmethod
    def _conversation(db, owner, conversation_id):
        row = db.scalar(select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_id == owner,
            Conversation.deleted.is_(False),
        ).with_for_update())
        if row is None:
            raise not_found()
        return row

    @staticmethod
    def _message(db, owner, conversation_id, message_id):
        row = db.scalar(select(ConversationMessage).where(
            ConversationMessage.id == message_id,
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.owner_id == owner,
        ).with_for_update())
        if row is None:
            raise not_found()
        return row

    def dispatch(self, owner: str, conversation_id: str, message_id: str, *, expected_sequence: int,
                 output_language: str = "auto") -> tuple[dict, bool]:
        """Commit message link, run, initial event/checkpoint and outbox together."""
        self._enabled()
        if expected_sequence < 1:
            raise CoworkerError("conversation_revision_conflict", "Reload the latest messages.", 409)
        with self.sessions.begin() as db:
            self._lock_account(db, owner)
            conversation = self._conversation(db, owner, conversation_id)
            message = self._message(db, owner, conversation_id, message_id)
            links = message.resource_links or []
            existing = [link for link in links if link.get("resource_type") == "agent_run"]
            if existing:
                run = db.scalar(select(AgentRun).where(
                    AgentRun.id == existing[0].get("resource_id"),
                    AgentRun.owner_id == owner,
                ))
                if run is None:
                    raise CoworkerError("conversation_run_missing", "The linked run is unavailable.", 409)
                return {"run_id": run.id, "state": run.state, "message_id": message.id,
                        "conversation_id": conversation.id, "replayed": True}, False
            if conversation.message_sequence != expected_sequence or message.sequence != expected_sequence:
                raise CoworkerError(
                    "conversation_revision_conflict", "The conversation changed. Review the latest message.", 409,
                )
            if len(message.text) > 4000 or len(message.text) < 3:
                raise CoworkerError("conversation_goal_invalid", "Use a task brief of 3 to 4000 characters.", 422)
            request = AgentRunCreate(goal=message.text, output_language=output_language)
            decision = qualify_agent_goal(request.goal, self.settings, has_attached_actions=False)
            if decision.execution != "agent_run" or decision.consequential or not decision.capability_available:
                raise CoworkerError(
                    "conversation_route_unavailable",
                    "This request needs another explicit workflow; chat does not approve external actions.",
                    409,
                )
            pins = require_current_selected_sources(db, owner, message.selected_sources or [])
            if any(pin["resource_type"] != "document_version" for pin in pins):
                raise CoworkerError(
                    "conversation_source_unsupported",
                    "This Agent run supports selected documents only. Remove other attachments.", 409,
                )
            if len(pins) > 5:
                raise CoworkerError("conversation_source_limit", "Select at most five documents.", 409)
            if db.scalar(select(func.count()).select_from(AgentRun).where(
                AgentRun.owner_id == owner, AgentRun.state.in_(ACTIVE_RUN_STATES),
            )) >= self.settings.max_active_agent_runs:
                raise CoworkerError("active_agent_limit", "The active Agent run limit has been reached.", 429)
            workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
            if workspace_id is None:
                raise not_found()
            # AgentRepository.create uses the same owner lock and run/outbox contracts.
            # This method does not open a second transaction or invoke that method.
            run_id = str(uuid4())
            payload = request.model_dump(mode="json")
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            now = utcnow()
            run = AgentRun(
                id=run_id, owner_id=owner, workspace_id=workspace_id,
                idempotency_key="conversation:" + message.id, fingerprint=fingerprint,
                goal=request.goal, output_language=request.output_language,
                input_versions=[pin["resource_id"] for pin in pins],
                action_ids=[], memory_namespaces=[], connector_read_grant_ids=[],
                connector_snapshot_ids=[], tool_allowlist=[],
                runtime_version=(3 if self.settings.agent_runtime_v3_enabled else 2 if (
                    self.settings.agent_dependency_graph_enabled and
                    self.settings.agent_parallel_execution_enabled
                ) else 1),
                state="queued", phase="planning",
                message="Conversation work accepted; awaiting the bounded Agent runtime.",
                deadline_at=now + timedelta(seconds=self.settings.agent_run_timeout_seconds),
            )
            db.add(run)
            db.flush()
            db.add(AgentStep(id=str(uuid4()), run_id=run.id, owner_id=owner,
                             ordinal=0, tool_name=None, state="queued",
                             input={"kind": "goal", "output_language": request.output_language}, output={}))
            db.add(AgentOutbox(run_id=run.id))
            self.agent._checkpoint(db, run, "run_created", evidence={
                "runtime_version": run.runtime_version, "deadline_at": iso(run.deadline_at),
                "source": "conversation_message",
            })
            self.agent._event(db, run, "queued", "planning", "Conversation work accepted.")
            self.agent._audit(db, owner, run.id, "conversation_run_created")
            message.resource_links = [*links, {"resource_type": "agent_run", "resource_id": run.id}]
            db.flush()
            return {"run_id": run.id, "state": run.state, "message_id": message.id,
                    "conversation_id": conversation.id, "replayed": False}, True

    def activity(self, owner: str, conversation_id: str, *, limit: int = 50) -> dict:
        """Read-only projection over existing message and Agent event ledgers."""
        if not self.settings.conversations_enabled:
            raise CoworkerError("conversations_unavailable", "Conversations are not enabled.", 409)
        if not 1 <= limit <= 100:
            raise CoworkerError("invalid_cursor", "Invalid activity limit.", 422)
        with self.sessions() as db:
            row = db.scalar(select(Conversation).where(
                Conversation.id == conversation_id, Conversation.owner_id == owner,
                Conversation.deleted.is_(False),
            ))
            if row is None:
                raise not_found()
            messages = list(db.scalars(select(ConversationMessage).where(
                ConversationMessage.conversation_id == row.id,
                ConversationMessage.owner_id == owner,
            ).order_by(ConversationMessage.sequence.desc()).limit(limit)))
            messages.reverse()
            ids = [link["resource_id"] for msg in messages for link in (msg.resource_links or [])
                   if link.get("resource_type") == "agent_run"]
            runs = {run.id: run for run in db.scalars(select(AgentRun).where(
                AgentRun.owner_id == owner, AgentRun.id.in_(ids),
            ))} if ids else {}
            latest = {}
            if ids:
                events = db.scalars(select(AgentEvent).where(
                    AgentEvent.owner_id == owner, AgentEvent.run_id.in_(ids),
                ).order_by(AgentEvent.run_id, AgentEvent.sequence.desc())).all()
                for event in events:
                    latest.setdefault(event.run_id, event)
            items = []
            for msg in messages:
                for link in (msg.resource_links or []):
                    if link.get("resource_type") != "agent_run":
                        continue
                    run = runs.get(link.get("resource_id"))
                    if run is None:
                        continue
                    event = latest.get(run.id)
                    items.append({"message_id": msg.id, "sequence": msg.sequence,
                                  "run_id": run.id, "state": run.state, "phase": run.phase,
                                  "cancel_requested": run.cancel_requested,
                                  "event_sequence": run.event_sequence,
                                  "updated_at": iso(run.updated_at),
                                  "detail": event.message if event is not None else run.message})
            return {"items": items, "message_sequence": row.message_sequence}
