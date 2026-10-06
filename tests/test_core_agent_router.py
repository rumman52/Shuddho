from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import Response

from services.coworker.agent_router import qualify_agent_goal
from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.api import create_agent_run
from services.coworker.config import Settings
from services.coworker.errors import CoworkerError


def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        auth_issuer="https://identity.example.test/auth/v1",
        environment="development",
        storage_backend="local",
        work_services_enabled=True,
        artifact_services_enabled=True,
        research_services_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
    )


@pytest.mark.parametrize(
    ("goal", "execution", "capability", "tools"),
    [
        ("What is a semiconductor?", "direct_answer", "chat", []),
        ("Create a professional project document.", "agent_run", "document", ["document.create"]),
        ("Draft a professional follow-up email to the team.", "agent_run", "email", ["email.draft"]),
        (
            "Research the latest AI coworker market and summarize the findings.",
            "agent_run",
            "agent_workflow",
            ["research.search", "report.create"],
        ),
        ("Book a flight from Dhaka to Singapore next Friday.", "transactions", "transactions", []),
        ("Remind me tomorrow at 8 AM to review the release.", "automation", "automation", []),
        ("Send this on Slack.", "unsupported", "unregistered_connector_action", []),
        ("Send it.", "clarify", "unknown_action", []),
    ],
)
def test_core_agent_phase1_required_routes(goal, execution, capability, tools):
    route = qualify_agent_goal(goal, settings())
    assert route.execution == execution
    assert route.capability == capability
    assert route.tools == tools


def test_router_distinguishes_draft_from_consequential_send():
    draft = qualify_agent_goal("Draft an email to the finance team.", settings())
    send = qualify_agent_goal("Send this email to the finance team.", settings())
    assert draft.execution == "agent_run"
    assert draft.tools == ["email.draft"]
    assert draft.consequential is False
    assert send.execution == "actions"
    assert send.capability == "email"
    assert send.consequential is True


def test_router_selects_current_server_owned_providers():
    research = qualify_agent_goal("Research the latest market changes.", settings())
    document = qualify_agent_goal("Create a project memo.", settings())
    assert research.provider == "tavily"
    assert document.provider == "coworker_model"


def test_disabled_capability_fails_cleanly_instead_of_falling_back():
    disabled = replace(settings(), artifact_services_enabled=False)
    route = qualify_agent_goal("Create a presentation for the board.", disabled)
    assert route.execution == "unsupported"
    assert route.reason_code == "capability_disabled"
    assert route.capability_available is False


def test_unknown_imperative_does_not_become_document_tool():
    route = qualify_agent_goal("Rotate the production encryption keys.", settings())
    assert route.execution == "unsupported"
    assert route.reason_code == "no_registered_capability"
    assert route.tools == []


def test_simple_question_does_not_create_agent_run():
    class AgentMustNotRun:
        def create(self, *_args, **_kwargs):
            raise AssertionError("simple question created an Agent run")

    services = SimpleNamespace(settings=settings(), agent=AgentMustNotRun())
    identity = SimpleNamespace(account_id="owner-1")

    with pytest.raises(CoworkerError) as error:
        create_agent_run(
            AgentRunCreate(goal="What is retrieval augmented generation?"),
            identity,
            services,
            Response(),
            "question-must-not-run",
        )
    assert error.value.code == "agent_route_direct_answer"


def test_nonexistent_connector_cannot_be_selected_as_a_tool():
    route = qualify_agent_goal("Send this message on Discord.", settings())
    assert route.execution == "unsupported"
    assert route.tools == []
    assert route.provider == "none"
    assert route.reason_code == "connector_not_registered"


def test_informational_how_to_question_is_direct_not_transaction():
    route = qualify_agent_goal("How do I book a flight safely?", settings())
    assert route.execution == "direct_answer"
    assert route.consequential is False
