"""Bounded user-authored conversation inputs; chat conveys no approval grant."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .goal_schemas import _safe_text
from .task_brief_schemas import MemoryPin


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        return _safe_text(value)


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    expected_updated_at: str = Field(min_length=1, max_length=64)

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        return _safe_text(value)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=12000)
    client_request_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    selected_resource_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @field_validator("text")
    @classmethod
    def safe_text(cls, value: str) -> str:
        return _safe_text(value)

    @field_validator("selected_resource_ids")
    @classmethod
    def unique_sources(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Select each resource once")
        return value


class ConversationDispatchCreate(BaseModel):
    """Optimistic revision binding; no action IDs or approval authority."""
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=1)
    output_language: str = Field(default="auto", max_length=35, pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$")
    project_id: UUID | None = None
    # None: legacy dispatch; []: reviewed brief with no memory.
    memory_pins: list[MemoryPin] | None = Field(default=None, max_length=20)


class ConversationSteerRequest(BaseModel):
    """A bounded user instruction for one active Runtime v3 run."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_sequence: int = Field(ge=1)
    expected_steering_revision: int = Field(ge=0)
    instruction: str = Field(min_length=1, max_length=4000)

    @field_validator("instruction")
    @classmethod
    def safe_instruction(cls, value: str) -> str:
        return _safe_text(value)


class ConversationCancelRequest(BaseModel):
    """Exact owner-visible message and Agent progress revisions."""
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=1)
    expected_event_sequence: int = Field(ge=0)


class ConversationReplyCreate(BaseModel):
    """Only the persisted message's selected_sources may ground a reply.

    No new file IDs, citations or action authority may be supplied here.
    """
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=1)
    project_id: UUID | None = None
