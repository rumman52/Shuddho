"""PA-09 durable negotiation case ledger."""
from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from action_samples import connected, enable_actions
from test_coworker import account, container

from services.coworker.action_schemas import ActionPrepare
from services.coworker.errors import CoworkerError
from services.coworker.models import NegotiationCase, NegotiationCaseRevision, NegotiationOffer, utcnow
from services.coworker.negotiation_schemas import (
    NegotiationCaseCreate,
    NegotiationCasePatch,
    NegotiationCaseTransition,
    NegotiationOfferCreate,
)


def enable_negotiations(container):
    enable_actions(container)
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

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.query(NegotiationOffer).filter(
            NegotiationOffer.owner_id == owner
        ).count() == 0
        assert db.query(NegotiationCaseRevision).filter(
            NegotiationCaseRevision.owner_id == owner
        ).count() == 0
        assert db.query(NegotiationCase).filter(
            NegotiationCase.owner_id == owner
        ).count() == 0
