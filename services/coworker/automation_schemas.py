from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


class AutomationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone offset")
    return value


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Use a valid IANA timezone") from error
    return value


class AutomationSchedule(AutomationModel):
    kind: Literal["daily", "weekly"]
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    weekdays: list[str] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def valid_weekdays(self):
        values = [item.lower() for item in self.weekdays]
        if len(set(values)) != len(values) or any(item not in WEEKDAYS for item in values):
            raise ValueError("Weekdays must be unique values from mon through sun")
        if self.kind == "weekly" and not values:
            raise ValueError("Weekly schedules need at least one weekday")
        if self.kind == "daily" and values:
            raise ValueError("Daily schedules do not accept weekdays")
        self.weekdays = values
        return self


class QuietHours(AutomationModel):
    start: str = Field(pattern=r"^(?:[01]d|2[0-3]):[0-5]d$")
    end: str = Field(pattern=r"^(?:[01]d|2[0-3]):[0-5]d$")

    @model_validator(mode="after")
    def not_empty(self):
        if self.start == self.end:
            raise ValueError("Quiet hours start and end must differ")
        return self


class AutomationCreate(AutomationModel):
    goal_id: UUID
    goal_revision: int = Field(ge=1)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    schedule: AutomationSchedule
    output_language: str = Field(default="en", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)
    overlap_policy: Literal["skip", "buffer_one"] = "skip"
    catchup_window_seconds: int = Field(default=3600, ge=60, le=86400)
    quiet_hours: QuietHours | None = None
    expires_at: datetime | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return _timezone(value)

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class AutomationPatch(AutomationModel):
    expected_revision: int = Field(ge=1)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    schedule: AutomationSchedule | None = None
    output_language: str | None = Field(default=None, pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)
    overlap_policy: Literal["skip", "buffer_one"] | None = None
    catchup_window_seconds: int | None = Field(default=None, ge=60, le=86400)
    quiet_hours: QuietHours | None = None
    expires_at: datetime | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return _timezone(value) if value is not None else None

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @model_validator(mode="after")
    def valid_patch(self):
        fields = self.model_fields_set - {"expected_revision"}
        if not fields:
            raise ValueError("Patch at least one automation field")
        required = {"timezone", "schedule", "output_language", "overlap_policy", "catchup_window_seconds"}
        if any(field in fields and getattr(self, field) is None for field in required):
            raise ValueError("Required automation fields cannot be null")
        return self


class AutomationTransition(AutomationModel):
    expected_revision: int = Field(ge=1)


class NotificationRead(AutomationModel):
    notification_id: UUID
