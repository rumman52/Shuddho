"""Server-owned Core Agent intent qualification and capability routing.

This layer runs before an ordinary public Agent run is created. It is deliberately
provider-free and registry-backed: user text can select only code-owned routes and
registered tools, never arbitrary connectors, providers, endpoints, or tool names.
"""
from __future__ import annotations

import re

from .agent_schemas import AgentRouteDecision
from .agent_tools import tool
from .config import Settings


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains(text: str, phrase: str) -> bool:
    if phrase.isascii() and re.fullmatch(r"[a-z0-9 ._+-]+", phrase):
        pattern = r"(?<![a-z0-9_])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![a-z0-9_])"
        return re.search(pattern, text) is not None
    return phrase in text


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains(text, phrase) for phrase in phrases)


def _research_requested(text: str) -> bool:
    """Treat 'current sources/documents' as local context, not an implicit web search."""
    explicit = tuple(item for item in _RESEARCH_MARKERS if item != "current")
    if _has_any(text, explicit):
        return True
    if not _contains(text, "current"):
        return False
    local_context = (
        "current source",
        "current sources",
        "my current source",
        "my current sources",
        "current document",
        "current documents",
        "my current document",
        "my current documents",
    )
    return not _has_any(text, local_context)


_QUESTION_PREFIXES = (
    "what is ",
    "what are ",
    "who is ",
    "who are ",
    "why ",
    "how ",
    "where is ",
    "where are ",
    "when is ",
    "when does ",
    "explain ",
    "define ",
    "tell me about ",
    "কি ",
    "কেন ",
    "কিভাবে ",
    "কে ",
    "কখন ",
    "কোথায় ",
)

_RESEARCH_MARKERS = (
    "research",
    "look up",
    "search for",
    "find online",
    "web research",
    "latest",
    "current",
    "recent",
    "today",
    "this week",
    "right now",
    "up to date",
    "competitor",
    "market developments",
    "গবেষণা",
    "সর্বশেষ",
    "বর্তমান",
)

_AUTOMATION_MARKERS = (
    "remind me",
    "reminder",
    "notify me",
    "alert me",
    "every day",
    "every morning",
    "every evening",
    "every week",
    "every month",
    "daily reminder",
    "weekly reminder",
    "when it becomes",
    "when the price",
    "when available",
    "মনে করিয়ে",
    "রিমাইন্ডার",
    "নোটিফাই",
    "প্রতি দিন",
    "প্রতিদিন",
)

_PAYMENT_UNSUPPORTED = (
    "transfer money",
    "send money",
    "wire money",
    "bank transfer",
    "pay my bill",
    "pay the bill",
    "cash out",
    "withdraw money",
)

_TRANSACTION_MARKERS = (
    "checkout",
    "check out this cart",
    "buy this",
    "purchase this",
    "place the order",
    "order this",
    "book a flight",
    "book flight",
    "book a hotel",
    "book hotel",
    "travel booking",
    "reserve a table",
    "restaurant reservation",
    "book a table",
    "negotiate this",
    "negotiate the price",
    "counter offer",
    "counteroffer",
    "কিনতে",
    "বুক কর",
    "রিজার্ভ",
    "ফ্লাইট বুক",
    "হোটেল বুক",
)

_UNSUPPORTED_CONNECTORS = (
    "slack",
    "whatsapp",
    "discord",
    "telegram",
    "dropbox",
    "notion",
)

_ACTION_VERBS = (
    "send",
    "publish",
    "post",
    "book",
    "reserve",
    "buy",
    "purchase",
    "pay",
    "delete",
    "cancel",
    "transfer",
    "invite",
    "submit",
)

_AGENT_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "research.search",
        "research",
        ("research", "compare", "comparison", "competitor", "market", "latest", "current", "recent", "look up", "search for", "গবেষণা", "সর্বশেষ"),
    ),
    (
        "presentation.create",
        "presentation",
        ("presentation", "slides", "slide deck", "pitch deck", "deck"),
    ),
    (
        "spreadsheet.create",
        "spreadsheet",
        ("spreadsheet", "excel", "xlsx", "budget table", "financial model", "calculation sheet"),
    ),
    (
        "meeting.prepare",
        "meeting",
        ("meeting agenda", "meeting minutes", "minutes for", "prepare an agenda", "meeting notes", "meeting pack", "investor pack"),
    ),
    (
        "career.create",
        "career",
        ("resume", "curriculum vitae", "cover letter", "interview prep", "interview preparation", "cv"),
    ),
    (
        "social.draft",
        "social",
        ("social post", "linkedin post", "facebook post", "instagram caption", "social caption"),
    ),
    (
        "email.draft",
        "email",
        ("email draft", "draft an email", "draft email", "suggest an email", "suggest email", "reply email", "follow-up email", "follow up email", "professional email", "ইমেইল ড্রাফট", "মেইল ড্রাফট"),
    ),
    (
        "daily_plan.create",
        "daily_plan",
        ("daily plan", "weekly plan", "work plan", "routine", "daily schedule"),
    ),
    (
        "personal_plan.create",
        "personal_plan",
        ("personal plan", "household plan", "shopping list", "event plan", "travel plan", "trip plan"),
    ),
    (
        "report.create",
        "report",
        ("report", "brief", "summary", "summarize", "summarise", "status update"),
    ),
    (
        "document.create",
        "document",
        ("document", "letter", "memo", "proposal", "sop", "application", "essay", "statement", "article", "story", "poem", "চিঠি", "আবেদন", "ডকুমেন্ট"),
    ),
)


