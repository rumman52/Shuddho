from __future__ import annotations

import httpx
import pytest

pytest.importorskip(
    "sqlalchemy",
    reason="Install the coworker extra for LinkedIn Agent-proposal staging tests",
)

from scripts import staging_live_linkedin_agent_proposals as live
from services.coworker.action_repository import digest
from services.coworker.agent_schemas import action_proposal_hash


RUN_ID = "11111111-1111-1111-1111-111111111111"
PROPOSAL_ID = "22222222-2222-2222-2222-222222222222"
ACTION_ID = "33333333-3333-3333-3333-333333333333"
CONNECTION_ID = "44444444-4444-4444-4444-444444444444"
MARKER = "shuddho-linkedin-proposal-testmarker"


def proposal():
    payload = {
        "kind": "social_publish_linkedin",
        "text": f"Synthetic LinkedIn proposal {MARKER}",
    }
    rationale = "The user explicitly requested this LinkedIn post suggestion."
    return {
        "id": PROPOSAL_ID,
        "kind": "social_publish_linkedin",
        "payload": payload,
        "rationale": rationale,
        "proposal_hash": action_proposal_hash(RUN_ID, payload, rationale),
        "state": "suggested",
        "promoted_action_id": None,
    }


def run_value():
    return {
        "id": RUN_ID,
        "planner_mode": "intelligent",
        "action_ids": [],
        "action_proposals": [proposal()],
        "tool_invocations": [{
            "tool": "social.draft",
            "state": "prepared",
            "consequential": False,
            "approval_required": False,
        }],
    }


def preview():
    value = {
        "version": 2,
        "provider": "linkedin",
        "connection_id": CONNECTION_ID,
        "account": "urn:li:person:member_123",
        "subject_id": "member_123",
        "payload": proposal()["payload"],
        "social_publishing": {
            "provider": "linkedin",
            "author": "connected_personal_member",
            "visibility": "public",
            "media": "none",
            "scheduling": "none",
            "social_read": "none",
            "agent_authority": "none",
        },
        "expires_at": "2026-09-25T12:00:00+00:00",
    }
    value["approval_scope"] = {
        "contract": "shuddho.consequential-action",
        "contract_version": 5,
        "provider": "linkedin",
        "capability": "social",
        "account": value["account"],
        "destinations": {},
        "policy": {"social_publishing": value["social_publishing"]},
    }
    return value


def test_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_LINKEDIN_AGENT_PROPOSALS",
        raising=False,
    )
    with pytest.raises(
        live.LinkedInAgentProposalValidationFailure,
        match="SHUDDHO_STAGING_ALLOW_LIVE_LINKEDIN_AGENT_PROPOSALS",
    ):
        live.require_guard()
    monkeypatch.setenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_LINKEDIN_AGENT_PROPOSALS",
        "true",
    )
    live.require_guard()


def test_inert_linkedin_proposal_binds_exact_hash_and_no_consequential_step():
    value = run_value()
    result = live.validate_inert_proposal(value, MARKER)
    assert result["id"] == PROPOSAL_ID

    value["tool_invocations"][0]["consequential"] = True
    with pytest.raises(
        live.LinkedInAgentProposalValidationFailure,
        match="consequential",
    ):
        live.validate_inert_proposal(value, MARKER)


def test_exact_promotion_stops_at_linkedin_approval_boundary():
    proposed = proposal()
    value = preview()
    action = {
        "id": ACTION_ID,
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": value,
        "preview_hash": digest(value),
    }
    calls = 0

    def respond(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(201, json=action)

    client = httpx.Client(
        base_url="https://staging.example.test",
        transport=httpx.MockTransport(respond),
    )
    result = live.promote_exact(
        client,
        "token",
        RUN_ID,
        proposed,
        {"id": CONNECTION_ID},
    )
    client.close()
    assert calls == 2
    assert result["state"] == "awaiting_approval"
    assert result["receipt"] is None
