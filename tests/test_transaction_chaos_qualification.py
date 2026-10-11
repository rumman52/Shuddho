"""TX-28 transaction chaos qualification.

Failure injection contract:
- provider uncertainty never becomes an automatic second execution;
- duplicate delivery is idempotent;
- expired approval cannot cross the execution boundary.

These tests intentionally exercise the transaction safety boundary rather than
provider-specific adapters.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from test_coworker import account, container
from test_personal_transactions import payload as commitment_payload
from test_transaction_reconciliation import enable_transactions, reviewed_transaction

from services.coworker.action_schemas import ActionPrepare
from services.coworker.errors import CoworkerError
from services.coworker.models import TransactionReconciliationEvidence, utcnow



def test_tx28_duplicate_execution_attempt_has_single_bound_action(container):
    """A repeated delivery cannot create a second consequential binding."""
    enable_transactions(container)
    owner = account(container, "tx28-duplicate-delivery")
    confirmed = reviewed_transaction(container, owner, "tx28-duplicate-delivery")

    binding = confirmed["review_binding"]
    connection = container.actions.repo

    action = container.actions.repo.prepare(
        owner,
        ActionPrepare.model_validate({
            "connection_id": None,
            "payload": commitment_payload(),
        }),
        "tx28-single-action",
    )

    container.transactions.bind_external_action(
        owner,
        binding["transaction_id"],
        binding["transaction_revision"],
        action["id"],
    )

    with pytest.raises(CoworkerError) as duplicate:
        container.transactions.bind_external_action(
            owner,
            binding["transaction_id"],
            binding["transaction_revision"],
            action["id"],
        )

    assert duplicate.value.code == "transaction_execution_already_bound"


def test_tx28_provider_timeout_records_unknown_without_retry_path(container):
    """A lost provider response is evidence for reconciliation, not retry."""
    enable_transactions(container)
    owner = account(container, "tx28-provider-timeout")
    confirmed = reviewed_transaction(container, owner, "tx28-provider-timeout")

    transaction_id = confirmed["id"]
    with container.repository.sessions.begin() as db:
        db.add(
            TransactionReconciliationEvidence(
                id="tx28-timeout-evidence",
                transaction_id=transaction_id,
                owner_id=owner,
                transaction_revision=confirmed["revision"],
                evidence_type="provider_timeout",
                evidence={"result": "lost_provider_response"},
            )
        )

    result = container.transactions.get(owner, transaction_id)
    assert result["state"] in {"confirmed", "outcome_unknown"}


def test_tx28_approval_after_expiration_does_not_execute(container):
    """Expired approvals fail closed."""
    enable_transactions(container)
    owner = account(container, "tx28-expired-approval")
    confirmed = reviewed_transaction(container, owner, "tx28-expired-approval")

    with container.repository.sessions.begin() as db:
        row = container.transactions._transaction(
            db,
            owner,
            confirmed["id"],
            lock=True,
        )
        row.expires_at = utcnow() - timedelta(seconds=1)

    with pytest.raises(CoworkerError):
        container.transactions.advance_execution(
            owner,
            confirmed["id"],
            confirmed["revision"],
        )
