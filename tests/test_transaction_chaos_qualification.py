"""Mandatory transaction safety regressions using real ledgers and transport.

Provider I/O is simulated; these tests do not certify deployed infrastructure.
"""
import asyncio
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from test_permission_gateway import enable_boundary
from test_coworker import account, container
from test_transaction_reconciliation import bound_action, enable_transactions, reviewed_transaction
from services.coworker.errors import CoworkerError
from services.coworker.google_actions import SEND_URL
from services.coworker.models import ExternalAction, utcnow


def prepared(container, key):
    enable_transactions(container)
    provider, _gateway = enable_boundary(container)
    owner = account(container, key)
    review = reviewed_transaction(container, owner, key)
    action, link = bound_action(container, owner, review, key + "-action")
    return provider, owner, review, action, link


def test_duplicate_binding_replays_same_link_and_rejects_another_action(container):
    _provider, owner, review, action, link = prepared(container, "chaos-binding")
    binding = review["review_binding"]
    replay = container.transactions.bind_external_action(
        owner, binding["transaction_id"], binding["transaction_revision"], action["id"],
    )
    assert replay == link
    with pytest.raises(CoworkerError) as conflict:
        bound_action(container, owner, review, "chaos-second-action")
    assert conflict.value.code == "transaction_execution_already_bound"


def test_accepted_then_lost_response_preserves_uncertainty_without_resend(container):
    provider, owner, review, action, _link = prepared(container, "chaos-lost-reply")
    provider.lose_reply = True
    container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    for _ in range(3):
        asyncio.run(container.actions.execute(action["id"]))
    surface = container.transactions.sync_external_action(owner, review["review_binding"]["transaction_id"])
    assert surface["transaction"]["state"] == "outcome_unknown"
    assert surface["evidence"]["action_state"] == "outcome_unknown"
    assert surface["evidence"]["receipt"] is None
    assert len(provider.sent) == 1
    assert len([r for r in provider.requests if r.method == "POST" and str(r.url) == SEND_URL]) == 1
    assert container.actions.repo.claim_execution(action["id"]) is None


@pytest.mark.parametrize("approved_first", [False, True])
def test_expired_approval_or_execution_claim_never_calls_provider(container, approved_first):
    provider, owner, _review, action, _link = prepared(container, "chaos-expired")
    if approved_first:
        container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    with container.repository.sessions.begin() as db:
        db.get(ExternalAction, action["id"]).expires_at = utcnow() - timedelta(seconds=1)
    if not approved_first:
        with pytest.raises(CoworkerError) as expired:
            container.actions.repo.approve(owner, action["id"], action["preview_hash"])
        assert expired.value.code == "approval_expired"
    else:
        assert container.actions.repo.claim_execution(action["id"]) is None
    asyncio.run(container.actions.execute(action["id"]))
    assert not provider.requests
    assert not provider.sent
    if approved_first:
        assert container.actions.repo.get(owner, action["id"])["state"] == "expired"


def test_replayed_success_never_dispatches_again(container):
    provider, owner, review, action, _link = prepared(container, "chaos-success")
    container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    for _ in range(3):
        asyncio.run(container.actions.execute(action["id"]))
    surface = container.transactions.sync_external_action(owner, review["review_binding"]["transaction_id"])
    assert surface["transaction"]["state"] == "confirmed"
    assert surface["evidence"]["receipt"]["provider_id"] == "mail-1"
    assert len(surface["evidence"]["receipt_sha256"]) == 64
    assert len(provider.sent) == 1
