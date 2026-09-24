from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_repository import digest
from services.coworker.agent_schemas import action_proposal_hash
from services.coworker.config import Settings


class LinkedInAgentProposalValidationFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {
        "status": "passed",
        "evidence": evidence,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def require_guard() -> None:
    if (
        os.environ.get(
            "SHUDDHO_STAGING_ALLOW_LIVE_LINKEDIN_AGENT_PROPOSALS",
            "",
        ).lower()
        != "true"
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_LINKEDIN_AGENT_PROPOSALS=true "
            "only for the controlled staging exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(
    response: httpx.Response,
    label: str,
    expected: int = 200,
) -> dict:
    if response.status_code != expected:
        raise LinkedInAgentProposalValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise LinkedInAgentProposalValidationFailure(
            f"{label} did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise LinkedInAgentProposalValidationFailure(
            f"{label} returned an unexpected JSON shape."
        )
    return value


def connection_for(connections: list[dict]) -> dict:
    matches = [
        item
        for item in connections
        if isinstance(item, dict)
        and item.get("provider") == "linkedin"
        and item.get("capability") == "social"
        and item.get("active") is True
    ]
    if len(matches) != 1:
        raise LinkedInAgentProposalValidationFailure(
            "Expected exactly one active LinkedIn social staging "
            f"connection; found {len(matches)}."
        )
    value = matches[0]
    if (
        not isinstance(value.get("id"), str)
        or not isinstance(value.get("email"), str)
    ):
        raise LinkedInAgentProposalValidationFailure(
            "LinkedIn social connection metadata is incomplete."
        )
    return value


def list_actions(
    client: httpx.Client,
    token: str,
) -> list[dict]:
    value = request_json(
        client.get("/api/v1/actions", headers=auth(token)),
        "list staging actions",
    )
    actions = value.get("actions")
    if not isinstance(actions, list):
        raise LinkedInAgentProposalValidationFailure(
            "Action list has an unexpected shape."
        )
    return [item for item in actions if isinstance(item, dict)]


def action_has_marker(action: dict, marker: str) -> bool:
    preview = action.get("preview")
    payload = preview.get("payload") if isinstance(preview, dict) else None
    return (
        isinstance(payload, dict)
        and payload.get("kind") == "social_publish_linkedin"
        and isinstance(payload.get("text"), str)
        and marker in payload["text"]
    )


def matching_actions(
    actions: list[dict],
    marker: str,
) -> list[dict]:
    return [item for item in actions if action_has_marker(item, marker)]


def create_agent_run(
    client: httpx.Client,
    token: str,
    marker: str,
) -> dict:
    goal = (
        "Suggest exactly one inert personal LinkedIn public text-post action proposal. "
        "Do not approve, publish, execute, select any provider/account/member, use an "
        "organization page, add media, schedule, or perform engagement actions. "
        f"The exact proposed post text must include this marker: {marker}. "
        "Do not create email or calendar proposals or any second action proposal. "
        "The proposed action must remain inert until I explicitly promote it."
    )
    return request_json(
        client.post(
            "/api/v1/agent-runs",
            headers=auth(token)
            | {"Idempotency-Key": "live-linkedin-agent-proposals-" + uuid.uuid4().hex},
            json={"goal": goal, "output_language": "en"},
        ),
        "create LinkedIn Agent-proposal run",
        expected=202,
    )


def wait_for_proposal(
    client: httpx.Client,
    token: str,
    run_id: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + max(30, timeout_seconds)
    last: dict = {}
    while time.monotonic() < deadline:
        last = request_json(
            client.get(
                f"/api/v1/agent-runs/{run_id}",
                headers=auth(token),
            ),
            "action-proposal Agent run",
        )
        proposals = last.get("action_proposals")
        if (
            last.get("planner_mode") == "intelligent"
            and isinstance(proposals, list)
            and proposals
        ):
            return last
        if last.get("state") in {"failed", "cancelled"}:
            raise LinkedInAgentProposalValidationFailure(
                "Action-proposal Agent run reached unexpected terminal state "
                f"{last.get('state')!r} before producing a proposal."
            )
        if last.get("state") == "completed":
            raise LinkedInAgentProposalValidationFailure(
                "Action-proposal Agent run completed without a live "
                "intelligent proposal."
            )
        time.sleep(2)
    raise LinkedInAgentProposalValidationFailure(
        "Action-proposal Agent run did not produce a proposal before timeout."
    )


def validate_inert_proposal(run: dict, marker: str) -> dict:
    if run.get("planner_mode") != "intelligent":
        raise LinkedInAgentProposalValidationFailure(
            "Live LinkedIn proposal probe did not use the intelligent planner."
        )
    if run.get("action_ids") != []:
        raise LinkedInAgentProposalValidationFailure(
            "LinkedIn proposal Agent run unexpectedly contains executable action bindings."
        )
    proposals = run.get("action_proposals")
    if not isinstance(proposals, list) or len(proposals) != 1:
        raise LinkedInAgentProposalValidationFailure(
            "Expected exactly one live model-generated LinkedIn action proposal."
        )
    proposal = proposals[0]
    if not isinstance(proposal, dict):
        raise LinkedInAgentProposalValidationFailure("LinkedIn proposal has an unexpected shape.")
    if (
        proposal.get("kind") != "social_publish_linkedin"
        or proposal.get("state") != "suggested"
        or proposal.get("promoted_action_id") is not None
    ):
        raise LinkedInAgentProposalValidationFailure(
            "New LinkedIn proposal is not an inert suggested personal post."
        )
    payload = proposal.get("payload")
    rationale = proposal.get("rationale")
    proposal_hash = proposal.get("proposal_hash")
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "social_publish_linkedin"
        or not isinstance(payload.get("text"), str)
        or marker not in payload["text"]
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Model-generated LinkedIn proposal does not match the explicitly requested staging scope."
        )
    if not isinstance(rationale, str) or not rationale.strip():
        raise LinkedInAgentProposalValidationFailure("LinkedIn proposal rationale is missing.")
    if (
        not isinstance(proposal_hash, str)
        or action_proposal_hash(str(run["id"]), payload, rationale) != proposal_hash
    ):
        raise LinkedInAgentProposalValidationFailure(
            "LinkedIn proposal hash does not bind the exact run/payload/rationale."
        )
    for item in run.get("tool_invocations", []):
        if not isinstance(item, dict):
            raise LinkedInAgentProposalValidationFailure(
                "Agent invocation metadata has an unexpected shape."
            )
        if (
            item.get("consequential") is True
            or item.get("approval_required") is True
            or item.get("tool") == "social_publish_linkedin"
        ):
            raise LinkedInAgentProposalValidationFailure(
                "Inert LinkedIn proposal generation inserted consequential Agent authority."
            )
    return proposal


def wrong_hash(value: str) -> str:
    if (
        len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Action proposal hash is invalid."
        )
    first = "0" if value[0] != "0" else "1"
    return first + value[1:]


def proposal_from_run(
    run: dict,
    proposal_id: str,
) -> dict:
    proposals = run.get("action_proposals")
    if not isinstance(proposals, list):
        raise LinkedInAgentProposalValidationFailure(
            "Agent run has no proposal collection."
        )
    matches = [
        item for item in proposals
        if isinstance(item, dict)
        and item.get("id") == proposal_id
    ]
    if len(matches) != 1:
        raise LinkedInAgentProposalValidationFailure(
            "Expected exactly one owned proposal in the Agent run."
        )
    return matches[0]


def reject_wrong_hash(
    client: httpx.Client,
    token: str,
    run_id: str,
    proposal: dict,
    connection_id: str,
) -> None:
    rejected = client.post(
        (
            f"/api/v1/agent-runs/{run_id}/action-proposals/"
            f"{proposal['id']}/promote"
        ),
        headers=auth(token),
        json={
            "connection_id": connection_id,
            "proposal_hash": wrong_hash(str(proposal["proposal_hash"])),
        },
    )
    if rejected.status_code != 409:
        raise LinkedInAgentProposalValidationFailure(
            "Wrong-hash proposal promotion returned HTTP "
            f"{rejected.status_code}; expected 409."
        )
    current = request_json(
        client.get(
            f"/api/v1/agent-runs/{run_id}",
            headers=auth(token),
        ),
        "read proposal after wrong-hash rejection",
    )
    row = proposal_from_run(current, str(proposal["id"]))
    if (
        row.get("state") != "suggested"
        or row.get("promoted_action_id") is not None
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Rejected proposal promotion changed proposal state."
        )


def promote_exact(
    client: httpx.Client,
    token: str,
    run_id: str,
    proposal: dict,
    connection: dict,
) -> dict:
    path = (
        f"/api/v1/agent-runs/{run_id}/action-proposals/"
        f"{proposal['id']}/promote"
    )
    body = {
        "connection_id": connection["id"],
        "proposal_hash": proposal["proposal_hash"],
    }
    action = request_json(
        client.post(path, headers=auth(token), json=body),
        "promote exact action proposal",
        expected=201,
    )
    if (
        action.get("state") != "awaiting_approval"
        or action.get("approved_at") is not None
        or action.get("receipt") is not None
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Proposal promotion did not create an unapproved action preview."
        )
    preview = action.get("preview")
    preview_hash = action.get("preview_hash")
    if (
        not isinstance(preview, dict)
        or not isinstance(preview_hash, str)
        or digest(preview) != preview_hash
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Promoted action preview/hash is invalid."
        )
    if (
        preview.get("version") != 2
        or preview.get("provider") != "linkedin"
        or preview.get("connection_id") != connection["id"]
        or preview.get("payload") != proposal["payload"]
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Promoted preview does not bind the user-selected connection and "
            "exact proposal payload."
        )
    scope = preview.get("approval_scope")
    if (
        not isinstance(scope, dict)
        or scope.get("contract") != "shuddho.consequential-action"
        or scope.get("contract_version") != 5
        or scope.get("provider") != "linkedin"
        or scope.get("capability") != "social"
        or scope.get("account") != preview.get("account")
        or scope.get("destinations") != {}
        or scope.get("policy", {}).get("social_publishing")
        != preview.get("social_publishing")
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Promoted preview is missing its server-owned approval scope."
        )

