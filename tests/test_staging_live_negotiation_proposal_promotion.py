from __future__ import annotations

import pytest

from scripts import staging_live_negotiation_proposal_promotion as live


def case(marker="marker123"):
    return {
        "id": "case-1",
        "revision": 2,
        "connection_id": "connection",
        "provider": "google",
        "counterparty_name": "Shuddho controlled staging mailbox",
        "counterparty_address": "stage@example.org",
        "subject": "Synthetic " + marker,
        "objective": "Synthetic objective",
    }


def proposal(marker="marker123"):
    value = {
        "id": "proposal-1",
        "case_id": "case-1",
        "case_revision": 2,
        "history_sequence": 1,
        "kind": "counteroffer",
        "output_language": "en",
        "summary": "Synthetic counteroffer",
        "terms": [
            {"name": "TestReference", "value": marker},
            {"name": "Amount", "value": "USD 0.00 synthetic"},
            {"name": "Effect", "value": "Controlled staging validation only"},
        ],
        "message": "Synthetic controlled staging message.",
        "rationale": "Synthetic rationale.",
        "risk_notes": [],
        "state": "suggested",
        "promoted_action_id": None,
    }
    value["proposal_hash"] = live.proposal_digest(value)
    return value


def promoted_action(marker="marker123"):
    current_case = case(marker)
    current_proposal = proposal(marker)
    binding = {
        "type": "negotiation_proposal",
        "proposal_id": current_proposal["id"],
        "proposal_hash": current_proposal["proposal_hash"],
        "case_id": current_case["id"],
        "case_revision": current_proposal["case_revision"],
        "history_sequence": current_proposal["history_sequence"],
    }
    payload = {
        "kind": "negotiation_commitment_email",
        "to": [current_case["counterparty_address"]],
        "cc": [],
        "bcc": [],
        "subject": current_case["subject"],
        "body": current_proposal["message"],
        "counterparty": current_case["counterparty_name"],
        "commitment_summary": current_proposal["summary"],
        "terms": current_proposal["terms"],
    }
    preview = {
        "version": 6,
        "provider": "google",
        "connection_id": "connection",
        "source_binding": binding,
        "payload": payload,
        "approval_scope": {
            "contract": "shuddho.consequential-action",
            "contract_version": 6,
            "action_kind": "negotiation_commitment_email",
            "source_binding": binding,
            "source_binding_sha256": live.stable_digest(binding),
        },
    }
    return current_case, current_proposal, {
        "id": "action-1",
        "connection_id": "connection",
        "kind": "negotiation_commitment_email",
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": live.digest(preview),
        "audit": [{"action": "action.prepared"}],
    }


def test_guard_requires_explicit_operator_opt_in(monkeypatch):
    monkeypatch.delenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_NEGOTIATION_PROPOSAL_PROMOTION",
        raising=False,
    )
    with pytest.raises(
        live.NegotiationProposalPromotionValidationFailure
    ):
        live.require_guard()
    monkeypatch.setenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_NEGOTIATION_PROPOSAL_PROMOTION",
        "true",
    )
    live.require_guard()


def test_proposal_digest_binds_exact_draft_and_case_history():
    value = proposal()
    assert live.proposal_digest(value) == value["proposal_hash"]
    changed = dict(value)
    changed["summary"] = "Changed"
    assert live.proposal_digest(changed) != value["proposal_hash"]


def test_proposal_validation_requires_exact_limits_and_binding():
    value = proposal()
    live.validate_proposal(
        value,
        case(),
        history_sequence=1,
        marker="marker123",
    )
    changed = dict(value)
    changed["terms"] = [
        {"name": "TestReference", "value": "other"},
        *value["terms"][1:],
    ]
    changed["proposal_hash"] = live.proposal_digest(changed)
    with pytest.raises(
        live.NegotiationProposalPromotionValidationFailure,
        match="staging term",
    ):
        live.validate_proposal(
            changed,
            case(),
            history_sequence=1,
            marker="marker123",
        )


def test_promoted_preview_binds_exact_source_payload_and_hash():
    current_case, current_proposal, action = promoted_action()
    live.validate_promoted_action(
        action,
        current_case,
        current_proposal,
        {"id": "connection", "provider": "google"},
    )

    changed = dict(action)
    changed_preview = dict(action["preview"])
    changed_preview["source_binding"] = dict(
        action["preview"]["source_binding"],
        history_sequence=2,
    )
    changed["preview"] = changed_preview
    changed["preview_hash"] = live.digest(changed_preview)
    with pytest.raises(
        live.NegotiationProposalPromotionValidationFailure
    ):
        live.validate_promoted_action(
            changed,
            current_case,
            current_proposal,
            {"id": "connection", "provider": "google"},
        )


def test_stale_denial_must_leave_action_unexecuted():
    _, _, action = promoted_action()
    live.validate_unexecuted(action)
    action["state"] = "queued"
    action["approved_at"] = "2026-09-29T00:00:00+00:00"
    action["audit"].append({"action": "action.approved"})
    with pytest.raises(
        live.NegotiationProposalPromotionValidationFailure
    ):
        live.validate_unexecuted(action)


def test_transaction_authority_and_operation_evidence_are_exact():
    assert live.validate_transaction_authority({
        "schema_version": 1,
        "personal_transactions_enabled": True,
        "operations": ["google:negotiation_commitment_email"],
    }, "google") == "google:negotiation_commitment_email"

    first = live.passed(
        "google proof",
        "google:negotiation_commitment_email",
    )
    second = live.passed(
        "microsoft proof",
        "microsoft:negotiation_commitment_email",
        first,
    )
    assert list(second["operation_evidence"]) == [
        "google:negotiation_commitment_email",
        "microsoft:negotiation_commitment_email",
    ]


def test_wrong_hash_changes_one_nibble():
    original = "a" * 64
    changed = live.wrong_hash(original)
    assert changed != original
    assert changed[1:] == original[1:]
    with pytest.raises(
        live.NegotiationProposalPromotionValidationFailure
    ):
        live.wrong_hash("short")
