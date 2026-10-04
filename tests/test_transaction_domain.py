"""TX-02 generic transaction business-state foundation."""
from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from action_samples import connected, enable_actions
from test_coworker import account, container

from services.coworker.errors import CoworkerError
from services.coworker.models import Transaction, TransactionEvent, TransactionRevision
from services.coworker.transaction_repository import TransactionDraft


def enable_transactions(container):
    enable_actions(container)
    settings = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        transaction_operations=frozenset({"google:negotiation_commitment_email"}),
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.transactions.settings = settings


def test_migration_adds_generic_transaction_domain_tables(container):
    tables = set(inspect(container.repository.sessions.kw["bind"]).get_table_names())
    assert {
        "cw_transactions",
        "cw_transaction_revisions",
        "cw_transaction_events",
        "cw_transaction_execution_links",
    } <= tables


def test_transaction_create_is_owner_scoped_idempotent_and_server_binds_connection(container):
    enable_transactions(container)
    alice = account(container, "tx02-alice")
    bob = account(container, "tx02-bob")
    connection = connected(container.actions.repo, alice, "email")
    draft = TransactionDraft(
        transaction_kind="reservation",
        provider="google",
        connection_id=connection["id"],
        currency="usd",
        counterparty="Example Venue",
    )

    created, was_created = container.transactions.create(alice, draft, "tx02-create")
    assert was_created is True
    assert created["revision"] == 1
    assert created["state"] == "draft"
    assert created["currency"] == "USD"
    assert created["provider"] == "google"
    assert created["connection_id"] == connection["id"]
    assert created["provider_account_ref"] == "simulated-google-subject"

    replay, replay_created = container.transactions.create(alice, draft, "tx02-create")
    assert replay_created is False
    assert replay["id"] == created["id"]

    with pytest.raises(CoworkerError) as conflict:
        container.transactions.create(
            alice,
            TransactionDraft(
                transaction_kind="reservation",
                provider="google",
                connection_id=connection["id"],
                currency="EUR",
                counterparty="Example Venue",
            ),
            "tx02-create",
        )
    assert conflict.value.code == "idempotency_conflict"

    with pytest.raises(CoworkerError) as hidden:
        container.transactions.get(bob, created["id"])
    assert hidden.value.code == "not_found"

    assert container.transactions.list(bob) == []


def test_transaction_connection_provider_identity_is_fail_closed(container):
    enable_transactions(container)
    owner = account(container, "tx02-provider")
    connection = connected(container.actions.repo, owner, "email")

    with pytest.raises(CoworkerError) as mismatch:
        container.transactions.create(
            owner,
            TransactionDraft(
                transaction_kind="reservation",
                provider="microsoft",
                connection_id=connection["id"],
            ),
            "provider-mismatch",
        )
    assert mismatch.value.code == "transaction_provider_mismatch"


def test_transaction_domain_revisions_events_and_optimistic_state_changes(container):
    enable_transactions(container)
    owner = account(container, "tx02-state")
    created, _ = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="reservation",
            provider="internal",
            currency="USD",
            counterparty="Example Venue",
        ),
        "tx02-state",
    )

    terms_ready = container.transactions.transition(
        owner,
        created["id"],
        1,
        "terms_ready",
    )
    assert terms_ready["revision"] == 2
    assert terms_ready["state"] == "terms_ready"

    awaiting_review = container.transactions.transition(
        owner,
        created["id"],
        2,
        "awaiting_review",
    )
    assert awaiting_review["revision"] == 3

    awaiting_approval = container.transactions.transition(
        owner,
        created["id"],
        3,
        "awaiting_approval",
    )
    assert awaiting_approval["revision"] == 4

    revisions = container.transactions.revisions(owner, created["id"])
    assert [item["revision"] for item in revisions] == [1, 2, 3, 4]
    assert revisions[0]["snapshot"]["state"] == "draft"
    assert revisions[-1]["snapshot"]["state"] == "awaiting_approval"

    events = container.transactions.events(owner, created["id"])
    assert [item["sequence"] for item in events] == [1, 2, 3, 4]
    assert events[0]["event_type"] == "transaction_created"
    assert events[-1]["state"] == "awaiting_approval"

    with pytest.raises(CoworkerError) as stale:
        container.transactions.transition(owner, created["id"], 3, "cancelled")
    assert stale.value.code == "transaction_revision_conflict"


@pytest.mark.parametrize(
    "reserved_state",
    ["approved", "executing", "confirmed", "failed", "outcome_unknown"],
)
def test_tx02_cannot_cross_external_action_execution_boundary(container, reserved_state):
    enable_transactions(container)
    owner = account(container, "tx02-boundary-" + reserved_state)
    created, _ = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="reservation",
            provider="internal",
        ),
        "tx02-boundary",
    )

    with pytest.raises(CoworkerError) as blocked:
        container.transactions.transition(
            owner,
            created["id"],
            created["revision"],
            reserved_state,
        )
    assert blocked.value.code == "transaction_execution_boundary"

    saved = container.transactions.get(owner, created["id"])
    assert saved["state"] == "draft"
    assert saved["revision"] == 1


def test_transaction_cancel_is_terminal_for_tx02_domain(container):
    enable_transactions(container)
    owner = account(container, "tx02-cancel")
    created, _ = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="shopping_checkout",
            provider="internal",
        ),
        "tx02-cancel",
    )
    cancelled = container.transactions.transition(owner, created["id"], 1, "cancelled")
    assert cancelled["state"] == "cancelled"

    with pytest.raises(CoworkerError) as invalid:
        container.transactions.transition(owner, created["id"], 2, "draft")
    assert invalid.value.code == "transaction_transition_invalid"


def test_account_erasure_removes_generic_transaction_domain(container):
    enable_transactions(container)
    owner = account(container, "tx02-erasure")
    created, _ = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="reservation",
            provider="internal",
        ),
        "tx02-erasure",
    )
    container.transactions.transition(owner, created["id"], 1, "cancelled")

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True

    with container.repository.sessions() as db:
        assert db.scalar(select(Transaction).where(Transaction.owner_id == owner)) is None
        assert db.scalar(select(TransactionRevision).where(TransactionRevision.owner_id == owner)) is None
        assert db.scalar(select(TransactionEvent).where(TransactionEvent.owner_id == owner)) is None
