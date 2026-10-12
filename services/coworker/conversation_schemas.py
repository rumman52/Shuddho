"""Bounded user-authored conversation inputs; chat conveys no approval grant."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .goal_schemas import _safe_text


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        return _safe_text(value)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=12000)
    client_request_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    selected_resource_ids: list[UUID] = Field(default_factory=list, max_length=10)

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


class ConversationCancelRequest(BaseModel):
    """Exact owner-visible message and Agent progress revisions."""
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=1)
    expected_event_sequence: int = Field(ge=0)
