from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class SuggestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PersonalSuggestionPreferences(SuggestionModel):
    enabled: bool = False
    delivery_enabled: bool = False

    @model_validator(mode="after")
    def delivery_requires_preview(self):
        if self.delivery_enabled and not self.enabled:
            raise ValueError("Suggestion delivery requires deterministic suggestion preview to be enabled.")
        return self
