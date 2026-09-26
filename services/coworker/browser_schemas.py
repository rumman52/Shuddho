from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrowserModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BrowserSessionCreate(BrowserModel):
    purpose: Literal["research", "form_prepare"]
    start_url: str = Field(min_length=8, max_length=4096)


class BrowserNavigateCreate(BrowserModel):
    url: str = Field(min_length=8, max_length=4096)


class BrowserTakeoverCreate(BrowserModel):
    reason: Literal["login", "mfa", "captcha", "sensitive_input"]
