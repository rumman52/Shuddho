from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SuggestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PersonalSuggestionPreferences(SuggestionModel):
    enabled: bool = False
    delivery_enabled: bool = False
    event_delivery_enabled: bool = False
    event_timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @field_validator("event_timezone")
    @classmethod
    def valid_event_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Use a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def valid_delivery_hierarchy(self):
        if self.delivery_enabled and not self.enabled:
            raise ValueError(
                "Suggestion delivery requires deterministic suggestion preview to be enabled."
            )
        if self.event_delivery_enabled and not self.delivery_enabled:
            raise ValueError(
                "Event-triggered suggestion delivery requires in-app suggestion delivery to be enabled."
            )
        return self
