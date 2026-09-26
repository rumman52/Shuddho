from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .action_schemas import CalendarCreate, EmailSend, LinkedInSocialPublish
from .memory_schemas import Namespace


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _safe_text(value: str) -> str:
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise ValueError("Text contains unsupported control characters")
    return value


class AgentRunCreate(AgentModel):
    goal: str = Field(min_length=3, max_length=4000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=5)
    action_ids: list[UUID] = Field(default_factory=list, max_length=3)
    memory_namespaces: list[Namespace] = Field(default_factory=list, max_length=5)
    output_language: str = Field(default="en", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)

    @field_validator("goal")
    @classmethod
    def safe_goal(cls, value: str) -> str:
        return _safe_text(value)

    @model_validator(mode="after")
    def unique_documents(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("A document may be included only once")
        if len(set(self.action_ids)) != len(self.action_ids):
            raise ValueError("An action may be included only once")
        if len(set(self.memory_namespaces)) != len(self.memory_namespaces):
            raise ValueError("A memory namespace may be included only once")
        return self


class TaskToolInput(AgentModel):
    instruction: str = Field(min_length=3, max_length=2000)
    notes: str = Field(default="", max_length=20000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=5)
    output_language: str = Field(default="en", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)

    @field_validator("instruction", "notes")
    @classmethod
    def safe_content(cls, value: str) -> str:
        return _safe_text(value)

    @model_validator(mode="after")
    def unique_documents(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("A document may be included only once")
        return self


class ResearchToolInput(TaskToolInput):
    query: str = Field(min_length=3, max_length=400)
    time_range: Literal["any", "day", "week", "month", "year"] = "any"

    @field_validator("query")
    @classmethod
    def safe_query(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("Use a single-line search query")
        return _safe_text(value)


class ApprovedActionToolInput(AgentModel):
    action_id: UUID


class AgentPlanStep(AgentModel):
    tool: str = Field(min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_.-]+$")
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded_arguments(self):
        try:
            encoded = json.dumps(self.arguments, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            raise ValueError("Tool arguments must be JSON serializable") from error
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("Tool arguments exceed the 32 KiB limit")
        return self


def action_proposal_hash(run_id: str, payload: dict, rationale: str) -> str:
    value = {
        "version": 1,
        "run_id": run_id,
        "payload": payload,
        "rationale": rationale,
    }
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


AgentProposalPayload = Annotated[
    EmailSend | CalendarCreate | LinkedInSocialPublish,
    Field(discriminator="kind"),
]


class AgentActionProposal(AgentModel):
    payload: AgentProposalPayload
    rationale: str = Field(min_length=3, max_length=300)

    @field_validator("rationale")
    @classmethod
    def safe_rationale(cls, value: str) -> str:
        return _safe_text(value)


class AgentPlannerChoice(AgentModel):
    tool: str = Field(min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_.-]+$")
    objective: str = Field(min_length=3, max_length=500)

    @field_validator("objective")
    @classmethod
    def safe_objective(cls, value: str) -> str:
        return _safe_text(value)


class AgentPlannerProposal(AgentModel):
    steps: list[AgentPlannerChoice] = Field(min_length=1, max_length=3)
    action_proposals: list[AgentActionProposal] = Field(default_factory=list, max_length=2)


class AgentObservation(AgentModel):
    ordinal: int = Field(ge=1, le=8)
    tool: str = Field(min_length=3, max_length=80)
    status: Literal["completed", "needs_input", "provider_confirmed"]
    resource_type: str | None = Field(default=None, max_length=40)
    summary: dict[str, Any] = Field(default_factory=dict)


class AgentV3Decision(AgentModel):
    decision: Literal["next_step", "needs_input", "awaiting_approval", "wait", "blocked", "complete"]
    tool: str | None = Field(default=None, min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_.-]+$")
    objective: str | None = Field(default=None, min_length=3, max_length=500)
    message: str | None = Field(default=None, min_length=1, max_length=300)
    wait_seconds: int | None = Field(default=None, ge=1, le=60)

    @field_validator("objective", "message")
    @classmethod
    def safe_text(cls, value: str | None) -> str | None:
        return _safe_text(value) if value is not None else None

    @model_validator(mode="after")
    def valid_decision(self):
        if self.decision == "next_step":
            if self.tool is None or self.objective is None:
                raise ValueError("next_step requires tool and objective")
            if self.message is not None or self.wait_seconds is not None:
                raise ValueError("next_step accepts only tool and objective")
        elif self.decision == "wait":
            if self.wait_seconds is None:
                raise ValueError("wait requires wait_seconds")
            if self.tool is not None or self.objective is not None:
                raise ValueError("wait cannot select a tool")
        else:
            if self.tool is not None or self.objective is not None or self.wait_seconds is not None:
                raise ValueError("Non-step decisions cannot select a tool or wait duration")
            if self.decision in {"needs_input", "blocked", "awaiting_approval"} and self.message is None:
                raise ValueError(f"{self.decision} requires a message")
        return self


class ActionProposalPromotion(AgentModel):
    connection_id: UUID
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActionProposalReview(AgentModel):
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


