from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

pytest.importorskip(
    "sqlalchemy",
    reason="Install the coworker extra for action-selection staging tests",
)

from scripts import staging_live_action_selection as live


def action(action_id: str, kind: str) -> dict:
    return {
        "id": action_id,
        "kind": kind,
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": {"payload": {"kind": kind}},
        "preview_hash": "a" * 64,
    }


def test_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_ACTION_SELECTION",
        raising=False,
    )
    with pytest.raises(
        live.ActionSelectionValidationFailure,
        match="SHUDDHO_STAGING_ALLOW_LIVE_ACTION_SELECTION",
    ):
        live.require_guard()

    monkeypatch.setenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_ACTION_SELECTION",
        "true",
    )
    live.require_guard()


def test_connection_for_is_provider_and_capability_specific():
    connections = [
        {
            "id": "g-email",
            "provider": "google",
            "capability": "email",
            "active": True,
            "email": "stage@example.com",
        },
        {
            "id": "g-calendar",
            "provider": "google",
            "capability": "calendar",
            "active": True,
            "email": "stage@example.com",
        },
        {
            "id": "m-email",
            "provider": "microsoft",
            "capability": "email",
            "active": True,
            "email": "stage@example.com",
        },
    ]
    assert live.connection_for(
        connections,
        "google",
        "email",
    )["id"] == "g-email"
    with pytest.raises(
        live.ActionSelectionValidationFailure,
        match="exactly one active",
    ):
        live.connection_for(
            connections,
            "microsoft",
            "calendar",
        )


def test_validate_run_requires_one_selected_email_and_approval_pause():
    email = action(
        "11111111-1111-1111-1111-111111111111",
        "email_send",
    )
    calendar = action(
        "22222222-2222-2222-2222-222222222222",
        "calendar_create",
    )
    run = {
        "planner_mode": "intelligent",
        "action_ids": [email["id"]],
        "tool_invocations": [
            {
                "tool": "email.send",
                "state": "awaiting_approval",
                "consequential": True,
                "approval_required": True,
            }
        ],
    }
    live.validate_run(run, email, calendar)

    run["tool_invocations"][0]["tool"] = "calendar.create"
    with pytest.raises(
        live.ActionSelectionValidationFailure,
        match="unexpected consequential tool",
    ):
        live.validate_run(run, email, calendar)


def test_validate_actions_requires_release_audit_and_no_approval():
    email_id = "11111111-1111-1111-1111-111111111111"
    calendar_id = "22222222-2222-2222-2222-222222222222"
    email = {
        "id": email_id,
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "audit": [{"action": "action.prepared"}],
    }
    calendar = {
        "id": calendar_id,
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.released_unselected"},
        ],
    }

    def respond(request: httpx.Request):
        if request.url.path.endswith(email_id):
            return httpx.Response(200, json=email)
        if request.url.path.endswith(calendar_id):
            return httpx.Response(200, json=calendar)
        return httpx.Response(404, json={})

    client = httpx.Client(
        base_url="https://staging.example.test",
        transport=httpx.MockTransport(respond),
    )
    live.validate_actions(
        client,
        "token",
        {"id": email_id},
        {"id": calendar_id},
    )

    calendar["audit"].append({"action": "action.approved"})
    with pytest.raises(
        live.ActionSelectionValidationFailure,
        match="approved or executed",
    ):
        live.validate_actions(
            client,
            "token",
            {"id": email_id},
            {"id": calendar_id},
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
    record = live.passed("live action selection")
    datetime.fromisoformat(record["verified_at"])
    merged = live.merge_evidence(
        base,
        {"action_selection": record},
    )
    assert merged["ci"]["status"] == "passed"
    assert merged["action_selection"]["status"] == "passed"