    if (
        not isinstance(preview.get("account"), str)
        or not preview["account"].startswith("urn:li:person:")
        or preview.get("social_publishing") != {
            "provider": "linkedin",
            "author": "connected_personal_member",
            "visibility": "public",
            "media": "none",
            "scheduling": "none",
            "social_read": "none",
            "agent_authority": "none",
        }
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Promoted LinkedIn preview exceeds the bounded personal-text authority."
        )

    replay = request_json(
        client.post(path, headers=auth(token), json=body),
        "replay exact proposal promotion",
        expected=201,
    )
    if (
        replay.get("id") != action.get("id")
        or replay.get("preview_hash") != preview_hash
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Exact promotion replay did not return the same immutable preview."
        )
    return action


def validate_post_promotion(
    client: httpx.Client,
    token: str,
    run_id: str,
    proposal: dict,
    action: dict,
    marker: str,
) -> None:
    time.sleep(2)
    current_action = request_json(
        client.get(
            f"/api/v1/actions/{action['id']}",
            headers=auth(token),
        ),
        "read promoted unapproved action",
    )
    if (
        current_action.get("state") != "awaiting_approval"
        or current_action.get("approved_at") is not None
        or current_action.get("receipt") is not None
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Promoted action changed state before explicit approval."
        )
    audit = [
        item.get("action")
        for item in current_action.get("audit", [])
        if isinstance(item, dict)
    ]
    if audit.count("action.prepared") != 1:
        raise LinkedInAgentProposalValidationFailure(
            "Promoted action does not have exactly one preparation audit event."
        )
    if (
        "action.approved" in audit
        or "action.execution_started" in audit
        or "action.succeeded" in audit
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Promoted action was approved or executed automatically."
        )

