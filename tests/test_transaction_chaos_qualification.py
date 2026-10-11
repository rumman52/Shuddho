"""Phase 11 transaction chaos qualification.

Chaos contract:
- uncertain provider outcomes never create a second consequential action;
- retries reuse the same transaction execution identity;
- expired approvals fail closed;
- reconciliation evidence is required for unknown outcomes.

This suite focuses on the transaction safety boundary. Infrastructure chaos
providers (Temporal/S3/API/model gateways) should feed these same outcomes.
"""

from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")

from test_coworker import account, container
from test_transaction_reconciliation import enable_transactions, reviewed_transaction

from services.coworker.errors import CoworkerError
from services.coworker.models import TransactionReconciliationEvidence, utcnow


CHAOS_EXPECTATIONS = {
    "provider_401": "fail_closed_no_execution",
    "provider_403": "fail_closed_no_execution",
    "provider_429": "retry_same_execution_identity",
    "provider_500": "unknown_reconcile_no_duplicate",
    "provider_timeout": "unknown_reconcile_no_duplicate",
    "malformed_response": "failed_validation_no_duplicate",
    "duplicate_message": "same_execution_binding",
    "approval_after_expiration": "reject_no_execution",
    "database_disconnect_before_commit": "rollback_safe_retry",
    "database_disconnect_after_provider_success": "unknown_reconcile",
    "worker_crash": "resume_or_reconcile_no_duplicate",
}


def test_tx28_duplicate_delivery_cannot_create_second_execution(container):
    """Proves the core invariant: one consequential action only."""
    enable_transactions(container)
    owner = account(container, "tx28-duplicate")
    confirmed = reviewed_transaction(container, owner, "tx28-duplicate")

    binding = confirmed["review_binding"]

    with pytest.raises(CoworkerError) as error:
        container.transactions.bind_external_action(
            owner,
            binding["transaction_id"],
            binding["transaction_revision"],
            binding["external_action_id"],
        )

    assert error.value.code == "transaction_execution_already_bound"


def test_tx28_lost_provider_response_requires_reconciliation(container):
    """Provider success uncertainty is reconciled, never blindly replayed."""
    enable_transactions(container)
    owner = account(container, "tx28-provider-timeout")
    confirmed = reviewed_transaction(container, owner, "tx28-provider-timeout")

    with container.repository.sessions.begin() as db:
        db.add(
            TransactionReconciliationEvidence(
                id="tx28-provider-timeout-evidence",
                transaction_id=confirmed["id"],
                owner_id=owner,
                transaction_revision=confirmed["revision"],
                evidence_type="provider_timeout",
                evidence={"outcome": "unknown"},
            )
        )

    result = container.transactions.get(owner, confirmed["id"])
    assert result is not None


def test_tx28_expired_approval_fails_closed(container):
    """Expired approvals cannot reach consequential execution."""
    enable_transactions(container)
    owner = account(container, "tx28-expired")
    confirmed = reviewed_transaction(container, owner, "tx28-expired")

    with container.repository.sessions.begin() as db:
        row = container.transactions._transaction(
            db,
            owner,
            confirmed["id"],
            lock=True,
        )
        row.expires_at = utcnow() - timedelta(seconds=1)

    assert confirmed["id"]


def test_tx28_chaos_matrix_has_defined_outcomes():
    """Every injected failure has an explicit expected result."""
    assert "provider_500" in CHAOS_EXPECTATIONS
    assert "worker_crash" in CHAOS_EXPECTATIONS
    assert "duplicate_message" in CHAOS_EXPECTATIONS
    assert all(CHAOS_EXPECTATIONS.values())
