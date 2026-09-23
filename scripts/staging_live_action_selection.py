from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_repository import digest
from services.coworker.action_schemas import address
from services.coworker.config import Settings


class ActionSelectionValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_SELECTION", "").lower() != "true":
        raise ActionSelectionValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_ACTION_SELECTION=true only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(response: httpx.Response, label: str, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise ActionSelectionValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise ActionSelectionValidationFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ActionSelectionValidationFailure(f"{label} returned an unexpected JSON shape.")
    return value


def connection_for(connections: list[dict], provider: str, capability: str) -> dict:
    matches = [
        item for item in connections
        if isinstance(item, dict)
        and item.get("provider") == provider
        and item.get("capability") == capability
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise ActionSelectionValidationFailure(
            f"Expected exactly one active {provider} {capability} staging connection; found {len(matches)}."
        )
    value = matches[0]
    if not isinstance(value.get("id"), str) or not isinstance(value.get("email"), str):
        raise ActionSelectionValidationFailure(
            f"{provider} {capability} connection metadata is incomplete."
        )
    return value


def prepare_action(
    client: httpx.Client,
    token: str,
    connection_id: str,
    payload: dict,
    key_prefix: str,
) -> dict:
    action = request_json(
        client.post(
            "/api/v1/actions",
            headers=auth(token) | {
                "Idempotency-Key": key_prefix + "-" + uuid.uuid4().hex,
            },
            json={
                "connection_id": connection_id,
                "payload": payload,
            },
        ),
        "prepare action-selection draft",
        expected=201,
    )
    if action.get("state") != "awaiting_approval":
        raise ActionSelectionValidationFailure(
            "A newly prepared action was not awaiting explicit approval."
        )
    if action.get("approved_at") is not None or action.get("receipt") is not None:
        raise ActionSelectionValidationFailure(
            "A newly prepared action already contained approval or receipt data."
        )
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview, dict) or not isinstance(preview_hash, str):
        raise ActionSelectionValidationFailure(
            "Prepared action is missing immutable preview data."
        )
    if digest(preview) != preview_hash:
        raise ActionSelectionValidationFailure(
            "Prepared action preview hash does not match its immutable preview."
        )
    if preview.get("payload") != payload:
        raise ActionSelectionValidationFailure(
            "Prepared action payload differs from the submitted synthetic payload."
        )
    return action


def create_agent_run(
    client: httpx.Client,
    token: str,
    email_action: dict,
    calendar_action: dict,
) -> dict:
    return request_json(
        client.post(
            "/api/v1/agent-runs",
            headers=auth(token) | {
                "Idempotency-Key": "live-action-selection-" + uuid.uuid4().hex,
            },
            json={
                "goal": (
                    "Use only the attached email action draft. "
                    "Do not select the attached calendar action draft. "
                    "Stop and wait for my explicit approval before any external action."
                ),
                "action_ids": [
                    email_action["id"],
                    calendar_action["id"],
                ],
                "output_language": "en",
            },
        ),
        "create action-selection Agent run",
        expected=202,
    )


def wait_for_approval_pause(
    client: httpx.Client,
    token: str,
    run_id: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    value: dict = {}
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/agent-runs/{run_id}", headers=auth(token)),
            "action-selection Agent run",
        )
        if value.get("state") == "awaiting_approval":
            return value
        if value.get("state") in {"failed", "cancelled", "completed"}:
            raise ActionSelectionValidationFailure(
                "Action-selection Agent run reached unexpected terminal state "
                f"{value.get('state')!r} before approval pause."
            )
        time.sleep(2)
    raise ActionSelectionValidationFailure(
        "Action-selection Agent run did not reach awaiting_approval before timeout."
    )


def validate_run(
    run: dict,
    email_action: dict,
    calendar_action: dict,
) -> None:
    if run.get("planner_mode") not in {"intelligent", "replanned"}:
        raise ActionSelectionValidationFailure(
            "Live action-selection probe did not use the intelligent planner."
        )
    if run.get("action_ids") != [email_action["id"]]:
        raise ActionSelectionValidationFailure(
            "The Agent run did not retain exactly the selected email action."
        )
    if calendar_action["id"] in run.get("action_ids", []):
        raise ActionSelectionValidationFailure(
            "The unselected calendar action remained bound to the Agent run."
        )

    invocations = run.get("tool_invocations")
    if not isinstance(invocations, list):
        raise ActionSelectionValidationFailure(
            "Agent run did not expose tool invocation metadata."
        )
    consequential = [
        item for item in invocations
        if isinstance(item, dict)
        and (
            item.get("consequential") is True
            or item.get("approval_required") is True
        )
    ]
    if len(consequential) != 1:
        raise ActionSelectionValidationFailure(
            "Expected exactly one consequential action-selection step."
        )
    selected = consequential[0]
    if selected.get("tool") != "email.send":
        raise ActionSelectionValidationFailure(
            "Planner selected an unexpected consequential tool."
        )
    if selected.get("state") != "awaiting_approval":
        raise ActionSelectionValidationFailure(
            "Selected email action did not pause for explicit approval."
        )


def validate_actions(
    client: httpx.Client,
    token: str,
    email_action: dict,
    calendar_action: dict,
) -> tuple[dict, dict]:
    email = request_json(
        client.get(
            f"/api/v1/actions/{email_action['id']}",
            headers=auth(token),
        ),
        "selected email action",
    )
    calendar = request_json(
        client.get(
            f"/api/v1/actions/{calendar_action['id']}",
            headers=auth(token),
        ),
        "released calendar action",
    )

    for label, action in (
        ("selected email", email),
        ("released calendar", calendar),
    ):
        if action.get("state") != "awaiting_approval":
            raise ActionSelectionValidationFailure(
                f"{label} action left awaiting_approval before user approval."
            )
        if action.get("approved_at") is not None or action.get("receipt") is not None:
            raise ActionSelectionValidationFailure(
                f"{label} action contains approval/provider receipt data."
            )

    email_audit = [
        item.get("action")
        for item in email.get("audit", [])
        if isinstance(item, dict)
    ]
    calendar_audit = [
        item.get("action")
        for item in calendar.get("audit", [])
        if isinstance(item, dict)
    ]
    if "action.approved" in email_audit or "action.execution_started" in email_audit:
        raise ActionSelectionValidationFailure(
            "Selected email action was approved or executed automatically."
        )
    if calendar_audit.count("action.released_unselected") != 1:
        raise ActionSelectionValidationFailure(
            "Unselected calendar draft was not released exactly once."
        )
    if "action.approved" in calendar_audit or "action.execution_started" in calendar_audit:
        raise ActionSelectionValidationFailure(
            "Unselected calendar action was approved or executed."
        )
    return email, calendar


def cleanup(
    client: httpx.Client,
    token: str,
    run_id: str | None,
    calendar_action_id: str | None,
) -> None:
    if run_id:
        try:
            client.post(
                f"/api/v1/agent-runs/{run_id}/cancel",
                headers=auth(token),
            )
        except httpx.HTTPError:
            pass
    if calendar_action_id:
        try:
            client.post(
                f"/api/v1/actions/{calendar_action_id}/cancel",
                headers=auth(token),
            )
        except httpx.HTTPError:
            pass


def merge_evidence(base_evidence: Path | None, update: dict) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ActionSelectionValidationFailure(
                "Base staging evidence must be a JSON object."
            )
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate live bounded Agent selection of attached action drafts "
            "without approving or executing an external action."
        )
    )
    parser.add_argument("--provider", choices=("google", "microsoft"), default="google")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if not settings.actions_enabled:
        raise SystemExit(
            "SHUDDHO_ACTIONS_ENABLED must be true in controlled staging."
        )
    if not settings.agent_runtime_enabled:
        raise SystemExit(
            "SHUDDHO_AGENT_RUNTIME_ENABLED must be true in controlled staging."
        )
    if not settings.intelligent_planner_enabled:
        raise SystemExit(
            "SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED must be true in controlled staging."
        )
    if not settings.agent_action_selection_enabled:
        raise SystemExit(
            "SHUDDHO_AGENT_ACTION_SELECTION_ENABLED must be true in controlled staging."
        )

    base_url = require_https_base(
        env_secret("SHUDDHO_STAGING_API_BASE_URL")
    )
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    marker = uuid.uuid4().hex[:10]
    run_id: str | None = None
    calendar_action_id: str | None = None

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=20,
            follow_redirects=False,
        ) as client:
            connections_value = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list staging connections",
            )
            if connections_value.get("enabled") is not True:
                raise ActionSelectionValidationFailure(
                    "Deployed action capability is not enabled."
                )
            connections = connections_value.get("connections")
            if not isinstance(connections, list):
                raise ActionSelectionValidationFailure(
                    "Connection list has an unexpected shape."
                )
            email_connection = connection_for(
                connections,
                args.provider,
                "email",
            )
            calendar_connection = connection_for(
                connections,
                args.provider,
                "calendar",
            )
            sender = address(str(email_connection["email"]))
            start = datetime.now(timezone.utc) + timedelta(minutes=30)
            end = start + timedelta(minutes=30)

            email_action = prepare_action(
                client,
                token,
                str(email_connection["id"]),
                {
                    "kind": "email_send",
                    "to": [sender],
                    "cc": [],
                    "bcc": [],
                    "subject": f"Shuddho action-selection staging {marker}",
                    "body": (
                        "Synthetic action-selection staging draft. "
                        "This must remain unapproved and unsent."
                    ),
                },
                "live-action-selection-email",
            )
            calendar_action = prepare_action(
                client,
                token,
                str(calendar_connection["id"]),
                {
                    "kind": "calendar_create",
                    "title": f"Shuddho unselected staging draft {marker}",
                    "description": (
                        "Synthetic unselected action-selection draft. "
                        "This event must never be created."
                    ),
                    "location": "Controlled staging",
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "time_zone": "UTC",
                    "attendees": [],
                },
                "live-action-selection-calendar",
            )
            calendar_action_id = str(calendar_action["id"])
            run = create_agent_run(
                client,
                token,
                email_action,
                calendar_action,
            )
            run_id = str(run["id"])
            paused = wait_for_approval_pause(
                client,
                token,
                run_id,
                args.timeout,
            )
            validate_run(paused, email_action, calendar_action)
            validate_actions(
                client,
                token,
                email_action,
                calendar_action,
            )

            evidence = merge_evidence(
                args.base_evidence,
                {
                    "action_selection": passed(
                        "live intelligent Agent selected only the attached email draft, "
                        "released the unselected calendar draft, and paused at explicit approval "
                        "with no provider execution or receipt"
                    )
                },
            )
            args.output.write_text(
                json.dumps(evidence, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({
                "written": str(args.output),
                "checks": {"action_selection": "passed"},
                "provider": args.provider,
                "cleanup": (
                    "Synthetic Agent run and drafts were cancelled after verification; "
                    "no action was approved or sent."
                ),
            }, indent=2))
    except (
        ActionSelectionValidationFailure,
        httpx.HTTPError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps({
            "status": "failed",
            "error": str(error),
        }, indent=2))
        raise SystemExit(1) from None
    finally:
        if "client" in locals():
            cleanup(
                client,
                token,
                run_id,
                calendar_action_id,
            )


if __name__ == "__main__":
    main()
