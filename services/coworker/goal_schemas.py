from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GoalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _safe_text(value: str) -> str:
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise ValueError("Text contains unsupported control characters")
    return value


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone offset")
    return value


class GoalMilestone(GoalModel):
    label: str = Field(min_length=1, max_length=200)
    due_at: datetime | None = None
    completed: bool = False

    @field_validator("label")
    @classmethod
    def safe_label(cls, value: str) -> str:
        return _safe_text(value)

    @field_validator("due_at")
    @classmethod
    def aware_due_at(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class GoalBudget(GoalModel):
    max_runs: int = Field(default=20, ge=1, le=1000)
    max_planner_tokens: int | None = Field(default=None, ge=1, le=10_000_000)


class GoalResource(GoalModel):
    kind: Literal["document", "memory_namespace"]
    reference: str = Field(min_length=1, max_length=128)

    @field_validator("reference")
    @classmethod
    def safe_reference(cls, value: str) -> str:
        return _safe_text(value)


class GoalCreate(GoalModel):
    objective: str = Field(min_length=3, max_length=4000)
    success_criteria: list[str] = Field(default_factory=list, max_length=10)
    constraints: list[str] = Field(default_factory=list, max_length=10)
    deadline_at: datetime | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    state: Literal["draft", "active"] = "active"
    milestones: list[GoalMilestone] = Field(default_factory=list, max_length=20)
    budget: GoalBudget = Field(default_factory=GoalBudget)
    authorized_resources: list[GoalResource] = Field(default_factory=list, max_length=20)
    next_review_at: datetime | None = None

    @field_validator("objective")
    @classmethod
    def safe_objective(cls, value: str) -> str:
        return _safe_text(value)

    @field_validator("success_criteria", "constraints")
    @classmethod
    def safe_lists(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 500 for value in values):
            raise ValueError("Goal list items must contain 1 to 500 characters")
        cleaned = [_safe_text(value) for value in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Goal list items must be unique")
        return cleaned

    @field_validator("deadline_at", "next_review_at")
    @classmethod
    def aware_dates(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Use a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def unique_resources(self):
        keys = {(item.kind, item.reference) for item in self.authorized_resources}
        if len(keys) != len(self.authorized_resources):
            raise ValueError("Authorized resources must be unique")
        return self


class GoalPatch(GoalModel):
    expected_revision: int = Field(ge=1)
    objective: str | None = Field(default=None, min_length=3, max_length=4000)
    success_criteria: list[str] | None = Field(default=None, max_length=10)
    constraints: list[str] | None = Field(default=None, max_length=10)
    deadline_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    milestones: list[GoalMilestone] | None = Field(default=None, max_length=20)
    budget: GoalBudget | None = None
    authorized_resources: list[GoalResource] | None = Field(default=None, max_length=20)
    next_review_at: datetime | None = None

    @field_validator("objective")
    @classmethod
    def safe_objective(cls, value: str | None) -> str | None:
        return _safe_text(value) if value is not None else None

    @field_validator("success_criteria", "constraints")
    @classmethod
    def safe_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if any(not value or len(value) > 500 for value in values):
            raise ValueError("Goal list items must contain 1 to 500 characters")
        cleaned = [_safe_text(value) for value in values]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Goal list items must be unique")
        return cleaned

    @field_validator("deadline_at", "next_review_at")
    @classmethod
    def aware_dates(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Use a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def has_change(self):
        if not (self.model_fields_set - {"expected_revision"}):
            raise ValueError("Patch at least one goal field")
        if self.authorized_resources is not None:
            keys = {(item.kind, item.reference) for item in self.authorized_resources}
            if len(keys) != len(self.authorized_resources):
                raise ValueError("Authorized resources must be unique")
        return self


class GoalTransition(GoalModel):
    expected_revision: int = Field(ge=1)


class GoalRunCreate(GoalModel):
    expected_revision: int = Field(ge=1)
    output_language: str = Field(default="en", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)
