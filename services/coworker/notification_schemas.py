from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NotificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NotificationPreferences(NotificationModel):
    in_app_enabled: bool = True
    automation_updates_enabled: bool = True
