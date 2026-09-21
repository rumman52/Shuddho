from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Namespace = Literal["profile", "preferences", "project", "organization", "writing"]


def _safe(value: str) -> str:
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise ValueError("Text contains unsupported control characters")
    return value


class MemoryFactCreate(MemoryModel):
    namespace: Namespace
    key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    value: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="auto", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)
    expires_at: datetime | None = None

    @field_validator("value")
    @classmethod
    def safe_value(cls, value: str) -> str:
        return _safe(value)


class MemoryFactUpdate(MemoryModel):
    value: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="auto", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)
    expires_at: datetime | None = None

    @field_validator("value")
    @classmethod
    def safe_value(cls, value: str) -> str:
        return _safe(value)
