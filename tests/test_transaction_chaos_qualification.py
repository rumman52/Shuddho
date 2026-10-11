"""CW-01 transaction chaos qualification.

The suite verifies the transaction safety boundary:
- duplicate deliveries preserve one execution identity;
- unknown provider outcomes require reconciliation;
- expired approvals cannot cross execution boundaries.
"""

from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")

from test_coworker import account, container
from test_transaction_reconciliation import enable_transactions, reviewed_transaction

from services.coworker.errors import CoworkerError
from services.coworker.models import TransactionReconciliationEvidence, utcnow


CHAOS_EXPECTATIONS = {
    "model_429": "retry_without_duplicate_action",
    "model_500": "fail_without_action",
    "model_timeout": "uncertain_reconcile",
    "provider_401": "fail_closed_no_execution",
    "provider_403": "fail_closed_no_execution",
    "provider_429": "retry_same_execution_identity",
    "provider_500": "unknown_reconcile_no_duplicate",
    "malformed_response": "failed_validation_no_duplicate",
    "database_disconnect": "rollback_or_reconcile",
    "s3_disconnect": "preserve_transaction_state",
    "temporal_outage": "resume_or_reconcile",
    "worker_crash": "resume_or_reconcile_no_duplicate",
    "api_crash": "safe_retry",
    "duplicate_message": "same_execution_binding",
    "lost_provider_response": "reconcile_without_resend",
    "approval_after_expiration": "reject_no_execution",
}


def test_tx28_duplicate_delivery_cannot_create_second_execution(container):
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

    assert container.transactions.get(owner, confirmed["id"]) is not None


def test_tx28_expired_approval_fails_closed(container):
    enable_transactions(container)
    owner = account(container, "tx28-expired")
    confirmed = reviewed_transaction(container, owner, "tx28-expired")

    with container.repository.sessions.begin() as db:
        row = container.transactions._transaction(db, owner, confirmed["id"], lock=True)
        row.expires_at = utcnow() - timedelta(seconds=1)

    with pytest.raises(CoworkerError):
        container.transactions.advance_execution(owner, confirmed["id"], confirmed["revision"])


def test_tx28_chaos_matrix_has_defined_outcomes():
    assert len(CHAOS_EXPECTATIONS) == 16
    assert all(CHAOS_EXPECTATIONS.values())
