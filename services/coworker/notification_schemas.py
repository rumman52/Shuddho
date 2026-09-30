from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .notification_digests import MAX_DIGEST_ITEMS


class NotificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NotificationPreferences(NotificationModel):
    in_app_enabled: bool = True
    automation_updates_enabled: bool = True


class NotificationDigestRead(NotificationModel):
    notification_ids: list[UUID] = Field(min_length=1, max_length=MAX_DIGEST_ITEMS)

    @field_validator("notification_ids")
    @classmethod
    def unique_members(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Digest members must be unique.")
        return value
