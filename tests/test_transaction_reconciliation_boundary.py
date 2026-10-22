"""Transaction reconciliation boundary regressions.

These tests protect the uncertainty boundary. They do not certify external
providers; provider execution remains behind ExternalAction.
"""

import asyncio

from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from test_permission_gateway import enable_boundary
from test_coworker import account, container
from test_transaction_reconciliation import bound_action, enable_transactions, reviewed_transaction
from services.coworker.errors import CoworkerError
from services.coworker.transaction_repository import TransactionRepository



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


def test_tx05_corrupted_unicode_digest_never_escapes_as_type_error():
    """Even corrupted DB evidence must produce a controlled 409 domain error."""
    common = {
        "transaction_id": "tx-unicode",
        "owner_id": "owner-unicode",
        "external_action_id": "external-unicode",
        "provider": "google",
        "action_kind": "negotiation_commitment_email",
        "preview_hash": "a" * 64,
    }
    link = SimpleNamespace(**common)
    evidence = SimpleNamespace(
        **common,
        action_state="succeeded",
        receipt=None,
        receipt_sha256=None,
        error_code=None,
        action_finished_at=None,
        evidence_sha256="é" * 64,
    )
    with pytest.raises(CoworkerError) as invalid:
        TransactionRepository._verify_execution_evidence(evidence, link)
    assert invalid.value.code == "transaction_evidence_integrity_failed"
    assert invalid.value.status_code == 409
