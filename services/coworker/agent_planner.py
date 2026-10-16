"""Deterministic bounded planner for Agent Runtime v1."""
from __future__ import annotations

import re


from .agent_schemas import AgentPlanStep, AgentPlannerProposal
from .approval_boundary import assert_model_tool_surface
from .agent_tools import TOOLS, tool
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


def deterministic_plan(goal: str, document_ids: list[str], output_language: str, settings: Settings, actions: list[dict] | None = None, *, tool_allowlist: list[str] | None = None) -> list[AgentPlanStep]:
    normalized = " ".join(goal.lower().split())
    permitted = set(tool_allowlist or [])
    selected: list[str] = []
    for name, phrases in _RULES:
        if any(phrase in normalized for phrase in phrases):
            spec = tool(name)
            if spec.enabled(settings) and not spec.consequential and (not permitted or name in permitted):
                selected.append(name)
    actions = list(actions or [])
    if not selected and not actions:
        raise CoworkerError(
            "no_agent_tool",
            "No registered non-consequential Agent capability matches this request.",
            409,
        )
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
            raise CoworkerError("tool_not_supported", "The attached action capability is not enabled in this runtime.", 409)
        steps.append(AgentPlanStep(tool=name, arguments={"action_id": action["id"]}))
    if not 1 <= len(steps) <= 8:
        raise CoworkerError("invalid_plan", "The bounded agent plan is too large.", 422)
    return steps



def action_selection_candidates(actions: list[dict] | None) -> dict[str, dict]:
    candidates: dict[str, dict] = {}
    for index, action in enumerate(list(actions or [])[:3], 1):
        if action.get("state") != "awaiting_approval":
            continue
        kind = action.get("kind")
        capability = "email" if kind == "email_send" else "calendar" if kind == "calendar_create" else None
        if capability is None:
            continue
        candidates[f"attached.{capability}.{index}"] = action
    return candidates


_PYTHON_FENCE = re.compile(r"```(?:python|py)\r?\n([\s\S]*?)\r?\n```", re.IGNORECASE)


def exact_user_python_source(goal: str, settings: Settings) -> str | None:
    """Return one exact user-authored Python fence or no planner authority.

    Extra prose around the fence is allowed, but a second fenced block is
    rejected so the model cannot choose among ambiguous executable inputs.
    """
    matches = list(_PYTHON_FENCE.finditer(goal))
    if len(matches) != 1 or goal.count("```") != 2:
        return None
    source = matches[0].group(1)
    encoded = source.encode("utf-8")
    if not source or len(encoded) > settings.sandbox_max_source_bytes:
        return None
    return source


def explicit_browser_url(goal: str) -> str | None:
    """Never let a planner invent browser destinations or sessions."""
    candidates = [
        raw.rstrip(".,;!?)]}")
        for raw in re.findall(r"https://[^\s<>\"']+", goal)
    ]
    if len(candidates) != 1:
        return None
    try:
        # The lightweight Agent evaluation suite intentionally omits SQLAlchemy.
        # Import the supervised broker only for an actually eligible browser URL.
        from .browser import normalize_browser_target
        normalized, _origin = normalize_browser_target(candidates[0])
    except CoworkerError:
        return None
    return normalized


def intelligent_tool_names(
    settings: Settings,
    actions: list[dict] | None = None,
    *,
    goal: str | None = None,
    runtime_version: int | None = None,
    tool_allowlist: list[str] | None = None,
) -> list[str]:
    allowed = set(tool_allowlist or [])
    names = [
        spec.name for spec in TOOLS.values()
        if spec.kind == "task"
        and not spec.consequential
        and not spec.approval_required
        and spec.enabled(settings)
        and (not allowed or spec.name in allowed)
    ]
    sandbox = TOOLS.get("sandbox.execute_python")
    if (
        runtime_version == 3
        and goal is not None
        and sandbox is not None
        and sandbox.enabled(settings)
        and exact_user_python_source(goal, settings) is not None
        and (not allowed or sandbox.name in allowed)
    ):
        names.append(sandbox.name)
    browser = TOOLS.get("browser.read")
    if (
        runtime_version == 3
        and goal is not None
        and browser is not None
        and browser.enabled(settings)
        and explicit_browser_url(goal) is not None
        and (not allowed or browser.name in allowed)
    ):
        names.append(browser.name)
    # Attached action handles are independently bound to the run and approved
    # via ExternalAction; a task-tool grant must not suppress those handles.
    if settings.agent_action_selection_enabled:
        names.extend(action_selection_candidates(actions))
    assert_model_tool_surface(names)
    return names


def proposal_to_plan(proposal: AgentPlannerProposal, goal: str, document_ids: list[str],
                     output_language: str, settings: Settings, actions: list[dict] | None = None, *,
                     tool_allowlist: list[str] | None = None) -> list[AgentPlanStep]:
    steps: list[AgentPlanStep] = []
    actions = list(actions or [])[:3]
    candidates = action_selection_candidates(actions) if settings.agent_action_selection_enabled else {}
    allowed = set(intelligent_tool_names(settings, actions, tool_allowlist=tool_allowlist))
    selected_action_ids: set[str] = set()
    for choice in proposal.steps:
        if choice.tool not in allowed:
            raise CoworkerError("planner_tool_scope", "The planner selected a tool outside the allowed registry.", 409)
        selected = candidates.get(choice.tool)
        if selected is not None:
            name = "email.send" if selected["kind"] == "email_send" else "calendar.create"
            spec = tool(name)
            if not spec.enabled(settings):
                raise CoworkerError("tool_not_supported", "The attached action capability is not enabled in this runtime.", 409)
            selected_action_ids.add(selected["id"])
            steps.append(AgentPlanStep(tool=name, arguments={"action_id": selected["id"]}))
            continue
        arguments = {
            "instruction": goal,
            "notes": goal if choice.tool == "report.create" else "",
            "document_ids": document_ids,
            "output_language": output_language,
        }
        if choice.tool == "research.search":
            arguments["query"] = goal[:400]
            arguments["time_range"] = "any"
        steps.append(AgentPlanStep(tool=choice.tool, arguments=arguments))

    for action in actions:
        if settings.agent_action_selection_enabled:
            # A user may approve a bound draft before planning finishes. Once it
            # leaves awaiting_approval it is no longer model-selectable and is
            # retained by the server automatically.
            if action.get("state") == "awaiting_approval":
                continue
        if action["id"] in selected_action_ids:
            continue
        name = "email.send" if action["kind"] == "email_send" else "calendar.create"
        spec = tool(name)
        if not spec.enabled(settings):
            raise CoworkerError("tool_not_supported", "The attached action capability is not enabled in this runtime.", 409)
        steps.append(AgentPlanStep(tool=name, arguments={"action_id": action["id"]}))
    if not 1 <= len(steps) <= 8:
        raise CoworkerError("invalid_plan", "The bounded agent plan is too large.", 422)
    return steps
