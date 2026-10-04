"""TX-03 exact final terms, money, quote freshness, and review binding."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from pydantic import ValidationError
from sqlalchemy import inspect, select

from action_samples import enable_actions
from test_coworker import account, container

from services.coworker.errors import CoworkerError
from services.coworker.models import TransactionTermsSnapshot, utcnow
from services.coworker.transaction_repository import TransactionDraft
from services.coworker.transaction_schemas import TransactionTermsDraft


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


def terms(*, total=12_500, currency="USD", expires_minutes=10, price_name="Room"):
    quoted = utcnow()
    return TransactionTermsDraft.model_validate({
        "terms": [
            {"name": price_name, "value": "Deluxe room"},
            {"name": "Cancellation", "value": "Free until 24 hours before arrival"},
        ],
        "price": {
            "currency": currency,
            "subtotal_minor": total - 1_500,
            "tax_minor": 1_000,
            "fees_minor": 500,
            "shipping_minor": 0,
            "discount_minor": 0,
            "total_minor": total,
        },
        "provider_quote_id": "quote-123",
        "quoted_at": quoted,
        "quote_expires_at": quoted + timedelta(minutes=expires_minutes),
    })


def create_transaction(container, owner, key="tx03"):
    value, created = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="reservation",
            provider="internal",
            currency="USD",
            counterparty="Example Hotel",
        ),
        key,
    )
    assert created is True
    return value


def test_tx03_migration_adds_terms_table_and_current_pointer(container):
    inspector = inspect(container.repository.sessions.kw["bind"])
    tables = set(inspector.get_table_names())
    assert "cw_transaction_terms" in tables
    columns = {column["name"] for column in inspector.get_columns("cw_transactions")}
    assert "current_terms_revision" in columns


def test_money_contract_uses_integer_minor_units_and_exact_arithmetic():
    value = terms()
    assert value.price.currency == "USD"
    assert value.price.total_minor == 12_500

    with pytest.raises(ValidationError):
        TransactionTermsDraft.model_validate({
            **value.model_dump(mode="python"),
            "price": {
                **value.price.model_dump(mode="python"),
                "total_minor": 125.50,
            },
        })

    with pytest.raises(ValidationError, match="exactly equal"):
        TransactionTermsDraft.model_validate({
            **value.model_dump(mode="python"),
            "price": {
                **value.price.model_dump(mode="python"),
                "total_minor": 12_499,
            },
        })


def test_terms_snapshot_is_immutable_hashed_and_owner_scoped(container):
    enable_transactions(container)
    alice = account(container, "tx03-alice")
    bob = account(container, "tx03-bob")
    transaction = create_transaction(container, alice, "tx03-terms")

    saved = container.transactions.set_terms(
        alice,
        transaction["id"],
        1,
        terms(),
    )
    assert saved["transaction"]["state"] == "terms_ready"
    assert saved["transaction"]["revision"] == 2
    assert saved["transaction"]["current_terms_revision"] == 2
    assert saved["terms"]["revision"] == 2
    assert saved["terms"]["currency"] == "USD"
    assert saved["terms"]["total_minor"] == 12_500
    assert len(saved["terms"]["terms_sha256"]) == 64

    with pytest.raises(CoworkerError) as hidden:
        container.transactions.latest_terms(bob, transaction["id"])
    assert hidden.value.code == "not_found"

    with container.repository.sessions() as db:
        row = db.get(TransactionTermsSnapshot, (transaction["id"], 2))
        assert row is not None
        assert row.terms_sha256 == saved["terms"]["terms_sha256"]


def test_fresh_terms_survive_state_revisions_but_expired_quote_blocks_review(container):
    enable_transactions(container)
    owner = account(container, "tx03-fresh")
    transaction = create_transaction(container, owner, "tx03-fresh")
    request = terms(expires_minutes=5)
    saved = container.transactions.set_terms(owner, transaction["id"], 1, request)

    review = container.transactions.transition(
        owner,
        transaction["id"],
        saved["transaction"]["revision"],
        "awaiting_review",
    )
    assert review["revision"] == 3
    assert review["current_terms_revision"] == 2

    binding = container.transactions.review_binding(
        owner,
        transaction["id"],
        3,
        expected_terms_sha256=saved["terms"]["terms_sha256"],
        now=request.quoted_at + timedelta(minutes=1),
    )
    assert binding["transaction_revision"] == 3
    assert binding["terms_revision"] == 2
    assert binding["terms_sha256"] == saved["terms"]["terms_sha256"]
    assert binding["currency"] == "USD"
    assert binding["total_minor"] == 12_500

    approval = container.transactions.transition(
        owner,
        transaction["id"],
        3,
        "awaiting_approval",
    )
    assert approval["revision"] == 4
    assert approval["current_terms_revision"] == 2

    with pytest.raises(CoworkerError) as expired:
        container.transactions.review_binding(
            owner,
            transaction["id"],
            4,
            expected_terms_sha256=saved["terms"]["terms_sha256"],
            now=request.quote_expires_at + timedelta(seconds=1),
        )
    assert expired.value.code == "transaction_quote_expired"


def test_changed_terms_force_fresh_review_and_old_hash_is_rejected(container):
    enable_transactions(container)
    owner = account(container, "tx03-change")
    transaction = create_transaction(container, owner, "tx03-change")
    first = container.transactions.set_terms(owner, transaction["id"], 1, terms())
    review = container.transactions.transition(owner, transaction["id"], 2, "awaiting_review")
    approval = container.transactions.transition(owner, transaction["id"], review["revision"], "awaiting_approval")
    assert approval["state"] == "awaiting_approval"

    changed = container.transactions.set_terms(
        owner,
        transaction["id"],
        approval["revision"],
        terms(total=13_000),
    )
    assert changed["transaction"]["state"] == "terms_ready"
    assert changed["transaction"]["current_terms_revision"] == changed["transaction"]["revision"]
    assert changed["terms"]["terms_sha256"] != first["terms"]["terms_sha256"]

    with pytest.raises(CoworkerError) as old_review:
        container.transactions.review_binding(
            owner,
            transaction["id"],
            changed["transaction"]["revision"],
            expected_terms_sha256=first["terms"]["terms_sha256"],
        )
    assert old_review.value.code == "transaction_terms_changed"


def test_currency_is_bound_to_transaction_and_cannot_silently_change(container):
    enable_transactions(container)
    owner = account(container, "tx03-currency")
    transaction = create_transaction(container, owner, "tx03-currency")

    with pytest.raises(CoworkerError) as changed:
        container.transactions.set_terms(
            owner,
            transaction["id"],
            1,
            terms(currency="EUR"),
        )
    assert changed.value.code == "transaction_currency_changed"


def test_quote_window_and_unique_terms_are_validated():
    quoted = utcnow()
    with pytest.raises(ValidationError, match="later than quote time"):
        TransactionTermsDraft.model_validate({
            "terms": [{"name": "Price", "value": "USD 10"}],
            "price": {
                "currency": "USD",
                "subtotal_minor": 1000,
                "tax_minor": 0,
                "fees_minor": 0,
                "shipping_minor": 0,
                "discount_minor": 0,
                "total_minor": 1000,
            },
            "provider_quote_id": "q",
            "quoted_at": quoted,
            "quote_expires_at": quoted,
        })

    with pytest.raises(ValidationError, match="unique"):
        TransactionTermsDraft.model_validate({
            "terms": [
                {"name": "Price", "value": "USD 10"},
                {"name": "price", "value": "USD 11"},
            ],
            "price": {
                "currency": "USD",
                "subtotal_minor": 1000,
                "tax_minor": 0,
                "fees_minor": 0,
                "shipping_minor": 0,
                "discount_minor": 0,
                "total_minor": 1000,
            },
            "quoted_at": quoted,
            "quote_expires_at": quoted + timedelta(minutes=5),
        })


def test_account_erasure_removes_transaction_terms(container):
    enable_transactions(container)
    owner = account(container, "tx03-erasure")
    transaction = create_transaction(container, owner, "tx03-erasure")
    container.transactions.set_terms(owner, transaction["id"], 1, terms())
    container.transactions.transition(owner, transaction["id"], 2, "cancelled")

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.scalar(
            select(TransactionTermsSnapshot).where(
                TransactionTermsSnapshot.owner_id == owner
            )
        ) is None
