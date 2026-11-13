"""Bounded task proposal and owner-scoped validation of reviewed conversation work."""
from __future__ import annotations
import re
from uuid import uuid4
from sqlalchemy import select
from .agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from .conversation_context import require_current_selected_sources
from .errors import CoworkerError
from .models import Conversation, ConversationMessage, Project, ProjectResource
from .provider_capacity import acquire_provider_lease, settle_provider_lease
from .repository import not_found
from .task_brief_schemas import TaskBrief, canonical_brief_digest

_SECOND = re.compile(r"\b(?:second|2nd)\s+(?:option|structure|one)\b", re.I)
_OPTION_TWO = re.compile(r"(?:\b(?:option|structure)\s*(?:2|two|second)\b|(?:^|\n)\s*2[.)])", re.I)
_TWO_PAGE = re.compile(r"\b(?:two[- ]page|2[- ]page|two pages|2 pages)\b", re.I)
_BRITISH = re.compile(r"\b(?:british english|uk english)\b", re.I)

class ConversationTaskBriefService:
    def __init__(self, sessions, settings, planner=None):
        self.sessions, self.settings = sessions, settings
        self.model = planner if planner is not None else DeepSeekAgentPlanner(settings)

    @staticmethod
    def _checked(db, owner, conversation_id, message_id, expected_sequence):
        conversation = db.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.owner_id == owner,
            Conversation.deleted.is_(False)))
        message = db.scalar(select(ConversationMessage).where(
            ConversationMessage.id == message_id,
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.owner_id == owner))
        if conversation is None or message is None:
            raise not_found()
        if conversation.message_sequence != expected_sequence or message.sequence != expected_sequence:
            raise CoworkerError("conversation_revision_conflict",
                                "Conversation changed; review its latest messages.", 409)
        return message

    @staticmethod
    def _history(db, owner, conversation_id, sequence):
        rows = list(db.scalars(select(ConversationMessage).where(
            ConversationMessage.owner_id == owner,
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.sequence <= sequence).order_by(ConversationMessage.sequence)))
        known = {}
        for row in rows:
            for pin in row.selected_sources or []:
                if isinstance(pin, dict) and isinstance(pin.get("resource_id"), str):
                    known[pin["resource_id"]] = pin
        history = [{"sequence": row.sequence, "text": row.text[:1800],
                    "source_ids": [pin["resource_id"] for pin in (row.selected_sources or [])
                                   if isinstance(pin, dict) and "resource_id" in pin]} for row in rows[-12:]]
        while sum(len(item["text"]) for item in history) > 18000:
            history.pop(0)
        return history, known

    @staticmethod
    def _project(db, settings, owner, conversation_id, project_id):
        if project_id is None:
            return {}
        if not settings.projects_enabled:
            raise CoworkerError("projects_unavailable", "Project context unavailable.", 409)
        project = db.scalar(select(Project).where(
            Project.id == project_id, Project.owner_id == owner, Project.deleted.is_(False)))
        link = db.scalar(select(ProjectResource.project_id).where(
            ProjectResource.project_id == project_id, ProjectResource.owner_id == owner,
            ProjectResource.resource_type == "conversation", ProjectResource.resource_id == conversation_id))
        if project is None or link is None:
            raise not_found()
        return {"project_id": project.id, "name": project.name,
                "revision": project.revision, "instructions": project.description or ""}

    @classmethod
    def validate_in_session(cls, db, settings, owner, conversation_id, message_id,
                            expected_sequence, brief: TaskBrief, project_id=None):
        if not settings.conversations_enabled:
            raise CoworkerError("conversations_unavailable", "Conversations not enabled.", 409)
        cls._checked(db, owner, conversation_id, message_id, expected_sequence)
        _, known = cls._history(db, owner, conversation_id, expected_sequence)
        source_ids = [str(value) for value in brief.source_ids]
        if any(identifier not in known for identifier in source_ids):
            raise CoworkerError("task_brief_source_invalid",
                                "Source was not selected in this conversation.", 409)
        pins = require_current_selected_sources(db, owner, [known[s] for s in source_ids])
        project = cls._project(db, settings, owner, conversation_id, project_id)
        digest = canonical_brief_digest(brief, pins, project, owner_id=owner,
                  conversation_id=conversation_id, message_id=message_id, sequence=expected_sequence)
        return {"brief": brief.model_dump(mode="json"), "selected_sources": pins,
                "project_context": project, "canonical_digest": digest}

    def validate(self, owner, conversation_id, message_id, *, expected_sequence, brief, project_id=None):
        with self.sessions() as db:
            result = self.validate_in_session(db, self.settings, owner, conversation_id,
                     message_id, expected_sequence, brief, project_id)
        return {"state": "ready", **result}

    async def propose(self, owner, conversation_id, message_id, *, expected_sequence, project_id=None):
        if not self.settings.conversations_enabled or not self.settings.agent_runtime_enabled:
            raise CoworkerError("conversation_dispatch_unavailable", "Task preview is disabled.", 409)
        with self.sessions() as db:
            self._checked(db, owner, conversation_id, message_id, expected_sequence)
            history, known = self._history(db, owner, conversation_id, expected_sequence)
            self._project(db, self.settings, owner, conversation_id, project_id)
        if history and _SECOND.search(history[-1]["text"]):
            if not _OPTION_TWO.search("\n".join(item["text"] for item in history[:-1])):
                return {"state": "needs_input", "question": "Which second option or structure do you mean?",
                        "brief": None, "canonical_digest": None}
        lease_id = str(uuid4())
        reserved = min(self.settings.agent_planner_max_output_tokens + 3000,
                       self.settings.provider_max_reserved_tokens_per_workspace)
        with self.sessions.begin() as db:
            acquire_provider_lease(db, self.settings, owner_id=owner, kind="planner",
                                   resource_id=lease_id, sequence=1, reserved_tokens=reserved)
        tokens = None
        try:
            proposal, tokens = await self.model.propose_task_brief(history, list(known))
        except PlannerFailure as error:
            tokens = error.total_tokens
            raise
        finally:
            with self.sessions.begin() as db:
                settle_provider_lease(db, kind="planner", resource_id=lease_id,
                                      sequence=1, actual_tokens=tokens)
        if proposal.state == "needs_input":
            return {"state": "needs_input", "question": proposal.question,
                    "brief": None, "canonical_digest": None}
        brief = proposal.brief
        prior = "\n".join(item["text"] for item in history[:-1])
        latest = history[-1]["text"] if history else ""
        constraints = list(brief.constraints)
        if (_TWO_PAGE.search(prior) and not re.search(r"\b(?:one|1|three|3)\s+pages?\b", latest, re.I)
                and not any(_TWO_PAGE.search(item) for item in constraints)):
            constraints.append("Maximum two pages")
        if (_BRITISH.search(prior) and not re.search(r"\b(?:american|us)\s+english\b", latest, re.I)
                and not any(_BRITISH.search(item) for item in constraints)):
            constraints.append("Use British English")
        if constraints != brief.constraints:
            brief = brief.model_copy(update={"constraints": constraints})
        brief = TaskBrief.model_validate(brief.model_dump(mode="json"))
        return {**self.validate(owner, conversation_id, message_id,
                 expected_sequence=expected_sequence, brief=brief, project_id=project_id), "question": None}
