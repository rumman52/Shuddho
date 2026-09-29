from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SuggestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PersonalSuggestionPreferences(SuggestionModel):
    enabled: bool = False
