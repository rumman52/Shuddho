from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from services.coworker.approval_boundary import (
    assert_inert_proposal_payload,
    assert_model_action_proposals,
    assert_model_tool_surface,
)
from services.coworker.agent_planning_model import DeepSeekAgentPlanner
from services.coworker.agent_router import qualify_agent_goal
from services.coworker.agent_schemas import AgentActionProposal
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
        actions_enabled=True,
        agent_action_proposals_enabled=True,
        agent_linkedin_proposals_enabled=True,
        personal_transactions_enabled=True,
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "email.send",
        "calendar.create",
        "document.share",
        "social.publish",
        "restaurant_reservation_create",
        "shopping_checkout_create",
        "travel_booking_create",
        "provider.update",
    ],
)
def test_phase5_model_cannot_receive_direct_mutation_tool(tool_name):
    with pytest.raises(CoworkerError) as error:
        assert_model_tool_surface([tool_name])
    assert error.value.code == "approval_boundary"


def test_phase5_model_may_only_select_opaque_prepared_action_handles():
    assert_model_tool_surface(["email.draft", "attached.email.1", "attached.calendar.2"])

    with pytest.raises(CoworkerError) as error:
        assert_model_tool_surface(["email.send"])
    assert error.value.code == "approval_boundary"


def test_phase5_email_proposal_is_inert_and_does_not_execute():
    proposal = AgentActionProposal.model_validate({
        "payload": {
            "kind": "email_send",
            "to": ["person@example.org"],
            "cc": [],
            "bcc": [],
            "subject": "Project update",
            "body": "Ready for review.",
        },
        "rationale": "The user asked for an email suggestion.",
    })
    assert_model_action_proposals(
        [proposal],
        allow_action_proposals=True,
        allow_linkedin_action_proposals=False,
    )


def test_phase5_calendar_proposal_is_inert_and_does_not_execute():
    proposal = AgentActionProposal.model_validate({
        "payload": {
            "kind": "calendar_create",
            "title": "Project review",
            "start_at": "2030-01-02T09:00:00+00:00",
            "end_at": "2030-01-02T09:30:00+00:00",
            "time_zone": "UTC",
            "attendees": ["person@example.org"],
            "description": "Review the project.",
        },
        "rationale": "The user asked for a calendar suggestion.",
    })
    assert_model_action_proposals(
        [proposal],
        allow_action_proposals=True,
        allow_linkedin_action_proposals=False,
    )


def test_phase5_social_publish_proposal_requires_explicit_server_gate():
    proposal = AgentActionProposal.model_validate({
        "payload": {
            "kind": "social_publish_linkedin",
            "text": "Project update",
        },
        "rationale": "The user asked for a LinkedIn post suggestion.",
    })

    with pytest.raises(CoworkerError) as error:
        assert_model_action_proposals(
            [proposal],
            allow_action_proposals=True,
            allow_linkedin_action_proposals=False,
        )
    assert error.value.code == "approval_boundary"

    assert_model_action_proposals(
        [proposal],
        allow_action_proposals=True,
        allow_linkedin_action_proposals=True,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "document_share"},
        {"kind": "restaurant_reservation_create"},
        {"kind": "shopping_checkout_create"},
        {"kind": "travel_booking_create"},
        {"kind": "provider_record_update"},
    ],
)
def test_phase5_model_cannot_persist_direct_mutation_proposal(payload):
    with pytest.raises(CoworkerError) as error:
        assert_inert_proposal_payload(
            payload,
            allow_linkedin_action_proposals=True,
        )
    assert error.value.code == "approval_boundary"


@pytest.mark.parametrize(
    ("goal", "execution", "capability"),
    [
        ("Send this email to the finance team.", "actions", "email"),
        ("Create a calendar event for tomorrow at 9 AM.", "actions", "calendar"),
        ("Publish this on LinkedIn.", "actions", "social_publish"),
        ("Share this document with reader@example.org.", "actions", "document_share"),
        ("Book a flight from Dhaka to Singapore next Friday.", "transactions", "transactions"),
        ("Reserve a table for two tonight.", "transactions", "transactions"),
        ("Buy this cart now.", "transactions", "transactions"),
    ],
)
def test_phase5_consequential_requests_never_enter_general_agent_planner(
    goal,
    execution,
    capability,
):
    route = qualify_agent_goal(goal, settings())
    assert route.execution == execution
    assert route.capability == capability
    assert route.consequential is True
    assert route.tools == []


@pytest.mark.parametrize(
    "goal",
    [
        "Draft an email to the finance team.",
        "Write a LinkedIn post draft about our launch.",
        "Prepare a project document.",
        "Summarize this report.",
    ],
)
def test_phase5_non_consequential_work_remains_available_to_agent(goal):
    route = qualify_agent_goal(goal, settings())
    assert route.execution == "agent_run"
    assert route.consequential is False


def test_phase5_unknown_provider_mutation_fails_closed():
    route = qualify_agent_goal(
        "Modify the provider record and overwrite the remote customer status.",
        settings(),
    )
    assert route.execution == "unsupported"
    assert route.capability_available is False
    assert route.tools == []


def test_phase5_planning_model_cannot_smuggle_linkedin_publish_when_gate_is_off():
    def respond(_request: httpx.Request) -> httpx.Response:
        content = {
            "steps": [
                {
                    "tool": "email.draft",
                    "objective": "Draft the supporting update.",
                }
            ],
            "action_proposals": [
                {
                    "payload": {
                        "kind": "social_publish_linkedin",
                        "text": "Publish this without approval.",
                    },
                    "rationale": "Attempted direct social mutation.",
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(content),
                        },
                    }
                ],
                "usage": {"total_tokens": 10},
            },
        )

    configured = replace(
        settings(),
        deepseek_api_key="test-only-key",
        agent_action_proposals_enabled=True,
        agent_linkedin_proposals_enabled=False,
    )
    planner = DeepSeekAgentPlanner(
        configured,
        httpx.MockTransport(respond),
    )

    with pytest.raises(CoworkerError) as error:
        asyncio.run(
            planner.propose(
                "Draft an update and publish it on LinkedIn.",
                ["email.draft"],
                allow_action_proposals=True,
                allow_linkedin_action_proposals=False,
            )
        )
    assert error.value.code == "approval_boundary"
