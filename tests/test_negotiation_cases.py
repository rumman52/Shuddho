"""PA-09 durable negotiation case ledger."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from action_samples import connected, enable_actions
from test_coworker import account, container

from services.coworker.action_schemas import ActionPrepare
from services.coworker.errors import CoworkerError
from services.coworker.models import NegotiationCase, NegotiationCaseRevision, NegotiationOffer, NegotiationProposal, utcnow
from services.coworker.negotiation_schemas import (
    NegotiationCaseCreate,
    NegotiationCasePatch,
    NegotiationCaseTransition,
    NegotiationOfferCreate,
    NegotiationProposalDraft,
    NegotiationProposalRequest,
    NegotiationProposalReview,
)


def enable_negotiations(container):
    enable_actions(container)
    # enable_actions installs a simulated ActionService/ActionRepository for
    # provider tests. Keep the proposal service bound to that same repository
    # so its prepare path observes the enabled action settings and shared DB.
    container.negotiation_proposals.actions = container.actions.repo
    settings = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        transaction_operations=frozenset(
            {"google:negotiation_commitment_email"}
        ),
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.negotiations.settings = settings
    container.negotiation_proposals.settings = settings
    container.negotiation_proposals.model.settings = settings


def case_request(connection_id):
    return NegotiationCaseCreate.model_validate({
        "connection_id": connection_id,
        "counterparty_name": "Example Supplier Ltd.",
        "counterparty_address": "counterparty@example.org",
        "subject": "Supply agreement",
        "objective": "Reach acceptable supply terms without exceeding the approved ceiling.",
        "limits": [
            {"name": "Price", "comparison": "at_most", "value": "USD 5,000"},
            {"name": "Delivery", "comparison": "at_most", "value": "30 days"},
        ],
    })


def create_case(container, owner, key="negotiation-case-1"):
    connection = connected(container.actions.repo, owner, "email")
    value, created = container.negotiations.create(
        owner,
        case_request(connection["id"]),
        key,
    )
    assert created is True
    return value, connection


def test_case_creation_is_idempotent_owner_scoped_and_revisioned(container):
    enable_negotiations(container)
    alice = account(container, "alice-negotiation")
    bob = account(container, "bob-negotiation")
    value, connection = create_case(container, alice)

    replay, created = container.negotiations.create(
        alice,
        case_request(connection["id"]),
        "negotiation-case-1",
    )
    assert created is False
    assert replay["id"] == value["id"]
    assert value["revision"] == 1
    assert value["provider"] == "google"
    assert value["offers"] == []

    with pytest.raises(CoworkerError) as hidden:
        container.negotiations.get(bob, value["id"])
    assert hidden.value.code == "not_found"

    with pytest.raises(CoworkerError) as conflict:
        changed = case_request(connection["id"]).model_copy(
            update={"objective": "Different objective"}
        )
        container.negotiations.create(
            alice,
            changed,
            "negotiation-case-1",
        )
    assert conflict.value.code == "idempotency_conflict"


def test_case_edits_are_optimistic_and_counterparty_scope_is_immutable(container):
    enable_negotiations(container)
    owner = account(container, "case-edit")
    value, _connection = create_case(container, owner, "case-edit-key")

    updated = container.negotiations.update(
        owner,
        value["id"],
        NegotiationCasePatch.model_validate({
            "expected_revision": 1,
            "objective": "Protect margin while preserving the delivery deadline.",
            "limits": [
                {"name": "Price", "comparison": "at_most", "value": "USD 4,900"},
            ],
        }),
    )
    assert updated["revision"] == 2
    assert updated["counterparty_address"] == "counterparty@example.org"
    assert updated["connection_id"] == value["connection_id"]

    with pytest.raises(CoworkerError) as stale:
        container.negotiations.update(
            owner,
            value["id"],
            NegotiationCasePatch(
                expected_revision=1,
                subject="Stale edit",
            ),
        )
    assert stale.value.code == "negotiation_revision_conflict"
    revisions = container.negotiations.revisions(owner, value["id"])
    assert [item["revision"] for item in revisions] == [1, 2]
    assert revisions[0]["snapshot"]["counterparty_address"] == "counterparty@example.org"


def test_case_lifecycle_blocks_history_until_resumed_and_terminal_is_final(container):
    enable_negotiations(container)
    owner = account(container, "case-state")
    value, _connection = create_case(container, owner, "case-state-key")

    paused = container.negotiations.transition(
        owner,
        value["id"],
        NegotiationCaseTransition(expected_revision=1, state="paused"),
    )
    assert paused["state"] == "paused"
    assert paused["revision"] == 2

    with pytest.raises(CoworkerError) as inactive:
        container.negotiations.append_offer(
            owner,
            value["id"],
            NegotiationOfferCreate(
                direction="theirs",
                kind="proposal",
                summary="Supplier proposed USD 5,200.",
                terms=[{"name": "Price", "value": "USD 5,200"}],
                occurred_at=utcnow(),
            ),
            "paused-offer",
        )
    assert inactive.value.code == "negotiation_case_inactive"

    resumed = container.negotiations.transition(
        owner,
        value["id"],
        NegotiationCaseTransition(expected_revision=2, state="active"),
    )
    closed = container.negotiations.transition(
        owner,
        value["id"],
        NegotiationCaseTransition(
            expected_revision=resumed["revision"],
            state="closed",
        ),
    )
    assert closed["state"] == "closed"

    with pytest.raises(CoworkerError) as terminal:
        container.negotiations.transition(
            owner,
            value["id"],
            NegotiationCaseTransition(
                expected_revision=closed["revision"],
                state="active",
            ),
        )
    assert terminal.value.code == "negotiation_case_terminal"


def test_offer_history_is_append_only_idempotent_and_sequenced(container):
    enable_negotiations(container)
    owner = account(container, "offer-history")
    value, _connection = create_case(container, owner, "offer-history-case")

    request = NegotiationOfferCreate(
        direction="theirs",
        kind="counteroffer",
        summary="Supplier reduced the quote.",
        terms=[
            {"name": "Price", "value": "USD 5,100"},
            {"name": "Delivery", "value": "28 days"},
        ],
        occurred_at=utcnow(),
    )
    first, created = container.negotiations.append_offer(
        owner,
        value["id"],
        request,
        "offer-history-1",
    )
    assert created is True
    assert first["sequence"] == 1

    replay, created = container.negotiations.append_offer(
        owner,
        value["id"],
        request,
        "offer-history-1",
    )
    assert created is False
    assert replay["id"] == first["id"]

    second, _ = container.negotiations.append_offer(
        owner,
        value["id"],
        NegotiationOfferCreate(
            direction="ours",
            kind="proposal",
            summary="We proposed the approved ceiling.",
            terms=[{"name": "Price", "value": "USD 5,000"}],
            occurred_at=utcnow(),
        ),
        "offer-history-2",
    )
    assert second["sequence"] == 2
    saved = container.negotiations.get(owner, value["id"])
    assert [item["sequence"] for item in saved["offers"]] == [1, 2]


def test_confirmed_commitment_link_must_match_case_and_exact_action(container):
    enable_negotiations(container)
    owner = account(container, "linked-commitment")
    case, connection = create_case(container, owner, "linked-case")
    payload = {
        "kind": "negotiation_commitment_email",
        "to": [case["counterparty_address"]],
        "cc": [],
        "bcc": [],
        "subject": case["subject"],
        "body": "We confirm the final terms below.",
        "counterparty": case["counterparty_name"],
        "commitment_summary": "Accept final supply agreement.",
        "terms": [
            {"name": "Price", "value": "USD 5,000"},
            {"name": "Delivery", "value": "30 days"},
        ],
    }
    prepared = container.actions.repo.prepare(
        owner,
        ActionPrepare.model_validate({
            "connection_id": connection["id"],
            "payload": payload,
        }),
        "linked-action",
    )
    approved = container.actions.repo.approve(
        owner,
        prepared["id"],
        prepared["preview_hash"],
    )
    claimed = container.actions.repo.claim_execution(approved["id"])
    assert claimed is not None
    container.actions.repo.finish(
        approved["id"],
        "succeeded",
        receipt={
            "provider": "google",
            "provider_id": "mail-1",
            "thread_id": "thread-1",
            "status": "accepted_by_gmail",
            "confirmed_at": utcnow().isoformat(),
        },
    )

    linked, created = container.negotiations.append_offer(
        owner,
        case["id"],
        NegotiationOfferCreate(
            direction="ours",
            kind="commitment",
            summary="Accept final supply agreement.",
            terms=payload["terms"],
            external_action_id=approved["id"],
            occurred_at=utcnow(),
        ),
        "linked-offer",
    )
    assert created is True
    assert linked["external_action_id"] == approved["id"]

    with pytest.raises(CoworkerError) as changed:
        container.negotiations.append_offer(
            owner,
            case["id"],
            NegotiationOfferCreate(
                direction="ours",
                kind="commitment",
                summary="Accept final supply agreement.",
                terms=[{"name": "Price", "value": "USD 4,900"}],
                external_action_id=approved["id"],
                occurred_at=utcnow(),
            ),
            "linked-offer-changed",
        )
    assert changed.value.code in {
        "negotiation_action_changed",
        "negotiation_action_unverified",
    }


def test_case_creation_requires_qualified_provider_operation(container):
    enable_actions(container)
    owner = account(container, "operation-gated-case")
    connection = connected(container.actions.repo, owner, "email")
    settings = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        transaction_operations=frozenset(
            {"microsoft:negotiation_commitment_email"}
        ),
        microsoft_actions_enabled=True,
        microsoft_client_id="client",
        microsoft_client_secret="secret",
        microsoft_redirect_uri="https://app.example.test/oauth/microsoft/callback",
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.negotiations.settings = settings

    with pytest.raises(CoworkerError) as denied:
        container.negotiations.create(
            owner,
            case_request(connection["id"]),
            "operation-gated-case",
        )
    assert denied.value.code == "personal_transaction_operation_disabled"




class FakeNegotiationProposalModel:
    def __init__(self, settings):
        self.settings = settings
        self.calls = 0

    async def propose(self, context, request):
        self.calls += 1
        return (
            NegotiationProposalDraft.model_validate({
                "summary": "Offer the approved ceiling with a shorter delivery target.",
                "terms": [
                    {"name": "Price", "value": "USD 5,000"},
                    {"name": "Delivery", "value": "28 days"},
                ],
                "message": (
                    "We would like to propose USD 5,000 with delivery in 28 days, "
                    "subject to review and agreement by both parties."
                ),
                "rationale": "Matches the recorded price ceiling and remains a reviewable draft.",
                "risk_notes": ["No counterparty acceptance has been recorded."],
            }),
            25,
            {"model": "synthetic-proposal-model", "prompt_sha256": "a" * 64},
        )


def enable_proposals(container):
    enable_negotiations(container)
    settings = replace(
        container.settings,
        intelligent_planner_enabled=True,
        agent_runtime_enabled=True,
        deepseek_api_key="test-only",
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.negotiations.settings = settings
    container.negotiation_proposals.settings = settings
    container.negotiation_proposals.model = FakeNegotiationProposalModel(settings)


def enable_proposal_promotion(container):
    enable_proposals(container)
    settings = replace(
        container.settings,
        agent_action_proposals_enabled=True,
        negotiation_proposal_promotion_enabled=True,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.negotiations.settings = settings
    container.negotiation_proposals.settings = settings
    container.negotiation_proposals.model.settings = settings


def generate_proposal(container, owner, case, key, kind="counteroffer"):
    proposal, created = asyncio.run(
        container.negotiation_proposals.generate(
            owner,
            case["id"],
            NegotiationProposalRequest(
                expected_revision=case["revision"],
                kind=kind,
                output_language="en",
            ),
            key,
        )
    )
    assert created is True
    return proposal


def test_model_proposal_is_inert_idempotent_and_hash_reviewed(container):
    enable_proposals(container)
    owner = account(container, "proposal-owner")
    case, _connection = create_case(container, owner, "proposal-case")
    request = NegotiationProposalRequest(
        expected_revision=case["revision"],
        kind="counteroffer",
        output_language="en",
    )

    proposal, created = asyncio.run(
        container.negotiation_proposals.generate(
            owner,
            case["id"],
            request,
            "proposal-request-1",
        )
    )
    assert created is True
    assert proposal["state"] == "suggested"
    assert proposal["case_revision"] == case["revision"]
    assert proposal["history_sequence"] == 0
    assert proposal["proposal_hash"]
    assert container.negotiation_proposals.model.calls == 1

    replay, created = asyncio.run(
        container.negotiation_proposals.generate(
            owner,
            case["id"],
            request,
            "proposal-request-1",
        )
    )
    assert created is False
    assert replay["id"] == proposal["id"]
    assert container.negotiation_proposals.model.calls == 1

    with pytest.raises(CoworkerError) as changed:
        container.negotiation_proposals.dismiss(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash="0" * 64),
        )
    assert changed.value.code == "negotiation_proposal_changed"

    dismissed = container.negotiation_proposals.dismiss(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    assert dismissed["state"] == "dismissed"


def test_proposal_becomes_stale_when_offer_history_changes(container):
    enable_proposals(container)
    owner = account(container, "proposal-stale")
    case, _connection = create_case(container, owner, "proposal-stale-case")
    request = NegotiationProposalRequest(
        expected_revision=case["revision"],
        kind="proposal",
        output_language="en",
    )
    proposal, _created = asyncio.run(
        container.negotiation_proposals.generate(
            owner,
            case["id"],
            request,
            "proposal-stale-request",
        )
    )
    assert proposal["state"] == "suggested"

    container.negotiations.append_offer(
        owner,
        case["id"],
        NegotiationOfferCreate(
            direction="theirs",
            kind="counteroffer",
            summary="Counterparty changed the commercial terms.",
            terms=[{"name": "Price", "value": "USD 5,100"}],
            occurred_at=utcnow(),
        ),
        "proposal-stale-offer",
    )
    refreshed = container.negotiations.get(owner, case["id"])
    saved = next(item for item in refreshed["proposals"] if item["id"] == proposal["id"])
    assert saved["state"] == "stale"


def test_proposal_generation_rejects_stale_case_revision(container):
    enable_proposals(container)
    owner = account(container, "proposal-revision")
    case, _connection = create_case(container, owner, "proposal-revision-case")
    updated = container.negotiations.update(
        owner,
        case["id"],
        NegotiationCasePatch(
            expected_revision=case["revision"],
            objective="Protect margin and request a shorter delivery window.",
        ),
    )
    assert updated["revision"] == case["revision"] + 1

    with pytest.raises(CoworkerError) as stale:
        asyncio.run(
            container.negotiation_proposals.generate(
                owner,
                case["id"],
                NegotiationProposalRequest(
                    expected_revision=case["revision"],
                    kind="response",
                    output_language="en",
                ),
                "proposal-stale-revision",
            )
        )
    assert stale.value.code == "negotiation_revision_conflict"


def test_proposal_promotion_requires_independent_gate(container):
    enable_proposals(container)
    owner = account(container, "proposal-promotion-disabled")
    case, _connection = create_case(container, owner, "proposal-promotion-disabled-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-promotion-disabled-request",
    )

    with pytest.raises(CoworkerError) as denied:
        container.negotiation_proposals.promote(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
        )
    assert denied.value.code == "negotiation_proposal_promotion_disabled"


def test_exact_proposal_promotion_creates_only_bound_unapproved_preview(container):
    enable_proposal_promotion(container)
    owner = account(container, "proposal-promote")
    other = account(container, "proposal-promote-other")
    case, connection = create_case(container, owner, "proposal-promote-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-promote-request",
    )

    with pytest.raises(CoworkerError) as wrong_hash:
        container.negotiation_proposals.promote(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash="0" * 64),
        )
    assert wrong_hash.value.code == "negotiation_proposal_changed"

    with pytest.raises(CoworkerError) as cross_owner:
        container.negotiation_proposals.promote(
            other,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
        )
    assert cross_owner.value.code == "not_found"

    action = container.negotiation_proposals.promote(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    assert action["state"] == "awaiting_approval"
    assert action["approved_at"] is None
    assert action["receipt"] is None
    assert action["connection_id"] == connection["id"]
    assert action["preview"]["payload"] == {
        "kind": "negotiation_commitment_email",
        "to": ["counterparty@example.org"],
        "cc": [],
        "bcc": [],
        "subject": "Supply agreement",
        "body": proposal["message"],
        "counterparty": "Example Supplier Ltd.",
        "commitment_summary": proposal["summary"],
        "terms": proposal["terms"],
    }
    assert action["preview"]["source_binding"] == {
        "type": "negotiation_proposal",
        "proposal_id": proposal["id"],
        "proposal_hash": proposal["proposal_hash"],
        "case_id": case["id"],
        "case_revision": case["revision"],
        "history_sequence": proposal["history_sequence"],
    }
    refreshed = container.negotiations.get(owner, case["id"])
    promoted = next(
        item for item in refreshed["proposals"] if item["id"] == proposal["id"]
    )
    assert promoted["state"] == "promoted"
    assert promoted["promoted_action_id"] == action["id"]
    assert promoted["promoted_at"] is not None

    replay = container.negotiation_proposals.promote(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    assert replay["id"] == action["id"]
    assert replay["state"] == "awaiting_approval"


def test_promoted_send_history_requires_success_and_is_idempotent(container):
    enable_proposal_promotion(container)
    owner = account(container, "proposal-record-send")
    other = account(container, "proposal-record-send-other")
    case, _connection = create_case(container, owner, "proposal-record-send-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-record-send-request",
    )
    action = container.negotiation_proposals.promote(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )

    with pytest.raises(CoworkerError) as unconfirmed:
        container.negotiations.record_promoted_send(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
        )
    assert unconfirmed.value.code == "negotiation_promoted_send_unconfirmed"

    with pytest.raises(CoworkerError) as wrong_hash:
        container.negotiations.record_promoted_send(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash="0" * 64),
        )
    assert wrong_hash.value.code == "negotiation_proposal_changed"

    with pytest.raises(CoworkerError) as cross_owner:
        container.negotiations.record_promoted_send(
            other,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
        )
    assert cross_owner.value.code == "not_found"

    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    claimed = container.actions.repo.claim_execution(approved["id"])
    assert claimed is not None
    finished_at = utcnow()
    container.actions.repo.finish(
        approved["id"],
        "succeeded",
        receipt={
            "provider": "google",
            "provider_id": "mail-promoted-1",
            "thread_id": "thread-promoted-1",
            "status": "accepted_by_gmail",
            "confirmed_at": finished_at.isoformat(),
        },
    )

    recorded, created = container.negotiations.record_promoted_send(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    assert created is True
    assert recorded["direction"] == "ours"
    assert recorded["kind"] == "commitment"
    assert recorded["summary"] == proposal["summary"]
    assert recorded["terms"] == proposal["terms"]
    assert recorded["external_action_id"] == action["id"]

    replay, created = container.negotiations.record_promoted_send(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    assert created is False
    assert replay["id"] == recorded["id"]

    saved = container.negotiations.get(owner, case["id"])
    linked = [
        offer for offer in saved["offers"]
        if offer["external_action_id"] == action["id"]
    ]
    assert len(linked) == 1


def test_failed_or_uncertain_promoted_action_never_records_confirmed_send(container):
    enable_proposal_promotion(container)
    owner = account(container, "proposal-record-failed")
    case, _connection = create_case(container, owner, "proposal-record-failed-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-record-failed-request",
    )
    action = container.negotiation_proposals.promote(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    claimed = container.actions.repo.claim_execution(approved["id"])
    assert claimed is not None
    container.actions.repo.finish(
        approved["id"],
        "outcome_unknown",
        error_code="provider_timeout",
    )

    with pytest.raises(CoworkerError) as denied:
        container.negotiations.record_promoted_send(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
        )
    assert denied.value.code == "negotiation_promoted_send_unconfirmed"
    assert container.negotiations.get(owner, case["id"])["offers"] == []


def test_stale_proposal_cannot_be_promoted(container):
    enable_proposal_promotion(container)
    owner = account(container, "proposal-promote-stale")
    case, _connection = create_case(container, owner, "proposal-promote-stale-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-promote-stale-request",
    )
    container.negotiations.append_offer(
        owner,
        case["id"],
        NegotiationOfferCreate(
            direction="theirs",
            kind="counteroffer",
            summary="The counterparty changed price after the draft.",
            terms=[{"name": "Price", "value": "USD 5,250"}],
            occurred_at=utcnow(),
        ),
        "proposal-promote-stale-offer",
    )

    with pytest.raises(CoworkerError) as stale:
        container.negotiation_proposals.promote(
            owner,
            case["id"],
            proposal["id"],
            NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
        )
    assert stale.value.code == "negotiation_proposal_stale"


def test_case_change_after_promotion_invalidates_approval(container):
    enable_proposal_promotion(container)
    owner = account(container, "proposal-approval-stale")
    case, _connection = create_case(container, owner, "proposal-approval-stale-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-approval-stale-request",
    )
    action = container.negotiation_proposals.promote(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    container.negotiations.update(
        owner,
        case["id"],
        NegotiationCasePatch(
            expected_revision=case["revision"],
            objective="Require a new commercial position before any commitment.",
        ),
    )

    with pytest.raises(CoworkerError) as stale:
        container.actions.repo.approve(
            owner,
            action["id"],
            action["preview_hash"],
        )
    assert stale.value.code == "negotiation_proposal_stale"
    saved = container.actions.repo.get(owner, action["id"])
    assert saved["state"] == "awaiting_approval"
    assert saved["approved_at"] is None


def test_offer_change_after_approval_cancels_before_provider_claim(container):
    enable_proposal_promotion(container)
    owner = account(container, "proposal-execution-stale")
    case, _connection = create_case(container, owner, "proposal-execution-stale-case")
    proposal = generate_proposal(
        container,
        owner,
        case,
        "proposal-execution-stale-request",
    )
    action = container.negotiation_proposals.promote(
        owner,
        case["id"],
        proposal["id"],
        NegotiationProposalReview(proposal_hash=proposal["proposal_hash"]),
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    assert approved["state"] == "queued"

    container.negotiations.append_offer(
        owner,
        case["id"],
        NegotiationOfferCreate(
            direction="theirs",
            kind="counteroffer",
            summary="New counterparty offer arrived after approval.",
            terms=[{"name": "Price", "value": "USD 4,950"}],
            occurred_at=utcnow(),
        ),
        "proposal-execution-stale-offer",
    )
    assert container.actions.repo.claim_execution(action["id"]) is None
    saved = container.actions.repo.get(owner, action["id"])
    assert saved["state"] == "cancelled"
    assert saved["error_code"] == "negotiation_proposal_stale"


def test_promotion_flag_dependencies_fail_closed(container):
    enable_proposals(container)
    missing_transactions = replace(
        container.settings,
        agent_action_proposals_enabled=True,
        negotiation_proposal_promotion_enabled=True,
        personal_transactions_enabled=False,
        transaction_operations=frozenset(),
    )
    with pytest.raises(ValueError, match="SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED"):
        missing_transactions.validate()

    missing_action_proposals = replace(
        container.settings,
        negotiation_proposal_promotion_enabled=True,
        agent_action_proposals_enabled=False,
    )
    with pytest.raises(ValueError, match="SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED"):
        missing_action_proposals.validate()


def test_account_erasure_removes_negotiation_case_history(container):
    enable_negotiations(container)
    owner = account(container, "negotiation-erasure")
    case, _connection = create_case(container, owner, "negotiation-erasure-case")
    container.negotiations.append_offer(
        owner,
        case["id"],
        NegotiationOfferCreate(
            direction="theirs",
            kind="proposal",
            summary="Synthetic offer for retention coverage.",
            terms=[{"name": "Price", "value": "USD 5,100"}],
            occurred_at=utcnow(),
        ),
        "negotiation-erasure-offer",
    )

    settings = replace(
        container.settings,
        intelligent_planner_enabled=True,
        agent_runtime_enabled=True,
        deepseek_api_key="test-only",
    )
    settings.validate()
    container.settings = settings
    container.negotiations.settings = settings
    container.negotiation_proposals.settings = settings
    container.negotiation_proposals.model = FakeNegotiationProposalModel(settings)
    current = container.negotiations.get(owner, case["id"])
    asyncio.run(
        container.negotiation_proposals.generate(
            owner,
            case["id"],
            NegotiationProposalRequest(
                expected_revision=current["revision"],
                kind="response",
                output_language="en",
            ),
            "negotiation-erasure-proposal",
        )
    )

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.query(NegotiationProposal).filter(
            NegotiationProposal.owner_id == owner
        ).count() == 0
        assert db.query(NegotiationOffer).filter(
            NegotiationOffer.owner_id == owner
        ).count() == 0
        assert db.query(NegotiationCaseRevision).filter(
            NegotiationCaseRevision.owner_id == owner
        ).count() == 0
        assert db.query(NegotiationCase).filter(
            NegotiationCase.owner_id == owner
        ).count() == 0
