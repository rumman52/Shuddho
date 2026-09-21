"""Deterministic bounded planner for Agent Runtime v1."""
from __future__ import annotations

from .agent_schemas import AgentPlanStep
from .agent_tools import tool
from .config import Settings
from .errors import CoworkerError

_RULES = (
    ("research.search", ("research", "compare", "comparison", "competitor", "market", "latest", "current", "travel research")),
    ("presentation.create", ("presentation", "slides", "slide deck", "pitch deck", "deck")),
    ("spreadsheet.create", ("spreadsheet", "excel", "xlsx", "table", "budget", "calculate", "calculation")),
    ("meeting.prepare", ("meeting", "agenda", "minutes")),
    ("career.create", ("resume", "cv", "cover letter", "interview")),
    ("social.draft", ("social post", "linkedin", "facebook", "caption")),
    ("email.draft", ("email", "reply", "follow-up", "follow up")),
    ("daily_plan.create", ("daily plan", "weekly plan", "schedule", "routine")),
    ("personal_plan.create", ("personal plan", "household", "shopping list", "event plan")),
    ("report.create", ("report", "brief", "summary", "summarize")),
)


def deterministic_plan(goal: str, document_ids: list[str], output_language: str, settings: Settings, actions: list[dict] | None = None) -> list[AgentPlanStep]:
    normalized = " ".join(goal.lower().split())
    selected: list[str] = []
    for name, phrases in _RULES:
        if any(phrase in normalized for phrase in phrases):
            spec = tool(name)
            if spec.enabled(settings) and not spec.consequential:
                selected.append(name)
    actions = list(actions or [])
    if not selected and not actions:
        fallback = tool("document.create")
        if not fallback.enabled(settings):
            raise CoworkerError("no_agent_tool", "No suitable non-consequential agent tool is enabled.", 409)
        selected = ["document.create"]
    selected = list(dict.fromkeys(selected))[:3]
    steps: list[AgentPlanStep] = []
    for name in selected:
        spec = tool(name)
        arguments = {
            "instruction": goal,
            "notes": goal if name == "report.create" else "",
            "document_ids": document_ids,
            "output_language": output_language,
        }
        if name == "research.search":
            arguments["query"] = goal[:400]
            arguments["time_range"] = "any"
        steps.append(AgentPlanStep(tool=name, arguments=arguments))
    for action in actions[:3]:
        name = "email.send" if action["kind"] == "email_send" else "calendar.create"
        spec = tool(name)
        if not spec.enabled(settings):
            raise CoworkerError("tool_unavailable", "The attached action capability is not enabled.", 409)
        steps.append(AgentPlanStep(tool=name, arguments={"action_id": action["id"]}))
    if not 1 <= len(steps) <= 8:
        raise CoworkerError("invalid_plan", "The bounded agent plan is too large.", 422)
    return steps
