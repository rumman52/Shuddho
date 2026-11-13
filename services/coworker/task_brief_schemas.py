"""Reviewed conversation work: bounded, inert task brief and canonical digest."""
from __future__ import annotations
import hashlib
import json
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .goal_schemas import _safe_text

class TaskBrief(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    objective: str = Field(min_length=3, max_length=4000)
    constraints: list[str] = Field(default_factory=list, max_length=12)
    deliverables: list[str] = Field(min_length=1, max_length=8)
    source_ids: list[UUID] = Field(default_factory=list, max_length=5)
    output_language: str = Field(default="auto", max_length=35, pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$")

    @field_validator("objective")
    @classmethod
    def safe_objective(cls, value):
        return _safe_text(value)

    @field_validator("constraints", "deliverables")
    @classmethod
    def valid_items(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicated brief items are not permitted")
        for item in value:
            if not isinstance(item, str) or not 1 <= len(item.strip()) <= 500 or item != item.strip():
                raise ValueError("Brief items must be trimmed strings of 1-500 characters")
            _safe_text(item)
        return value

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicated source selection")
        return value

class TaskBriefSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["ready", "needs_input"]
    brief: TaskBrief | None = None
    question: str | None = Field(default=None, min_length=3, max_length=300)

    @model_validator(mode="after")
    def consistent(self):
        if self.state == "ready" and (self.brief is None or self.question is not None):
            raise ValueError("Ready suggestion requires a brief")
        if self.state == "needs_input" and (self.brief is not None or self.question is None):
            raise ValueError("Ambiguous suggestion requires a question")
        return self

class TaskBriefProposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=1)
    project_id: UUID | None = None

class TaskBriefPreviewRequest(TaskBriefProposeRequest):
    brief: TaskBrief

def canonical_brief_digest(brief: TaskBrief, pins: list[dict], project: dict, *,
                           owner_id: str, conversation_id: str, message_id: str, sequence: int) -> str:
    bounded_pins = [{"resource_type": p["resource_type"], "resource_id": p["resource_id"],
                     "sha256": p["sha256"], "document_id": p.get("document_id"),
                     "version": p.get("version")} for p in pins]
    data = {"schema_version": 1, "brief": brief.model_dump(mode="json"), "source_pins": bounded_pins,
            "project_context": project or {}, "owner": owner_id, "conversation": conversation_id,
            "message": message_id, "sequence": sequence}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
