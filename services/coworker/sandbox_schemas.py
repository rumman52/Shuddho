from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SandboxModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SandboxSessionCreate(SandboxModel):
    purpose: Literal["data_analysis", "code_task", "interactive_artifact"]
    runtime: Literal["python311"] = "python311"


class SandboxExecutionCreate(SandboxModel):
    source: str = Field(min_length=1, max_length=20000)
