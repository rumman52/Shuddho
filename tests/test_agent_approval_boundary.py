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


# All non-streaming planner entry points must share the same provider boundary.
_PLANNER_CASES = [
    ("decide", {"decision": "needs_input", "message": "Please clarify."}, "invalid_planner_output"),
    ("propose", {"steps": [{"tool": "email.draft", "objective": "Draft the update."}]}, "invalid_planner_output"),
    ("propose_code", {"source": "print('ok')\n"}, "invalid_code_proposal"),
    ("propose_repository_patch", {"summary": "Draft patch", "changes": [
        {"path": "example.py", "operation": "create", "content": "print('ok')\n", "rationale": "Example"}
    ]}, "invalid_fly_patch"),
]


def _invoke_planner_boundary(method, body):
    planner = DeepSeekAgentPlanner(
        replace(settings(), deepseek_api_key="test-only-key"),
        httpx.MockTransport(lambda _request: httpx.Response(200, json=body)),
    )
    if method == "decide":
        return asyncio.run(planner.decide("Draft an update.", ["email.draft"], [],
                                          remaining_budget={}, dependencies={}))
    if method == "propose":
        return asyncio.run(planner.propose("Draft an update.", ["email.draft"]))
    if method == "propose_code":
        return asyncio.run(planner.propose_code("Draft an example."))
    return asyncio.run(planner.propose_repository_patch("Draft an example.", []))


def _planner_boundary_body(content):
    return {"choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(content),
    }}], "usage": {"total_tokens": 30, "prompt_tokens": 20, "completion_tokens": 10}}


@pytest.mark.parametrize("method,content,code", _PLANNER_CASES)
@pytest.mark.parametrize("invalid", ["role", "index", "bool_index", "error", "function_call",
                                     "tool_calls", "refusal", "finish"])
def test_all_planners_reject_unsafe_provider_envelopes(method, content, code, invalid):
    from services.coworker.agent_planning_model import PlannerFailure

    body = _planner_boundary_body(content)
    choice, message = body["choices"][0], body["choices"][0]["message"]
    if invalid == "role":
        message["role"] = "user"
    elif invalid == "index":
        choice["index"] = 1
    elif invalid == "bool_index":
        choice["index"] = False
    elif invalid == "error":
        body["error"] = {"message": "private"}
    elif invalid == "function_call":
        message["function_call"] = {"name": "unsafe"}
    elif invalid == "tool_calls":
        message["tool_calls"] = [{"id": "unsafe"}]
    elif invalid == "refusal":
        message["refusal"] = "refused"
    else:
        choice["finish_reason"] = "length"

    with pytest.raises(PlannerFailure) as error:
        _invoke_planner_boundary(method, body)
    assert error.value.code == code
    assert error.value.total_tokens == 30
    if method == "decide":
        assert (error.value.input_tokens, error.value.output_tokens) == (20, 10)


@pytest.mark.parametrize("method,content,_code", _PLANNER_CASES)
@pytest.mark.parametrize("usage,expected", [
    ({"total_tokens": -1}, None), ("malformed", None), ({"total_tokens": False}, None),
    ({"total_tokens": 0}, 0), ({"total_tokens": 30}, 30), (None, None),
])
def test_all_planners_preserve_unknown_usage_and_valid_counts(method, content, _code, usage, expected):
    body = _planner_boundary_body(content)
    body["usage"] = usage
    result = _invoke_planner_boundary(method, body)
    assert result[1] == expected


@pytest.mark.parametrize("method,content,_code", _PLANNER_CASES)
def test_all_planners_accept_legacy_omitted_role_and_index(method, content, _code):
    body = _planner_boundary_body(content)
    del body["choices"][0]["index"]
    del body["choices"][0]["message"]["role"]
    assert _invoke_planner_boundary(method, body)[1] == 30
