from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.action_registry import stable_digest
from services.coworker.config import Settings


class NegotiationProposalPromotionValidationFailure(RuntimeError):
    pass


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def proposal_digest(proposal: dict) -> str:
    required = {
        "id",
        "case_id",
        "case_revision",
        "history_sequence",
        "kind",
        "output_language",
        "summary",
        "terms",
        "message",
        "rationale",
        "risk_notes",
    }
    if any(key not in proposal for key in required):
        raise NegotiationProposalPromotionValidationFailure(
            "Negotiation proposal is missing hash-bound fields."
        )
    draft = {
        "summary": proposal["summary"],
        "terms": proposal["terms"],
        "message": proposal["message"],
        "rationale": proposal["rationale"],
        "risk_notes": proposal["risk_notes"],
    }
    return digest({
        "schema_version": 1,
        "case_id": proposal["case_id"],
        "case_revision": proposal["case_revision"],
        "history_sequence": proposal["history_sequence"],
        "kind": proposal["kind"],
        "output_language": proposal["output_language"],
        "draft": draft,
    })


def passed(
    evidence: str,
    operation: str,
    existing: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    operation_evidence: dict[str, dict[str, str]] = {}
    if isinstance(existing, dict):
        prior = existing.get("operation_evidence")
        if isinstance(prior, dict):
            for key, value in prior.items():
                if (
                    isinstance(key, str)
                    and isinstance(value, dict)
                    and isinstance(value.get("evidence"), str)
                    and value["evidence"].strip()
                    and isinstance(value.get("verified_at"), str)
                ):
                    operation_evidence[key] = {
                        "evidence": value["evidence"],
                        "verified_at": value["verified_at"],
                    }
    operation_evidence[operation] = {
        "evidence": evidence,
        "verified_at": now,
    }
    return {
        "status": "passed",
        "evidence": "qualified negotiation proposal promotion operations: "
        + ", ".join(sorted(operation_evidence)),
        "verified_at": now,
        "operation_evidence": {
            key: operation_evidence[key]
            for key in sorted(operation_evidence)
        },
    }


def require_guard() -> None:
    if (
        os.environ.get(
            "SHUDDHO_STAGING_ALLOW_LIVE_NEGOTIATION_PROPOSAL_PROMOTION",
            "",
        ).lower()
        != "true"
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_NEGOTIATION_PROPOSAL_PROMOTION=true "
            "only for the dedicated controlled-staging promotion exercise."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(
    response: httpx.Response,
    label: str,
    expected: int = 200,
) -> dict:
    if response.status_code != expected:
        raise NegotiationProposalPromotionValidationFailure(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise NegotiationProposalPromotionValidationFailure(
            f"{label} did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise NegotiationProposalPromotionValidationFailure(
            f"{label} returned an unexpected JSON shape."
        )
    return value


def wrong_hash(value: str) -> str:
    if (
        len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Negotiation proposal hash is invalid."
        )
    return ("0" if value[0] != "0" else "1") + value[1:]


def validate_transaction_authority(value: dict, provider: str) -> str:
    operation = f"{provider}:negotiation_commitment_email"
    if (
        value.get("schema_version") not in {1, 2}
        or value.get("personal_transactions_enabled") is not True
        or not isinstance(value.get("operations"), list)
        or operation not in value["operations"]
    ):
        raise NegotiationProposalPromotionValidationFailure(
            f"Deployed PA-09 transaction authority does not allow {operation}."
        )
    return operation


def connection_for(connections: list[dict], provider: str) -> dict:
    matches = [
        item
        for item in connections
        if isinstance(item, dict)
        and item.get("active") is True
        and item.get("provider") == provider
        and item.get("capability") == "email"
        and isinstance(item.get("id"), str)
        and isinstance(item.get("email"), str)
    ]
    if len(matches) != 1:
        raise NegotiationProposalPromotionValidationFailure(
            f"Expected exactly one active {provider} email connection for controlled staging; "
            f"found {len(matches)}."
        )
    return matches[0]


def case_payload(
    connection_id: str,
    counterparty: str,
    marker: str,
) -> dict:
    return {
        "connection_id": connection_id,
        "counterparty_name": "Shuddho controlled staging mailbox",
        "counterparty_address": counterparty,
        "subject": f"Shuddho PA-09 promotion staging {marker}",
        "objective": (
            "Prepare a synthetic nonbinding counteroffer for controlled staging only. "
            "Preserve every exact user limit as an explicit proposed term. "
            "Do not claim agreement, delivery, payment, booking, savings, legal effect, "
            "provider execution or counterparty acceptance."
        ),
        "limits": [
            {
                "name": "TestReference",
                "comparison": "exact",
                "value": marker,
            },
            {
                "name": "Amount",
                "comparison": "exact",
                "value": "USD 0.00 synthetic",
            },
            {
                "name": "Effect",
                "comparison": "exact",
                "value": "Controlled staging validation only",
            },
        ],
    }


def expected_term_map(marker: str) -> dict[str, str]:
    return {
        "testreference": marker,
        "amount": "USD 0.00 synthetic",
        "effect": "Controlled staging validation only",
    }


def validate_proposal(
    proposal: dict,
    case: dict,
    *,
    history_sequence: int,
    marker: str,
) -> None:
    if (
        proposal.get("state") != "suggested"
        or proposal.get("case_id") != case.get("id")
        or proposal.get("case_revision") != case.get("revision")
        or proposal.get("history_sequence") != history_sequence
        or proposal.get("kind") != "counteroffer"
        or proposal.get("output_language") != "en"
        or proposal.get("promoted_action_id") is not None
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Generated proposal is not bound to the expected case revision/history."
        )
    proposal_hash = proposal.get("proposal_hash")
    if (
        not isinstance(proposal_hash, str)
        or proposal_hash != proposal_digest(proposal)
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Generated proposal hash does not bind the exact stored draft."
        )
    terms = proposal.get("terms")
    if not isinstance(terms, list) or not terms:
        raise NegotiationProposalPromotionValidationFailure(
            "Generated proposal has no explicit terms to promote."
        )
    actual: dict[str, str] = {}
    for item in terms:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("value"), str)
        ):
            raise NegotiationProposalPromotionValidationFailure(
                "Generated proposal terms have an unexpected shape."
            )
        actual[item["name"].casefold()] = item["value"]
    for name, value in expected_term_map(marker).items():
        if actual.get(name) != value:
            raise NegotiationProposalPromotionValidationFailure(
                f"Generated proposal did not preserve exact staging term {name}."
            )


def proposal_from_case(case: dict, proposal_id: str) -> dict:
    proposals = case.get("proposals")
    if not isinstance(proposals, list):
        raise NegotiationProposalPromotionValidationFailure(
            "Negotiation case has no proposal collection."
        )
    matches = [
        item
        for item in proposals
        if isinstance(item, dict) and item.get("id") == proposal_id
    ]
    if len(matches) != 1:
        raise NegotiationProposalPromotionValidationFailure(
            "Expected exactly one proposal with the requested ID."
        )
    return matches[0]


def matching_actions(
    actions: list[dict],
    proposal_id: str,
) -> list[dict]:
    result = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        preview = item.get("preview")
        binding = preview.get("source_binding") if isinstance(preview, dict) else None
        if isinstance(binding, dict) and binding.get("proposal_id") == proposal_id:
            result.append(item)
    return result


def validate_promoted_action(
    action: dict,
    case: dict,
    proposal: dict,
    connection: dict,
) -> None:
    if (
        action.get("state") != "awaiting_approval"
        or action.get("approved_at") is not None
        or action.get("receipt") is not None
        or action.get("connection_id") != connection.get("id")
        or action.get("kind") != "negotiation_commitment_email"
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Exact promotion did not create one unapproved negotiation action."
        )
    preview = action.get("preview")
    if not isinstance(preview, dict):
        raise NegotiationProposalPromotionValidationFailure(
            "Promoted action has no immutable preview."
        )
    expected_binding = {
        "type": "negotiation_proposal",
        "proposal_id": proposal["id"],
        "proposal_hash": proposal["proposal_hash"],
        "case_id": case["id"],
        "case_revision": proposal["case_revision"],
        "history_sequence": proposal["history_sequence"],
    }
    expected_payload = {
        "kind": "negotiation_commitment_email",
        "to": [case["counterparty_address"]],
        "cc": [],
        "bcc": [],
        "subject": case["subject"],
        "body": proposal["message"],
        "counterparty": case["counterparty_name"],
        "commitment_summary": proposal["summary"],
        "terms": proposal["terms"],
    }
    if (
        preview.get("version") != 6
        or preview.get("provider") != connection.get("provider")
        or preview.get("connection_id") != connection.get("id")
        or preview.get("source_binding") != expected_binding
        or preview.get("payload") != expected_payload
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Promoted action preview does not exactly bind proposal/case/provider state."
        )
    if action.get("preview_hash") != digest(preview):
        raise NegotiationProposalPromotionValidationFailure(
            "Promoted action preview hash is invalid."
        )
    approval_scope = preview.get("approval_scope")
    if (
        not isinstance(approval_scope, dict)
        or approval_scope.get("contract") != "shuddho.consequential-action"
        or approval_scope.get("contract_version") != 6
        or approval_scope.get("action_kind") != "negotiation_commitment_email"
        or approval_scope.get("source_binding") != expected_binding
        or approval_scope.get("source_binding_sha256") != stable_digest(expected_binding)
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Approval scope does not bind the exact negotiation proposal source."
        )


def validate_unexecuted(action: dict) -> None:
    audit = [
        item.get("action")
        for item in action.get("audit", [])
        if isinstance(item, dict)
    ]
    if (
        action.get("state") != "awaiting_approval"
        or action.get("approved_at") is not None
        or action.get("receipt") is not None
        or audit.count("action.prepared") != 1
        or "action.approved" in audit
        or "action.execution_started" in audit
        or "action.succeeded" in audit
    ):
        raise NegotiationProposalPromotionValidationFailure(
            "Stale-source denial did not preserve the no-provider-mutation boundary."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate exact-hash PA-09 negotiation proposal promotion through "
            "the deployed public staging API without executing a provider mutation."
        )
    )
    parser.add_argument(
        "--provider",
        choices=("google", "microsoft"),
        default="google",
    )
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_guard()
    settings = Settings.from_env()
    if (
        not settings.actions_enabled
        or not settings.connector_trust_boundary_enabled
        or not settings.personal_transactions_enabled
        or not settings.agent_runtime_enabled
        or not settings.intelligent_planner_enabled
        or not settings.agent_action_proposals_enabled
        or not settings.negotiation_proposal_promotion_enabled
        or not settings.deepseek_api_key
    ):
        raise SystemExit(
            "Controlled staging requires actions, connector trust boundary, "
            "personal transactions, Agent runtime, intelligent planner, action "
            "proposals, negotiation proposal promotion and a configured DeepSeek key."
        )
    if args.provider == "microsoft" and not settings.microsoft_actions_enabled:
        raise SystemExit(
            "Microsoft actions must be enabled for the Microsoft promotion probe."
        )
    operation = f"{args.provider}:negotiation_commitment_email"
    if operation not in settings.transaction_operations:
        raise SystemExit(
            "Controlled staging requires the exact provider negotiation operation "
            "in SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS."
        )

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    counterparty = env_secret(
        "SHUDDHO_STAGING_TRANSACTION_COUNTERPARTY_EMAIL"
    )
    marker = uuid.uuid4().hex[:12]
    case_id: str | None = None
    action_id: str | None = None

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=30,
            follow_redirects=False,
        ) as client:
            authority = request_json(
                client.get(
                    "/api/v1/transaction-authority-manifest",
                    headers=auth(token),
                ),
                "read transaction authority manifest",
            )
            validate_transaction_authority(authority, args.provider)

            listed = request_json(
                client.get("/api/v1/connections", headers=auth(token)),
                "list staging connections",
            )
            connections = listed.get("connections")
            if not isinstance(connections, list):
                raise NegotiationProposalPromotionValidationFailure(
                    "Connection list has an unexpected shape."
                )
            connection = connection_for(connections, args.provider)

            capability = request_json(
                client.get("/api/v1/negotiations", headers=auth(token)),
                "read negotiation capability",
            )
            if (
                capability.get("enabled") is not True
                or capability.get("proposals_enabled") is not True
                or capability.get("proposal_promotion_enabled") is not True
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Deployed negotiation proposal promotion capability is not enabled."
                )

            case = request_json(
                client.post(
                    "/api/v1/negotiations",
                    headers=auth(token)
                    | {
                        "Idempotency-Key":
                        "live-negotiation-promotion-case-" + uuid.uuid4().hex
                    },
                    json=case_payload(
                        str(connection["id"]),
                        counterparty,
                        marker,
                    ),
                ),
                "create controlled-staging negotiation case",
                expected=201,
            )
            case_id = str(case["id"])
            if (
                case.get("provider") != args.provider
                or case.get("connection_id") != connection.get("id")
                or case.get("counterparty_address") != counterparty
                or case.get("state") != "active"
                or case.get("revision") != 1
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Created negotiation case does not match the selected staging scope."
                )

            first = request_json(
                client.post(
                    f"/api/v1/negotiations/{case_id}/proposals",
                    headers=auth(token)
                    | {
                        "Idempotency-Key":
                        "live-negotiation-promotion-proposal-" + uuid.uuid4().hex
                    },
                    json={
                        "expected_revision": case["revision"],
                        "kind": "counteroffer",
                        "output_language": "en",
                    },
                ),
                "generate history-bound negotiation proposal",
                expected=201,
            )
            validate_proposal(
                first,
                case,
                history_sequence=0,
                marker=marker,
            )

            actions_before = request_json(
                client.get("/api/v1/actions", headers=auth(token)),
                "list actions before promotion",
            ).get("actions")
            if (
                not isinstance(actions_before, list)
                or matching_actions(actions_before, str(first["id"]))
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Generated proposal unexpectedly created an ExternalAction."
                )

            request_json(
                client.post(
                    f"/api/v1/negotiations/{case_id}/offers",
                    headers=auth(token)
                    | {
                        "Idempotency-Key":
                        "live-negotiation-promotion-history-" + uuid.uuid4().hex
                    },
                    json={
                        "direction": "theirs",
                        "kind": "response",
                        "summary": "Synthetic history change before promotion.",
                        "terms": [
                            {
                                "name": "HistoryReference",
                                "value": marker,
                            }
                        ],
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    },
                ),
                "append synthetic history change",
                expected=201,
            )
            stale = client.post(
                (
                    f"/api/v1/negotiations/{case_id}/proposals/"
                    f"{first['id']}/promote"
                ),
                headers=auth(token),
                json={"proposal_hash": first["proposal_hash"]},
            )
            if stale.status_code != 409:
                raise NegotiationProposalPromotionValidationFailure(
                    "History-stale proposal promotion was not rejected."
                )

            current_case = request_json(
                client.get(
                    f"/api/v1/negotiations/{case_id}",
                    headers=auth(token),
                ),
                "read case after history change",
            )
            stale_saved = proposal_from_case(
                current_case,
                str(first["id"]),
            )
            if stale_saved.get("state") != "stale":
                raise NegotiationProposalPromotionValidationFailure(
                    "History-bound proposal was not rendered stale after history changed."
                )

            fresh = request_json(
                client.post(
                    f"/api/v1/negotiations/{case_id}/proposals",
                    headers=auth(token)
                    | {
                        "Idempotency-Key":
                        "live-negotiation-promotion-fresh-" + uuid.uuid4().hex
                    },
                    json={
                        "expected_revision": current_case["revision"],
                        "kind": "counteroffer",
                        "output_language": "en",
                    },
                ),
                "generate fresh negotiation proposal",
                expected=201,
            )
            validate_proposal(
                fresh,
                current_case,
                history_sequence=1,
                marker=marker,
            )

            wrong = client.post(
                (
                    f"/api/v1/negotiations/{case_id}/proposals/"
                    f"{fresh['id']}/promote"
                ),
                headers=auth(token),
                json={
                    "proposal_hash": wrong_hash(
                        str(fresh["proposal_hash"])
                    )
                },
            )
            if wrong.status_code != 409:
                raise NegotiationProposalPromotionValidationFailure(
                    "Wrong-hash negotiation proposal promotion was not rejected."
                )
            unchanged = request_json(
                client.get(
                    f"/api/v1/negotiations/{case_id}",
                    headers=auth(token),
                ),
                "read proposal after wrong-hash denial",
            )
            wrong_saved = proposal_from_case(
                unchanged,
                str(fresh["id"]),
            )
            if (
                wrong_saved.get("state") != "suggested"
                or wrong_saved.get("promoted_action_id") is not None
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Wrong-hash denial changed proposal state."
                )

            promoted = request_json(
                client.post(
                    (
                        f"/api/v1/negotiations/{case_id}/proposals/"
                        f"{fresh['id']}/promote"
                    ),
                    headers=auth(token),
                    json={"proposal_hash": fresh["proposal_hash"]},
                ),
                "promote exact negotiation proposal",
            )
            action_id = str(promoted["id"])
            validate_promoted_action(
                promoted,
                current_case,
                fresh,
                connection,
            )

            replay = request_json(
                client.post(
                    (
                        f"/api/v1/negotiations/{case_id}/proposals/"
                        f"{fresh['id']}/promote"
                    ),
                    headers=auth(token),
                    json={"proposal_hash": fresh["proposal_hash"]},
                ),
                "replay exact negotiation proposal promotion",
            )
            if (
                replay.get("id") != promoted.get("id")
                or replay.get("preview_hash") != promoted.get("preview_hash")
                or replay.get("preview") != promoted.get("preview")
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Exact promotion replay did not converge on one immutable preview."
                )

            promoted_case = request_json(
                client.get(
                    f"/api/v1/negotiations/{case_id}",
                    headers=auth(token),
                ),
                "read case after exact promotion",
            )
            saved = proposal_from_case(
                promoted_case,
                str(fresh["id"]),
            )
            if (
                saved.get("state") != "promoted"
                or saved.get("promoted_action_id") != action_id
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Proposal did not persist the exact promoted action link."
                )

            actions_after = request_json(
                client.get("/api/v1/actions", headers=auth(token)),
                "list actions after promotion",
            ).get("actions")
            if (
                not isinstance(actions_after, list)
                or len(matching_actions(actions_after, str(fresh["id"]))) != 1
            ):
                raise NegotiationProposalPromotionValidationFailure(
                    "Exact promotion did not create exactly one source-bound ExternalAction."
                )

            changed_case = request_json(
                client.patch(
                    f"/api/v1/negotiations/{case_id}",
                    headers=auth(token),
                    json={
                        "expected_revision": promoted_case["revision"],
                        "objective": (
                            promoted_case["objective"]
                            + " Synthetic post-promotion revision change "
                            + marker
                        ),
                    },
                ),
                "change case revision after promotion",
            )
            if changed_case.get("revision") != promoted_case["revision"] + 1:
                raise NegotiationProposalPromotionValidationFailure(
                    "Post-promotion case update did not advance the revision."
                )

            denied = client.post(
                f"/api/v1/actions/{action_id}/approve",
                headers=auth(token),
                json={"preview_hash": promoted["preview_hash"]},
            )
            if denied.status_code != 409:
                raise NegotiationProposalPromotionValidationFailure(
                    "Case-revision change did not invalidate exact action approval."
                )

            still_inert = request_json(
                client.get(
                    f"/api/v1/actions/{action_id}",
                    headers=auth(token),
                ),
                "read stale promoted action",
            )
            validate_unexecuted(still_inert)

            evidence: dict = {}
            if args.base_evidence:
                loaded = json.loads(
                    args.base_evidence.read_text(encoding="utf-8")
                )
                if not isinstance(loaded, dict):
                    raise NegotiationProposalPromotionValidationFailure(
                        "Base evidence must be a JSON object."
                    )
                evidence.update(loaded)
            evidence["negotiation_proposal_promotion"] = passed(
                (
                    f"live {args.provider} PA-09 proposal promotion passed canonical "
                    "proposal hashing, offer-history stale denial, wrong-hash denial, "
                    "server-built proposal/case/source-bound immutable preview creation, "
                    "idempotent replay, case-revision approval invalidation and zero "
                    "provider mutation before approval"
                ),
                operation,
                evidence.get("negotiation_proposal_promotion"),
            )
            args.output.write_text(
                json.dumps(evidence, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({
                "written": str(args.output),
                "status": "passed",
                "feature": "negotiation_proposal_promotion",
                "provider": args.provider,
                "case_id": case_id,
                "proposal_id": fresh["id"],
                "action_id": action_id,
            }, indent=2))
    except (
        NegotiationProposalPromotionValidationFailure,
        httpx.HTTPError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps(
            {"status": "failed", "error": str(error)},
            indent=2,
        ))
        raise SystemExit(1) from None
    finally:
        if case_id is not None:
            try:
                with httpx.Client(
                    base_url=base_url,
                    timeout=10,
                    follow_redirects=False,
                ) as cleanup:
                    if action_id is not None:
                        cleanup.post(
                            f"/api/v1/actions/{action_id}/cancel",
                            headers=auth(token),
                        )
                    current = cleanup.get(
                        f"/api/v1/negotiations/{case_id}",
                        headers=auth(token),
                    )
                    if current.status_code == 200:
                        value = current.json()
                        if (
                            isinstance(value, dict)
                            and value.get("state") in {"active", "paused"}
                            and isinstance(value.get("revision"), int)
                        ):
                            cleanup.post(
                                f"/api/v1/negotiations/{case_id}/transition",
                                headers=auth(token),
                                json={
                                    "expected_revision": value["revision"],
                                    "state": "cancelled",
                                },
                            )
            except Exception:
                pass


if __name__ == "__main__":
    main()
