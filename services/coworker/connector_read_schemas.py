from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConnectorReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConnectorReadGrantCreate(ConnectorReadModel):
    connection_id: UUID
    purpose: Literal["agent_context"] = "agent_context"
    destination: Literal["planner_context"] = "planner_context"
    expires_at: datetime

    @model_validator(mode="after")
    def bounded_expiry(self):
        value = self.expires_at
        if value.tzinfo is None:
            raise ValueError("Read-grant expiry must include a UTC offset")
        now = datetime.now(timezone.utc)
        if value.astimezone(timezone.utc) <= now + timedelta(minutes=5):
            raise ValueError("Read grants must remain valid for at least five minutes")
        if value.astimezone(timezone.utc) > now + timedelta(days=30):
            raise ValueError("Read grants may last at most 30 days")
        return self


class ConnectorReadSyncRequest(ConnectorReadModel):
    force_full: bool = False
    max_items: int = Field(default=30, ge=1, le=100)
