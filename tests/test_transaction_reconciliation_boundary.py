"""Transaction reconciliation boundary regressions.

These tests protect the uncertainty boundary. They do not certify external
providers; provider execution remains behind ExternalAction.
"""

import asyncio

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from test_permission_gateway import enable_boundary
from test_coworker import account, container
from test_transaction_reconciliation import bound_action, enable_transactions, reviewed_transaction
from services.coworker.errors import CoworkerError



def prepared_transaction(container, key):
    enable_transactions(container)
    provider, _gateway = enable_boundary(container)
    owner = account(container, key)
    review = reviewed_transaction(container, owner, key)
    action, link = bound_action(container, owner, review, key + "-action")
    return provider, owner, review, action, link



def test_reconciliation_keeps_single_execution_identity_after_unknown_outcome(container):
    provider, owner, review, action, _link = prepared_transaction(container, "tx-reconcile-unknown")

    provider.lose_reply = True
    container.actions.repo.approve(owner, action["id"], action["preview_hash"])

    asyncio.run(container.actions.execute(action["id"]))
    first_count = len(provider.sent)

    surface = container.transactions.sync_external_action(
        owner,
        review["review_binding"]["transaction_id"],
    )

    assert surface["transaction"]["state"] == "outcome_unknown"
    assert len(provider.sent) == first_count == 1

    asyncio.run(container.actions.execute(action["id"]))
    assert len(provider.sent) == 1



def test_reconciliation_receipt_binding_remains_owner_scoped(container):
    provider, owner, review, action, _link = prepared_transaction(container, "tx-owner-scope")

    container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    asyncio.run(container.actions.execute(action["id"]))

    surface = container.transactions.sync_external_action(
        owner,
        review["review_binding"]["transaction_id"],
    )

    assert surface["evidence"]["external_action_id"] == action["id"]
    assert surface["evidence"]["provider"] == "google"
    assert surface["transaction"]["state"] == "confirmed"
    assert len(provider.sent) == 1

    other = account(container, "tx-owner-scope-other")
    with pytest.raises(CoworkerError) as hidden:
        container.transactions.sync_external_action(
            other, review["review_binding"]["transaction_id"],
        )
    assert hidden.value.status_code == 404
