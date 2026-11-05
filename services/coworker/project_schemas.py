"""Project organization is separate from context and execution permission."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .goal_schemas import _safe_text

class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    @field_validator("name", "description")
    @classmethod
    def safe_text(cls, value): return _safe_text(value)

class ProjectEdit(ProjectCreate):
    expected_revision: int = Field(ge=1)

class ProjectRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)

class ProjectLink(ProjectRevision):
    resource_type: Literal["conversation", "document"]
    resource_id: UUID
