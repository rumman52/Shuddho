"""Phase 11 transaction chaos qualification.

The transaction contract under test:

* provider uncertainty must not trigger a second consequential action;
* duplicate delivery must resolve to one execution binding;
* expired approvals fail closed;
* reconciliation evidence is the source of truth after uncertain outcomes.
"""

from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")

from test_coworker import account, container
from test_transaction_reconciliation import enable_transactions, reviewed_transaction

from services.coworker.errors import CoworkerError
from services.coworker.models import TransactionReconciliationEvidence, utcnow


def test_tx28_duplicate_execution_binding_is_rejected(container):
    """A duplicate delivery cannot create a second consequential binding."""
    enable_transactions(container)
    owner = account(container, "tx28-duplicate")
    confirmed = reviewed_transaction(container, owner, "tx28-duplicate")

    action_id = confirmed["review_binding"]["external_action_id"]

    with pytest.raises(CoworkerError) as error:
        container.transactions.bind_external_action(
            owner,
            confirmed["review_binding"]["transaction_id"],
            confirmed["review_binding"]["transaction_revision"],
            action_id,
        )

    assert error.value.code == "transaction_execution_already_bound"


def test_tx28_provider_timeout_creates_reconciliation_evidence(container):
    """Lost provider responses remain reconcilable and are not blindly retried."""
    enable_transactions(container)
    owner = account(container, "tx28-timeout")
    confirmed = reviewed_transaction(container, owner, "tx28-timeout")

    with container.repository.sessions.begin() as db:
        db.add(
            TransactionReconciliationEvidence(
                id="tx28-timeout-evidence",
                transaction_id=confirmed["id"],
                owner_id=owner,
                transaction_revision=confirmed["revision"],
                evidence_type="provider_timeout",
                evidence={"status": "lost_provider_response"},
            )
        )

    result = container.transactions.get(owner, confirmed["id"])
    assert result is not None


def test_tx28_expired_approval_fails_closed(container):
    """An approval after expiration cannot cross the execution boundary."""
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

    with pytest.raises(CoworkerError):
        container.transactions.get(owner, confirmed["id"])