    current_run = request_json(
        client.get(
            f"/api/v1/agent-runs/{run_id}",
            headers=auth(token),
        ),
        "read Agent run after proposal promotion",
    )
    row = proposal_from_run(current_run, str(proposal["id"]))
    if (
        row.get("state") != "promoted"
        or row.get("promoted_action_id") != action["id"]
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Agent run does not record the exact promoted standalone action."
        )
    if current_run.get("action_ids") != []:
        raise LinkedInAgentProposalValidationFailure(
            "Proposal promotion retrofitted an executable action into the "
            "saved Agent plan."
        )
    for item in current_run.get("tool_invocations", []):
        if isinstance(item, dict) and (
            item.get("consequential") is True
            or item.get("approval_required") is True
            or item.get("tool") == "social_publish_linkedin"
        ):
            raise LinkedInAgentProposalValidationFailure(
                "Proposal promotion inserted a consequential Agent invocation."
            )

    matches = matching_actions(
        list_actions(client, token),
        marker,
    )
    if (
        len(matches) != 1
        or matches[0].get("id") != action["id"]
    ):
        raise LinkedInAgentProposalValidationFailure(
            "Expected exactly one matching standalone action after promotion."
        )


def cleanup(
    client: httpx.Client,
    token: str,
    run_id: str | None,
    proposal: dict | None,
    action_id: str | None,
) -> None:
    if action_id:
        try:
            client.post(
                f"/api/v1/actions/{action_id}/cancel",
                headers=auth(token),
            )
        except httpx.HTTPError:
            pass
    if proposal and run_id and not action_id:
        try:
            client.post(
                (
                    f"/api/v1/agent-runs/{run_id}/action-proposals/"
                    f"{proposal['id']}/dismiss"
                ),
                headers=auth(token),
                json={"proposal_hash": proposal["proposal_hash"]},
            )
        except httpx.HTTPError:
            pass
    if run_id:
        try:
            client.post(
                f"/api/v1/agent-runs/{run_id}/cancel",
                headers=auth(token),
            )
        except httpx.HTTPError:
            pass


def merge_evidence(
    base_evidence: Path | None,
    update: dict,
) -> dict:
    base = {}
    if base_evidence:
        value = json.loads(
            base_evidence.read_text(encoding="utf-8")
        )
        if not isinstance(value, dict):
            raise LinkedInAgentProposalValidationFailure(
                "Base staging evidence must be a JSON object."
            )
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate live model-generated LinkedIn Agent proposals remain inert "
            "until explicit user promotion, and promotion still stops at the "
            "normal approval boundary."
        )
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    required = (
        ("SHUDDHO_WORK_SERVICES_ENABLED", settings.work_services_enabled),
        ("SHUDDHO_ACTIONS_ENABLED", settings.actions_enabled),
        ("SHUDDHO_AGENT_RUNTIME_ENABLED", settings.agent_runtime_enabled),
        (
            "SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED",
            settings.intelligent_planner_enabled,
        ),
        (
            "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED",
            settings.agent_action_proposals_enabled,
        ),
        (
            "SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED",
            settings.agent_linkedin_proposals_enabled,
        ),
        (
            "SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED",
            settings.action_social_publishing_enabled,
        ),
    )
    for name, enabled in required:
        if not enabled:
            raise SystemExit(
                f"{name} must be true in controlled staging."
            )

    base_url = require_https_base(
        env_secret("SHUDDHO_STAGING_API_BASE_URL")
    )
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    marker = "shuddho-linkedin-proposal-" + uuid.uuid4().hex[:12]

    run_id: str | None = None
    proposal: dict | None = None
    action_id: str | None = None

    client = httpx.Client(
        base_url=base_url,
        timeout=20,
        follow_redirects=False,
    )
    try:
        connections_value = request_json(
            client.get(
                "/api/v1/connections",
                headers=auth(token),
            ),
            "list staging connections",
        )
        if connections_value.get("enabled") is not True:
            raise LinkedInAgentProposalValidationFailure(
                "Deployed action capability is not enabled."
            )
        connections = connections_value.get("connections")
        if not isinstance(connections, list):
            raise LinkedInAgentProposalValidationFailure(
                "Connection list has an unexpected shape."
            )
        connection = connection_for(connections)

        if matching_actions(
            list_actions(client, token),
            marker,
        ):
            raise LinkedInAgentProposalValidationFailure(
                "Unique staging marker already exists in external actions."
            )

        run = create_agent_run(client, token, marker)
        run_id = str(run["id"])
        planned = wait_for_proposal(
            client,
            token,
            run_id,
            args.timeout,
        )
        proposal = validate_inert_proposal(planned, marker)

        if matching_actions(
            list_actions(client, token),
            marker,
        ):
            raise LinkedInAgentProposalValidationFailure(
                "Model proposal created an external action before promotion."
            )

        reject_wrong_hash(
            client,
            token,
            run_id,
            proposal,
            str(connection["id"]),
        )

        action = promote_exact(
            client,
            token,
            run_id,
            proposal,
            connection,
        )
        action_id = str(action["id"])
        validate_post_promotion(
            client,
            token,
            run_id,
            proposal,
            action,
            marker,
        )

        evidence = merge_evidence(
            args.base_evidence,
            {
                "agent_linkedin_proposals": passed(
                    "live intelligent Agent produced one inert personal LinkedIn text "
                    "proposal with no matching external action; no provider/account/member "
                    "was model-selected; wrong-hash promotion was rejected; exact user-selected "
                    "LinkedIn social connection promotion created exactly one standalone immutable "
                    "awaiting_approval preview; saved Agent plan remained non-consequential; "
                    "no approval, execution audit, provider request, or LinkedIn receipt occurred"
                )
            },
        )
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "written": str(args.output),
            "checks": {"agent_linkedin_proposals": "passed"},
            "provider": "linkedin",
            "run_id": run_id,
            "proposal_id": proposal["id"],
            "action_id": action_id,
            "cleanup": (
                "The promoted synthetic preview and Agent run are cancelled "
                "after verification. No action is approved or executed."
            ),
        }, indent=2))
    except (
        LinkedInAgentProposalValidationFailure,
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
        cleanup(
            client,
            token,
            run_id,
            proposal,
            action_id,
        )
        client.close()


if __name__ == "__main__":
    main()
