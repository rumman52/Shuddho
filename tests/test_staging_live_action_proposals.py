from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

pytest.importorskip(
    "sqlalchemy",
    reason="Install the coworker extra for action-proposal staging tests",
)

from scripts import staging_live_action_proposals as live
from services.coworker.agent_schemas import action_proposal_hash


RUN_ID = "11111111-1111-1111-1111-111111111111"
PROPOSAL_ID = "22222222-2222-2222-2222-222222222222"
ACTION_ID = "33333333-3333-3333-3333-333333333333"
CONNECTION_ID = "44444444-4444-4444-4444-444444444444"
MARKER = "shuddho-proposal-testmarker"


def proposal():
    payload = {
        "kind": "email_send",
        "to": ["stage@example.com"],
        "cc": [],
        "bcc": [],
        "subject": f"Project update {MARKER}",
        "body": f"Synthetic staging body {MARKER}",
    }
    rationale = "The user explicitly requested this staging email."
    return {
        "id": PROPOSAL_ID,
        "kind": "email_send",
        "payload": payload,
        "rationale": rationale,
        "proposal_hash": action_proposal_hash(
            RUN_ID,
            payload,
            rationale,
        ),
        "state": "suggested",
        "promoted_action_id": None,
    }


def run_value():
    return {
        "id": RUN_ID,
        "planner_mode": "intelligent",
        "action_ids": [],
        "action_proposals": [proposal()],
        "tool_invocations": [
            {
                "tool": "email.draft",
                "state": "prepared",
                "consequential": False,
                "approval_required": False,
            }
        ],
    }


def test_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_ACTION_PROPOSALS",
        raising=False,
    )
    with pytest.raises(
        live.ActionProposalValidationFailure,
        match="SHUDDHO_STAGING_ALLOW_LIVE_ACTION_PROPOSALS",
    ):
        live.require_guard()

    monkeypatch.setenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_ACTION_PROPOSALS",
        "true",
    )
    live.require_guard()


def test_validate_inert_proposal_binds_exact_hash_and_no_action_step():
    value = run_value()
    result = live.validate_inert_proposal(
        value,
        "stage@example.com",
        MARKER,
    )
    assert result["id"] == PROPOSAL_ID

    value["action_ids"] = [ACTION_ID]
    with pytest.raises(
        live.ActionProposalValidationFailure,
        match="executable action bindings",
    ):
        live.validate_inert_proposal(
            value,
            "stage@example.com",
            MARKER,
        )


def test_reject_wrong_hash_keeps_proposal_suggested():
    current = run_value()

    def respond(request: httpx.Request):
        if request.method == "POST":
            return httpx.Response(
                409,
                json={
                    "error": {
                        "code": "proposal_changed",
                        "message": "Review again.",
                    }
                },
            )
        if request.method == "GET":
            return httpx.Response(200, json=current)
        return httpx.Response(404, json={})

    client = httpx.Client(
        base_url="https://staging.example.test",
        transport=httpx.MockTransport(respond),
    )
    live.reject_wrong_hash(
        client,
        "token",
        RUN_ID,
        proposal(),
        CONNECTION_ID,
    )
    client.close()


def test_validate_post_promotion_requires_unapproved_standalone_action():
    proposed = proposal()
    proposed["state"] = "promoted"
    proposed["promoted_action_id"] = ACTION_ID
    run = run_value()
    run["action_proposals"] = [proposed]

    preview = {
        "version": 2,
        "provider": "google",
        "connection_id": CONNECTION_ID,
        "account": "stage@example.com",
        "subject_id": "stage-subject",
        "payload": proposed["payload"],
        "approval_scope": {
            "provider": "google",
            "connection_id": CONNECTION_ID,
            "payload_sha256": "a" * 64,
        },
        "expires_at": "2026-09-23T12:00:00+00:00",
    }
    from services.coworker.action_repository import digest

    action = {
        "id": ACTION_ID,
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": digest(preview),
        "audit": [{"action": "action.prepared"}],
    }

    def respond(request: httpx.Request):
        if request.url.path == f"/api/v1/actions/{ACTION_ID}":
            return httpx.Response(200, json=action)
        if request.url.path == f"/api/v1/agent-runs/{RUN_ID}":
            return httpx.Response(200, json=run)
        if request.url.path == "/api/v1/actions":
            return httpx.Response(200, json={"actions": [action]})
        return httpx.Response(404, json={})

    client = httpx.Client(
        base_url="https://staging.example.test",
        transport=httpx.MockTransport(respond),
    )
    live.validate_post_promotion(
        client,
        "token",
        RUN_ID,
        proposed,
        action,
        MARKER,
    )

    run["action_ids"] = [ACTION_ID]
    with pytest.raises(
        live.ActionProposalValidationFailure,
        match="retrofitted an executable action",
    ):
        live.validate_post_promotion(
            client,
            "token",
            RUN_ID,
            proposed,
            action,
            MARKER,
        )
    client.close()


def test_merge_evidence_preserves_base_and_adds_timestamp(tmp_path):
    base = tmp_path / "base.json"
    base.write_text(
        json.dumps({
            "ci": {
                "status": "passed",
                "evidence": "ci",
            }
        }),
        encoding="utf-8",
    )
    record = live.passed("live inert action proposals")
    datetime.fromisoformat(record["verified_at"])
    merged = live.merge_evidence(
        base,
        {"action_proposals": record},
    )
    assert merged["ci"]["status"] == "passed"
    assert merged["action_proposals"]["status"] == "passed"