def _decision(
    *,
    intent: str,
    complexity: str,
    execution: str,
    capability: str,
    tools: list[str] | None = None,
    provider: str = "none",
    access: str = "read",
    consequential: bool = False,
    capability_available: bool = True,
    confidence: float = 1.0,
    fallback_policy: str,
    reason_code: str,
    message: str,
) -> AgentRouteDecision:
    return AgentRouteDecision(
        intent=intent,
        complexity=complexity,
        execution=execution,
        capability=capability,
        tools=tools or [],
        provider=provider,
        access=access,
        consequential=consequential,
        capability_available=capability_available,
        confidence=confidence,
        fallback_policy=fallback_policy,
        reason_code=reason_code,
        message=message,
    )


def _question_like(text: str) -> bool:
    return text.startswith(_QUESTION_PREFIXES)


def _ambiguous_high_impact(text: str) -> bool:
    return re.fullmatch(
        r"(?:please\s+)?(?:send|publish|post|book|reserve|buy|purchase|pay|delete|cancel|transfer|submit)"
        r"(?:\s+(?:it|this|that|them))?(?:\s+now)?(?:\s+for\s+me)?[.!]?",
        text,
    ) is not None


def qualify_agent_goal(
    goal: str,
    settings: Settings,
    *,
    has_attached_actions: bool = False,
) -> AgentRouteDecision:
    """Classify a user goal before a public Agent run or planner call.

    The result contains only server-owned route/provider/tool identifiers.
    """
    text = _normalize(goal)
    if not text:
        return _decision(
            intent="unsupported",
            complexity="simple",
            execution="unsupported",
            capability="none",
            confidence=1.0,
            fallback_policy="unsupported",
            reason_code="empty_goal",
            message="A non-empty request is required.",
        )

    research_requested = _research_requested(text)

    # Clear explanatory questions are direct even when they mention an action
    # as a concept (for example, "How do I book a flight?").
    if _question_like(text) and not research_requested:
        return _decision(
            intent="direct_question",
            complexity="simple",
            execution="direct_answer",
            capability="chat",
            provider="none",
            access="read",
            confidence=0.99,
            fallback_policy="direct",
            reason_code="direct_question",
            message="Answer this request directly without creating an Agent run.",
        )

    if _ambiguous_high_impact(text):
        return _decision(
            intent="ambiguous_action",
            complexity="consequential",
            execution="clarify",
            capability="unknown_action",
            provider="none",
            access="action",
            consequential=True,
            capability_available=False,
            confidence=0.99,
            fallback_policy="clarify",
            reason_code="ambiguous_consequential_action",
            message="Clarify the target and exact requested action before any consequential operation.",
        )

    if _has_any(text, _PAYMENT_UNSUPPORTED):
        return _decision(
            intent="unsupported",
            complexity="consequential",
            execution="unsupported",
            capability="payments_or_transfers",
            provider="none",
            access="action",
            consequential=True,
            capability_available=False,
            confidence=0.99,
            fallback_policy="unsupported",
            reason_code="unsupported_payment_authority",
            message="Shuddho does not have general payment, bank-transfer, or cash-movement authority.",
        )

    if _has_any(text, _UNSUPPORTED_CONNECTORS) and _has_any(text, _ACTION_VERBS):
        return _decision(
            intent="unsupported",
            complexity="consequential",
            execution="unsupported",
            capability="unregistered_connector_action",
            provider="none",
            access="action",
            consequential=True,
            capability_available=False,
            confidence=0.99,
            fallback_policy="unsupported",
            reason_code="connector_not_registered",
            message="That connector/action is not registered for execution.",
        )

    if _has_any(text, _AUTOMATION_MARKERS):
        destructive = _has_any(text, ("cancel", "delete", "stop", "disable"))
        return _decision(
            intent="automation",
            complexity="consequential" if destructive else "single_step",
            execution="automation",
            capability="automation",
            provider="temporal",
            access="action",
            consequential=destructive,
            confidence=0.99,
            fallback_policy="domain_handler",
            reason_code="automation_intent",
            message="Route this request to the Automation capability, not the general Agent planner.",
        )

    if "shopping list" not in text and _has_any(text, _TRANSACTION_MARKERS):
        return _decision(
            intent="transaction",
            complexity="consequential",
            execution="transactions",
            capability="transactions",
            provider="transaction_registry",
            access="action",
            consequential=True,
            confidence=0.99,
            fallback_policy="domain_handler",
            reason_code="transaction_intent",
            message="Route this request to the Transactions domain and its qualified provider registry.",
        )

    # Consequential connected actions are kept out of ordinary tool planning.
    email_action = _has_any(text, ("email", "e-mail", "mail", "ইমেইল", "মেইল")) and _contains(text, "send")
    calendar_action = _has_any(text, ("calendar", "schedule a meeting", "schedule meeting", "add an event", "create an event"))
    social_action = _has_any(text, ("linkedin", "facebook", "social")) and _has_any(text, ("publish", "post"))
    document_share_action = (
        _has_any(text, ("document", "file", "artifact"))
        and _has_any(text, ("share", "grant access", "send access"))
    )
    draft_only = _has_any(text, ("draft", "prepare a draft", "write a draft", "caption"))
    if (email_action and not draft_only) or calendar_action or (social_action and not draft_only) or document_share_action:
        capability = (
            "email" if email_action
            else "calendar" if calendar_action
            else "social_publish" if social_action
            else "document_share"
        )
        return _decision(
            intent="external_action",
            complexity="consequential",
            execution="actions",
            capability=capability,
            provider="bound_connection",
            access="action",
            consequential=True,
            confidence=0.98,
            fallback_policy="domain_handler",
            reason_code="consequential_connected_action",
            message="Route this request through the bound action preview/approval path; do not let the planner invent a connector or endpoint.",
        )

    if text.endswith("?"):
        return _decision(
            intent="direct_question",
            complexity="simple",
            execution="direct_answer",
            capability="chat",
            provider="none",
            access="read",
            confidence=0.95,
            fallback_policy="direct",
            reason_code="direct_question",
            message="Answer this request directly without creating an Agent run.",
        )

    selected: list[str] = []
    intents: list[str] = []
    for name, intent, phrases in _AGENT_RULES:
        if name == "research.search":
            matched = research_requested or _has_any(
                text,
                tuple(phrase for phrase in phrases if phrase != "current"),
            )
        else:
            matched = _has_any(text, phrases)
        if not matched:
            continue
        spec = tool(name)
        if not spec.enabled(settings):
            return _decision(
                intent=intent,
                complexity="single_step",
                execution="unsupported",
                capability=spec.skill_id or name,
                provider="none",
                access="read" if name == "research.search" else "write",
                capability_available=False,
                confidence=0.99,
                fallback_policy="unsupported",
                reason_code="capability_disabled",
                message=f"The required capability '{spec.skill_id or name}' is currently disabled.",
            )
        selected.append(name)
        intents.append(intent)

    selected = list(dict.fromkeys(selected))[:3]
    intents = list(dict.fromkeys(intents))

    if selected:
        if len(selected) > 1:
            complexity = "multi_step"
            intent = "multi_tool"
        else:
            complexity = "single_step"
            intent = intents[0]
        has_research = "research.search" in selected
        access = "read_write" if has_research and len(selected) > 1 else "read" if has_research else "write"
        if has_research and len(selected) > 1:
            provider = f"{settings.search_provider}+coworker_model"
        elif has_research:
            provider = settings.search_provider
        else:
            provider = "coworker_model"
        return _decision(
            intent=intent,
            complexity=complexity,
            execution="agent_run",
            capability="agent_workflow" if len(selected) > 1 else (tool(selected[0]).skill_id or selected[0]),
            tools=selected,
            provider=provider,
            access=access,
            confidence=0.99 if len(selected) == 1 else 0.97,
            fallback_policy="deterministic_agent",
            reason_code="registered_agent_capability",
            message="Create a bounded Agent run using only the selected registered tools.",
        )

    if has_attached_actions:
        return _decision(
            intent="attached_action",
            complexity="consequential",
            execution="agent_run",
            capability="approved_actions",
            tools=[],
            provider="bound_connection",
            access="action",
            consequential=True,
            confidence=0.99,
            fallback_policy="deterministic_agent",
            reason_code="attached_approved_action",
            message="Create the bounded Agent run; attached action handles remain subject to immutable approval.",
        )

    # Unknown imperative requests must not be silently converted into a document.
    return _decision(
        intent="unsupported",
        complexity="simple",
        execution="unsupported",
        capability="none",
        provider="none",
        access="read",
        capability_available=False,
        confidence=0.90,
        fallback_policy="unsupported",
        reason_code="no_registered_capability",
        message="No registered Shuddho capability matches this request.",
    )
