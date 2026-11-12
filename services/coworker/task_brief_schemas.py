"""Explicit, versioned memory selection for reviewed conversation task briefs.

An omitted selection preserves pre-brief namespace retrieval. An explicit empty
selection opts into brief semantics and supplies no memories.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryPin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: UUID
    expected_version: int = Field(ge=1)


class TaskBriefMemorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_pins: list[MemoryPin] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_memory_ids(self):
        ids = [pin.fact_id for pin in self.memory_pins]
        if len(ids) != len(set(ids)):
            raise ValueError("Select each memory fact only once")
        return self
