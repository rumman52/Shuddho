"""CW-06/07: atomic, bounded conversation admission into the existing Agent ledger.

No user text grants ExternalAction authority. PostgreSQL serializes each owner's
admissions with the same Account lock used by the other ledgers.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import timedelta
from pathlib import PurePath
from uuid import uuid4

from sqlalchemy import func, select

from .agent_repository import ACTIVE_RUN_STATES
from .agent_router import qualify_agent_goal
from .agent_schemas import AgentRunCreate
from .conversation_context import require_current_selected_sources
from .conversation_task_briefs import ConversationTaskBriefService
from .errors import CoworkerError
from .memory_repository import require_current_memory_pins
from .task_brief_schemas import MemoryPin, TaskBriefMemorySelection, TaskBrief
from .models import (
    Account, AgentEvent, AgentOutbox, AgentRun, AgentStep, Conversation,
    ConversationMessage, Project, ProjectResource, Workspace, utcnow,
)
from .repository import iso, not_found


_SQLITE_DISPATCH_LOCK = threading.Lock()


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

    @staticmethod
    def _dispatch_fingerprint(request: AgentRunCreate, selected_sources: list[dict], project_context: dict, reviewed_digest: str | None = None) -> str:
        sources = [{
            "resource_type": item.get("resource_type"),
            "resource_id": item.get("resource_id"),
            "document_id": item.get("document_id"),
            "version": item.get("version"),
            "sha256": item.get("sha256"),
        } for item in selected_sources]
        payload = {
            "request": request.model_dump(mode="json"),
            "selected_sources": sources,
            "project_context": project_context or {},
        }
        if reviewed_digest is not None:
            payload["reviewed_digest"] = reviewed_digest
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _project_snapshot(self, db, owner: str, conversation_id: str, project_id: str | None) -> dict:
        if project_id is None:
            return {}
        if not self.settings.projects_enabled:
            raise CoworkerError("projects_unavailable", "Project context is not available in this workspace.", 409)
        project = db.scalar(select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner,
            Project.deleted.is_(False),
        ).with_for_update())
        linked = db.scalar(select(ProjectResource.project_id).where(
            ProjectResource.project_id == project_id,
            ProjectResource.owner_id == owner,
            ProjectResource.resource_type == "conversation",
            ProjectResource.resource_id == conversation_id,
        ))
        if project is None or linked is None:
            raise not_found()
        return {
            "project_id": project.id,
            "name": project.name,
            "revision": project.revision,
            "instructions": project.description or "",
        }

    def dispatch(self, owner: str, conversation_id: str, message_id: str, *, expected_sequence: int,
                 output_language: str = "auto", project_id: str | None = None,
                 reviewed_brief: TaskBrief | None = None,
                 expected_digest: str | None = None,
                 memory_pins: list[MemoryPin] | None = None) -> tuple[dict, bool]:
        """Emulate the Postgres owner-row lock for SQLite integration tests."""
        kwargs = dict(expected_sequence=expected_sequence, output_language=output_language,
                      project_id=project_id, reviewed_brief=reviewed_brief, expected_digest=expected_digest,
                      memory_pins=memory_pins)
        bind = self.sessions.kw.get("bind")
        if bind is not None and bind.dialect.name == "sqlite":
            with _SQLITE_DISPATCH_LOCK:
                return self._dispatch_once(owner, conversation_id, message_id, **kwargs)
        return self._dispatch_once(owner, conversation_id, message_id, **kwargs)

    def _dispatch_once(self, owner: str, conversation_id: str, message_id: str, *, expected_sequence: int,
                 output_language: str = "auto", project_id: str | None = None,
                 reviewed_brief: TaskBrief | None = None,
                 expected_digest: str | None = None,
                 memory_pins: list[MemoryPin] | None = None) -> tuple[dict, bool]:
        """Commit message link, run, initial event/checkpoint and outbox together."""
        self._enabled()
        selection = None if memory_pins is None else TaskBriefMemorySelection(
            memory_pins=memory_pins,
        ).model_dump(mode="json")["memory_pins"]
        if selection is not None and len(selection) > self.settings.max_memory_context_facts:
            raise CoworkerError("memory_selection_limit", "Too many selected memories for this task.", 409)
        if expected_sequence < 1:
            raise CoworkerError("conversation_revision_conflict", "Reload the latest messages.", 409)
        if (reviewed_brief is None) != (expected_digest is None):
            raise CoworkerError("task_brief_digest_required", "Review the task brief before admission.", 422)
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
                reviewed_snapshot = dict(run.reviewed_brief or {})
                if bool(reviewed_snapshot) != bool(reviewed_brief):
                    raise CoworkerError("idempotency_conflict",
                                        "This message was already started with different run options.", 409)
                if reviewed_brief is not None:
                    if output_language not in {"auto", reviewed_brief.output_language}:
                        raise CoworkerError("idempotency_conflict", "Output language changed.", 409)
                    preview = ConversationTaskBriefService.validate_in_session(
                        db, self.settings, owner, conversation_id, message_id,
                        expected_sequence, reviewed_brief, project_id)
                    if (preview["canonical_digest"] != expected_digest
                            or reviewed_snapshot.get("canonical_digest") != expected_digest):
                        raise CoworkerError("idempotency_conflict", "Reviewed brief or sources changed.", 409)
                    replay_request = AgentRunCreate(
                        goal=reviewed_brief.objective, output_language=reviewed_brief.output_language)
                else:
                    replay_request = AgentRunCreate(goal=message.text, output_language=output_language)
                saved_project_context = dict(run.project_context or {})
                if (("memory_pins" in saved_project_context) != (selection is not None)
                    or (selection is not None and saved_project_context["memory_pins"] != selection)):
                    raise CoworkerError(
                        "idempotency_conflict", "This task was dispatched with a different memory selection.", 409,
                    )
                requested_project_id = saved_project_context.get("project_id")
                if (str(project_id) if project_id is not None else None) != requested_project_id:
                    raise CoworkerError(
                        "idempotency_conflict", "This message was dispatched with different project context.", 409,
                    )
                fingerprint = self._dispatch_fingerprint(
                    replay_request,
                    preview["selected_sources"] if reviewed_brief is not None else message.selected_sources or [],
                    saved_project_context, reviewed_digest=expected_digest,
                )
                legacy_fingerprint = hashlib.sha256(json.dumps(
                    replay_request.model_dump(mode="json"), sort_keys=True,
                ).encode()).hexdigest()
                if run.fingerprint != fingerprint and not (
                    reviewed_brief is None and run.fingerprint == legacy_fingerprint
                    and not saved_project_context
                    and not list(getattr(run, "input_artifacts", []) or [])
                ):
                    raise CoworkerError(
                        "idempotency_conflict", "This message was dispatched with different options.", 409,
                    )
                return {"run_id": run.id, "state": run.state, "message_id": message.id,
                        "conversation_id": conversation.id, "replayed": True}, False
            if conversation.message_sequence != expected_sequence or message.sequence != expected_sequence:
                raise CoworkerError(
                    "conversation_revision_conflict", "The conversation changed. Review the latest message.", 409,
                )
            if reviewed_brief is not None:
                preview = ConversationTaskBriefService.validate_in_session(
                    db, self.settings, owner, conversation_id, message_id,
                    expected_sequence, reviewed_brief, project_id)
                if preview["canonical_digest"] != expected_digest:
                    raise CoworkerError("task_brief_digest_mismatch", "Brief changed. Preview it again.", 409)
                if output_language not in {"auto", reviewed_brief.output_language}:
                    raise CoworkerError("task_brief_language_mismatch", "Output language mismatch.", 409)
                goal = reviewed_brief.objective
                selected_source_pins = preview["selected_sources"]
            else:
                goal = message.text
                selected_source_pins = message.selected_sources or []
            if len(goal) > 4000 or len(goal) < 3:
                raise CoworkerError("conversation_goal_invalid", "Use a task brief of 3 to 4000 characters.", 422)
            request = AgentRunCreate(
                goal=goal,
                output_language=reviewed_brief.output_language if reviewed_brief is not None else output_language,
            )
            decision = qualify_agent_goal(request.goal, self.settings, has_attached_actions=False)
            if decision.execution != "agent_run" or decision.consequential or not decision.capability_available:
                raise CoworkerError(
                    "conversation_route_unavailable",
                    "This request needs another explicit workflow; chat does not approve external actions.",
                    409,
                )
            pins = require_current_selected_sources(db, owner, selected_source_pins)
            if len(pins) > 5:
                raise CoworkerError("conversation_source_limit", "Select at most five sources.", 409)
            document_pins = [pin for pin in pins if pin["resource_type"] == "document_version"]
            artifact_pins = [pin for pin in pins if pin["resource_type"] == "artifact"]
            runtime_version = (3 if self.settings.agent_runtime_v3_enabled else 2 if (
                self.settings.agent_dependency_graph_enabled and
                self.settings.agent_parallel_execution_enabled
            ) else 1)
            if artifact_pins:
                if runtime_version != 3 or not self.settings.context_retrieval_enabled:
                    raise CoworkerError(
                        "conversation_artifact_context_unavailable",
                        "Generated artifacts require Agent Runtime v3 with context retrieval enabled.",
                        409,
                    )
                supported_extensions = {"txt", "docx", "pdf", "csv", "xlsx", "pptx"}
                for pin in artifact_pins:
                    extension = PurePath(str(pin.get("filename") or "")).suffix.lower().lstrip(".")
                    if extension not in supported_extensions:
                        raise CoworkerError(
                            "context_source_unsupported",
                            "This generated artifact format cannot be safely extracted as Agent context.",
                            409,
                        )
                    if int(pin.get("byte_size", 0)) < 1 or int(pin["byte_size"]) > self.settings.max_upload_bytes:
                        raise CoworkerError(
                            "context_source_too_large",
                            "A selected generated artifact exceeds the supported context size.",
                            409,
                        )
            project_context = self._project_snapshot(db, owner, conversation_id, project_id)
            if reviewed_brief is not None and project_context != preview["project_context"]:
                raise CoworkerError("task_brief_digest_mismatch", "Project context changed.", 409)
            if db.scalar(select(func.count()).select_from(AgentRun).where(
                AgentRun.owner_id == owner, AgentRun.state.in_(ACTIVE_RUN_STATES),
            )) >= self.settings.max_active_agent_runs:
                raise CoworkerError("active_agent_limit", "The active Agent run limit has been reached.", 429)
            workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
            if workspace_id is None:
                raise not_found()
            if selection is not None:
                require_current_memory_pins(db, owner, workspace_id, selection, self.settings)
                project_context["memory_pins"] = selection
            # AgentRepository.create uses the same owner lock and run/outbox contracts.
            # This method does not open a second transaction or invoke that method.
            run_id = str(uuid4())
            fingerprint = self._dispatch_fingerprint(request, pins, project_context, reviewed_digest=expected_digest)
            now = utcnow()
            run = AgentRun(
                id=run_id, owner_id=owner, workspace_id=workspace_id,
                idempotency_key="conversation:" + message.id, fingerprint=fingerprint,
                goal=request.goal, output_language=request.output_language,
                input_versions=[pin["resource_id"] for pin in document_pins],
                input_artifacts=[pin["resource_id"] for pin in artifact_pins],
                project_context=project_context,
                reviewed_brief=({
                    "schema_version": 1, "brief": reviewed_brief.model_dump(mode="json"),
                    "source_pins": pins, "canonical_digest": expected_digest,
                    "message_sequence": expected_sequence,
                } if reviewed_brief is not None else {}),
                steering_revision=0, steering_instructions=[],
                action_ids=[], memory_namespaces=[], connector_read_grant_ids=[],
                connector_snapshot_ids=[], tool_allowlist=[],
                runtime_version=runtime_version,
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

    def cancel(self, owner: str, conversation_id: str, message_id: str, *,
               expected_sequence: int, expected_event_sequence: int) -> dict:
        """Revision-check and cancel the linked run in the SAME DB transaction.

        This reuses the established Agent cancellation path (child task/action
        invalidation included) and cannot silently create a replacement run.
        """
        self._enabled()
        with self.sessions.begin() as db:
            self._lock_account(db, owner)
            conversation = self._conversation(db, owner, conversation_id)
            message = self._message(db, owner, conversation_id, message_id)
            if conversation.message_sequence != expected_sequence:
                raise CoworkerError(
                    "conversation_revision_conflict", "The conversation changed. Reload before steering.", 409,
                )
            links = [link for link in (message.resource_links or [])
                     if link.get("resource_type") == "agent_run"]
            if len(links) != 1:
                raise CoworkerError("conversation_run_missing", "This message has no linked Agent run.", 409)
            run = db.scalar(select(AgentRun).where(
                AgentRun.id == links[0].get("resource_id"), AgentRun.owner_id == owner,
            ).with_for_update())
            if run is None:
                raise not_found()
            if run.cancel_requested and run.state == "cancelled":
                return {"run_id": run.id, "state": run.state, "event_sequence": run.event_sequence}
            if run.event_sequence != expected_event_sequence:
                raise CoworkerError(
                    "agent_revision_conflict", "Agent progress changed. Refresh activity before cancelling.", 409,
                )
            self.agent.cancel_in_session(db, owner, run.id)
            return {"run_id": run.id, "state": run.state, "event_sequence": run.event_sequence}

    def steer(self, owner: str, conversation_id: str, message_id: str, *,
              expected_sequence: int, expected_steering_revision: int, instruction: str) -> dict:
        """Append one revision-bound instruction to one active Runtime v3 run."""
        self._enabled()
        instruction = instruction.strip() if isinstance(instruction, str) else ""
        if not instruction or len(instruction) > 4000:
            raise CoworkerError("agent_steering_invalid", "Use an instruction of 1 to 4000 characters.", 422)
        with self.sessions.begin() as db:
            self._lock_account(db, owner)
            conversation = self._conversation(db, owner, conversation_id)
            message = self._message(db, owner, conversation_id, message_id)
            if conversation.message_sequence != expected_sequence:
                raise CoworkerError(
                    "conversation_revision_conflict", "The conversation changed. Reload before steering.", 409,
                )
            links = [link for link in (message.resource_links or [])
                     if isinstance(link, dict) and link.get("resource_type") == "agent_run"]
            if len(links) != 1:
                raise CoworkerError("conversation_run_missing", "This message has no linked Agent run.", 409)
            run = db.scalar(select(AgentRun).where(
                AgentRun.id == links[0].get("resource_id"),
                AgentRun.owner_id == owner,
            ).with_for_update())
            if run is None:
                raise not_found()
            if run.runtime_version != 3:
                raise CoworkerError(
                    "agent_steering_unavailable",
                    "Live steering is supported by Agent Runtime v3 runs only.",
                    409,
                )
            if run.state not in {"queued", "planning", "running"} or run.cancel_requested:
                raise CoworkerError(
                    "agent_run_closed",
                    "This Agent run cannot accept new instructions in its current state.",
                    409,
                )
            if run.steering_revision != expected_steering_revision:
                raise CoworkerError(
                    "agent_steering_revision_conflict",
                    "Agent instructions changed. Refresh the task before steering again.",
                    409,
                )
            history = list(run.steering_instructions or [])
            if len(history) >= 20 or sum(
                len(str(item.get("instruction", "")).encode("utf-8")) for item in history
            ) + len(instruction.encode("utf-8")) > 12000:
                raise CoworkerError(
                    "agent_steering_limit",
                    "This task has reached its bounded instruction history limit.",
                    429,
                )
            revision = run.steering_revision + 1
            history.append({
                "revision": revision,
                "instruction": instruction,
                "created_at": iso(utcnow()),
            })
            run.steering_instructions = history
            run.steering_revision = revision
            self.agent._event(
                db, run, run.state, run.phase,
                "A new user instruction is queued for the next planning checkpoint.",
            )
            self.agent._audit(db, owner, run.id, "agent_run_steered")
            return {
                "run_id": run.id,
                "state": run.state,
                "steering_revision": run.steering_revision,
                "event_sequence": run.event_sequence,
            }

    @staticmethod
    def _activity_cursor(owner: str, conversation_id: str, sequence: int) -> str:
        """Opaque-ish, scope-bound checkpoint, not a permission token or grant."""
        scope = hashlib.sha256(f"{owner}:{conversation_id}".encode("utf-8")).hexdigest()[:24]
        return f"v1:{scope}:{sequence}"

    @classmethod
    def _activity_sequence(cls, owner: str, conversation_id: str, after: str, maximum: int) -> int:
        """Validate a cursor against the already authorized conversation owner."""
        if after == "start":
            return 0
        pieces = after.split(":")
        if (
            len(after) > 64 or len(pieces) != 3 or pieces[0] != "v1"
            or not pieces[2].isascii() or not pieces[2].isdecimal()
            or pieces[2].startswith("0") and pieces[2] != "0"
        ):
            raise CoworkerError("invalid_cursor", "Invalid conversation activity cursor.", 422)
        sequence = int(pieces[2])
        if (
            pieces[1] != cls._activity_cursor(owner, conversation_id, sequence).split(":")[1]
            or sequence > maximum
        ):
            raise CoworkerError("invalid_cursor", "Activity cursor is outside this conversation.", 422)
        return sequence

    def activity(self, owner: str, conversation_id: str, *, after: str | None = None,
                 limit: int = 50) -> dict:
        """Read-only, owner-bound resumable projection over existing Agent records.

        No `after` retains legacy latest-N polling (so run progress can change
        without a new message). `after=start` then `next_cursor` walks owned
        messages forward; its checkpoint advances over messages without Agent work.
        The cursor is a read position, never an authority or dispatch identity.
        """
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

            if after is None:
                # Preserve the previous polling contract for live changes on
                # existing Agent runs even when no message has been appended.
                messages = list(db.scalars(select(ConversationMessage).where(
                    ConversationMessage.conversation_id == row.id,
                    ConversationMessage.owner_id == owner,
                ).order_by(ConversationMessage.sequence.desc()).limit(limit)))
                messages.reverse()
                more = False
                last_sequence = messages[-1].sequence if messages else row.message_sequence
            else:
                sequence = self._activity_sequence(owner, conversation_id, after, row.message_sequence)
                page = list(db.scalars(select(ConversationMessage).where(
                    ConversationMessage.conversation_id == row.id,
                    ConversationMessage.owner_id == owner,
                    ConversationMessage.sequence > sequence,
                ).order_by(ConversationMessage.sequence).limit(limit + 1)))
                more = len(page) > limit
                messages = page[:limit]
                last_sequence = messages[-1].sequence if messages else sequence

            ids = [link["resource_id"] for msg in messages for link in (msg.resource_links or [])
                   if isinstance(link, dict) and link.get("resource_type") == "agent_run"
                   and isinstance(link.get("resource_id"), str)]
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
                    if not isinstance(link, dict) or link.get("resource_type") != "agent_run":
                        continue
                    run = runs.get(link.get("resource_id"))
                    if run is None:
                        continue
                    event = latest.get(run.id)
                    items.append({"message_id": msg.id, "sequence": msg.sequence,
                                  "run_id": run.id, "state": run.state, "phase": run.phase,
                                  "cancel_requested": run.cancel_requested,
                                  "event_sequence": run.event_sequence,
                                  "steering_revision": run.steering_revision,
                                  "runtime_version": run.runtime_version,
                                  "updated_at": iso(run.updated_at),
                                  "detail": event.message if event is not None else run.message})
            return {
                "items": items,
                "message_sequence": row.message_sequence,
                "next_cursor": self._activity_cursor(owner, conversation_id, last_sequence),
                "has_more": more,
            }
