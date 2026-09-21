"""Server-owned tool contracts for the bounded Agent Runtime foundation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Type

from pydantic import BaseModel

from .agent_schemas import ApprovedActionToolInput, ResearchToolInput, TaskToolInput
from .config import Settings
from .errors import CoworkerError

ToolKind = Literal["task", "approved_action"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    kind: ToolKind
    input_model: Type[BaseModel]
    skill_id: str | None = None
    capability: str | None = None
    consequential: bool = False
    approval_required: bool = False
    timeout_seconds: int = 180

    def public(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "consequential": self.consequential,
            "approval_required": self.approval_required,
            "timeout_seconds": self.timeout_seconds,
        }

    def enabled(self, settings: Settings) -> bool:
        if self.name == "research.search":
            return settings.research_services_enabled
        if self.name in {"presentation.create", "spreadsheet.create"}:
            return settings.artifact_services_enabled
        if self.kind == "approved_action":
            return settings.actions_enabled
        return settings.work_services_enabled or self.skill_id == "report_email"

    def validate(self, arguments: dict):
        try:
            return self.input_model.model_validate(arguments)
        except Exception as error:
            raise CoworkerError("invalid_tool_arguments", "The agent step has invalid tool arguments.", 422) from error


TOOLS = {
    spec.name: spec for spec in (
        ToolSpec("report.create", "1", "task", TaskToolInput, skill_id="report_email"),
        ToolSpec("document.create", "1", "task", TaskToolInput, skill_id="document"),
        ToolSpec("career.create", "1", "task", TaskToolInput, skill_id="career"),
        ToolSpec("social.draft", "1", "task", TaskToolInput, skill_id="social"),
        ToolSpec("daily_plan.create", "1", "task", TaskToolInput, skill_id="daily_plan"),
        ToolSpec("personal_plan.create", "1", "task", TaskToolInput, skill_id="personal_plan"),
        ToolSpec("email.draft", "1", "task", TaskToolInput, skill_id="email"),
        ToolSpec("meeting.prepare", "1", "task", TaskToolInput, skill_id="meeting"),
        ToolSpec("presentation.create", "1", "task", TaskToolInput, skill_id="presentation", timeout_seconds=240),
        ToolSpec("spreadsheet.create", "1", "task", TaskToolInput, skill_id="spreadsheet", timeout_seconds=240),
        ToolSpec("research.search", "1", "task", ResearchToolInput, skill_id="research", timeout_seconds=240),
        ToolSpec("email.send", "1", "approved_action", ApprovedActionToolInput, capability="email",
                 consequential=True, approval_required=True, timeout_seconds=120),
        ToolSpec("calendar.create", "1", "approved_action", ApprovedActionToolInput, capability="calendar",
                 consequential=True, approval_required=True, timeout_seconds=120),
    )
}


def tool(name: str) -> ToolSpec:
    value = TOOLS.get(name)
    if value is None:
        raise CoworkerError("unknown_tool", "This agent tool is not registered.", 409)
    return value


def available_tools(settings: Settings) -> list[dict]:
    return [spec.public() for spec in TOOLS.values() if spec.enabled(settings)]
