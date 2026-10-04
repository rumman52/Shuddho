"""TX-05 transaction-to-ExternalAction receipt and reconciliation evidence."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from action_samples import action_request, connected, enable_actions
from test_coworker import account, container
from test_personal_transactions import payload as commitment_payload
from test_transaction_terms import terms

from services.coworker.action_schemas import ActionPrepare
from services.coworker.errors import CoworkerError
from services.coworker.models import TransactionExecutionLink, TransactionReconciliationEvidence, utcnow
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


def reviewed_transaction(container, owner, key="tx05-reviewed"):
    created, was_created = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="reservation",
            provider="internal",
            currency="USD",
            counterparty="Example Hotel",
        ),
        key,
    )
    assert was_created is True
    saved = container.transactions.set_terms(owner, created["id"], 1, terms())
    review = container.transactions.start_review(
        owner,
        created["id"],
        saved["transaction"]["revision"],
    )
    confirmed = container.transactions.confirm_review(
        owner,
        created["id"],
        review["revision"],
        saved["terms"]["terms_sha256"],
    )
    return confirmed


def bound_action(container, owner, confirmed, key="tx05-action"):
    connection = connected(container.actions.repo, owner, "email")
    exact_terms = confirmed["review_binding"]
    request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": commitment_payload(
            counterparty="Example Hotel",
            terms=[
                {"name": "Room", "value": "Deluxe room"},
                {
                    "name": "Cancellation",
                    "value": "Free until 24 hours before arrival",
                },
            ],
        ),
    })
    binding = {
        "transaction_id": exact_terms["transaction_id"],
        "transaction_revision": exact_terms["transaction_revision"],
        "terms_revision": exact_terms["terms_revision"],
        "terms_sha256": exact_terms["terms_sha256"],
    }
    action = container.actions.repo.prepare(
        owner,
        request,
        key,
        transaction_binding=binding,
    )
    assert action["preview"]["version"] == 7
    assert action["preview"]["transaction_binding"] == binding
    assert action["preview"]["approval_scope"]["contract_version"] == 7
    assert action["preview"]["approval_scope"]["transaction_binding"] == binding
    assert len(
        action["preview"]["approval_scope"]["transaction_binding_sha256"]
    ) == 64
    link = container.transactions.bind_external_action(
        owner,
        exact_terms["transaction_id"],
        exact_terms["transaction_revision"],
        action["id"],
    )
    return action, link


def test_tx05_migration_adds_bound_link_columns_and_evidence_table(container):
    inspector = inspect(container.repository.sessions.kw["bind"])
    tables = set(inspector.get_table_names())
    assert "cw_transaction_reconciliation_evidence" in tables
    columns = {
        item["name"]
        for item in inspector.get_columns("cw_transaction_execution_links")
    }
    assert {
        "terms_revision",
        "terms_sha256",
        "preview_hash",
        "provider",
        "action_kind",
    } <= columns


def test_non_transaction_action_cannot_receive_transaction_binding(container):
    enable_transactions(container)
    owner = account(container, "tx05-non-transaction")
    confirmed = reviewed_transaction(container, owner, "tx05-non-transaction")
    connection = connected(container.actions.repo, owner, "email")
    binding = confirmed["review_binding"]

    with pytest.raises(CoworkerError) as blocked:
        container.actions.repo.prepare(
            owner,
            action_request(connection, "email_send"),
            "tx05-email-binding",
            transaction_binding={
                "transaction_id": binding["transaction_id"],
                "transaction_revision": binding["transaction_revision"],
                "terms_revision": binding["terms_revision"],
                "terms_sha256": binding["terms_sha256"],
            },
        )
    assert blocked.value.code == "approval_changed"


def test_link_requires_exact_reviewed_transaction_binding(container):
    enable_transactions(container)
    owner = account(container, "tx05-exact-binding")
    confirmed = reviewed_transaction(container, owner, "tx05-exact-binding")
    connection = connected(container.actions.repo, owner, "email")
    binding = confirmed["review_binding"]
    request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": commitment_payload(),
    })
    wrong_hash = "0" * 64 if binding["terms_sha256"] != "0" * 64 else "1" * 64
    action = container.actions.repo.prepare(
        owner,
        request,
        "tx05-wrong-binding",
        transaction_binding={
            "transaction_id": binding["transaction_id"],
            "transaction_revision": binding["transaction_revision"],
            "terms_revision": binding["terms_revision"],
            "terms_sha256": wrong_hash,
        },
    )

    with pytest.raises(CoworkerError) as changed:
        container.transactions.bind_external_action(
            owner,
            binding["transaction_id"],
            binding["transaction_revision"],
            action["id"],
        )
    assert changed.value.code == "transaction_action_binding_changed"


def test_transaction_execution_link_is_single_attempt_and_owner_scoped(container):
    enable_transactions(container)
    owner = account(container, "tx05-one-attempt")
    other = account(container, "tx05-other")
    confirmed = reviewed_transaction(container, owner, "tx05-one-attempt")
    first, link = bound_action(container, owner, confirmed, "tx05-first-action")
    assert link["external_action_id"] == first["id"]
    assert link["terms_sha256"] == confirmed["review_binding"]["terms_sha256"]

    connection = connected(container.actions.repo, owner, "email")
    binding = confirmed["review_binding"]
    second = container.actions.repo.prepare(
        owner,
        ActionPrepare.model_validate({
            "connection_id": connection["id"],
            "payload": commitment_payload(),
        }),
        "tx05-second-action",
        transaction_binding={
            "transaction_id": binding["transaction_id"],
            "transaction_revision": binding["transaction_revision"],
            "terms_revision": binding["terms_revision"],
            "terms_sha256": binding["terms_sha256"],
        },
    )
    with pytest.raises(CoworkerError) as duplicate:
        container.transactions.bind_external_action(
            owner,
            binding["transaction_id"],
            binding["transaction_revision"],
            second["id"],
        )
    assert duplicate.value.code == "transaction_execution_already_bound"

    with pytest.raises(CoworkerError) as hidden:
        container.transactions.execution_surface(other, binding["transaction_id"])
    assert hidden.value.code == "not_found"


def test_local_sync_projects_action_state_and_dedupes_receipt_evidence(container):
    enable_transactions(container)
    owner = account(container, "tx05-sync")
    confirmed = reviewed_transaction(container, owner, "tx05-sync")
    action, _link = bound_action(container, owner, confirmed, "tx05-sync-action")
    transaction_id = confirmed["review_binding"]["transaction_id"]

    awaiting = container.transactions.sync_external_action(owner, transaction_id)
    assert awaiting["transaction"]["state"] == "awaiting_approval"
    assert awaiting["evidence"]["action_state"] == "awaiting_approval"

    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    queued = container.transactions.sync_external_action(owner, transaction_id)
    assert queued["transaction"]["state"] == "approved"
    assert queued["evidence"]["action_state"] == "queued"

    claimed = container.actions.repo.claim_execution(approved["id"])
    assert claimed is not None
    executing = container.transactions.sync_external_action(owner, transaction_id)
    assert executing["transaction"]["state"] == "executing"
    assert executing["evidence"]["action_state"] == "executing"

    receipt = {
        "provider": "google",
        "status": "accepted_by_gmail",
        "provider_id": "mail-tx05",
        "message_id": f'<{action["id"]}@shuddho.invalid>',
        "confirmed_at": utcnow().isoformat(),
    }
    container.actions.repo.finish(
        action["id"],
        "succeeded",
        receipt=receipt,
    )
    succeeded = container.transactions.sync_external_action(owner, transaction_id)
    assert succeeded["transaction"]["state"] == "confirmed"
    assert succeeded["evidence"]["action_state"] == "succeeded"
    assert succeeded["evidence"]["receipt"] == receipt
    assert len(succeeded["evidence"]["receipt_sha256"]) == 64

    replay = container.transactions.sync_external_action(owner, transaction_id)
    assert replay["evidence"]["evidence_sha256"] == succeeded["evidence"]["evidence_sha256"]
    surface = container.transactions.execution_surface(owner, transaction_id)
    assert [item["action_state"] for item in surface["evidence"]] == [
        "awaiting_approval",
        "queued",
        "executing",
        "succeeded",
    ]
    assert surface["reconciliation"]["available"] is False
    observed = [
        item
        for item in container.transactions.events(owner, transaction_id)
        if item["event_type"] == "transaction_execution_observed"
    ]
    assert len(observed) == 4


def test_outcome_unknown_never_retries_and_late_receipt_can_confirm(container):
    enable_transactions(container)
    owner = account(container, "tx05-unknown")
    confirmed = reviewed_transaction(container, owner, "tx05-unknown")
    action, _link = bound_action(container, owner, confirmed, "tx05-unknown-action")
    transaction_id = confirmed["review_binding"]["transaction_id"]

    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    claimed = container.actions.repo.claim_execution(approved["id"])
    assert claimed is not None
    container.actions.repo.finish(
        action["id"],
        "outcome_unknown",
        error_code="provider_timeout",
    )
    unknown = container.transactions.sync_external_action(owner, transaction_id)
    assert unknown["transaction"]["state"] == "outcome_unknown"
    assert unknown["evidence"]["receipt"] is None

    with pytest.raises(CoworkerError) as unavailable:
        container.transactions.reconciliation_action_id(owner, transaction_id)
    assert unavailable.value.code == "reconciliation_unavailable"

    receipt = {
        "provider": "google",
        "status": "accepted_by_gmail",
        "provider_id": "mail-late",
        "message_id": f'<{action["id"]}@shuddho.invalid>',
        "confirmed_at": utcnow().isoformat(),
    }
    container.actions.repo.finish(action["id"], "succeeded", receipt=receipt)
    recovered = container.transactions.sync_external_action(owner, transaction_id)
    assert recovered["transaction"]["state"] == "confirmed"
    assert [item["action_state"] for item in container.transactions.execution_surface(
        owner,
        transaction_id,
    )["evidence"]][-2:] == ["outcome_unknown", "succeeded"]


def test_invalid_success_receipt_fails_closed_without_confirming_transaction(container):
    enable_transactions(container)
    owner = account(container, "tx05-receipt")
    confirmed = reviewed_transaction(container, owner, "tx05-receipt")
    action, _link = bound_action(container, owner, confirmed, "tx05-receipt-action")
    transaction_id = confirmed["review_binding"]["transaction_id"]

    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    assert container.actions.repo.claim_execution(approved["id"]) is not None
    container.actions.repo.finish(
        action["id"],
        "succeeded",
        receipt={
            "provider": "microsoft",
            "status": "accepted",
            "confirmed_at": utcnow().isoformat(),
        },
    )
    with pytest.raises(CoworkerError) as invalid:
        container.transactions.sync_external_action(owner, transaction_id)
    assert invalid.value.code == "transaction_receipt_invalid"
    assert container.transactions.get(owner, transaction_id)["state"] == "awaiting_approval"



def test_terms_cannot_change_after_external_action_is_bound(container):
    enable_transactions(container)
    owner = account(container, "tx05-locked-terms")
    confirmed = reviewed_transaction(container, owner, "tx05-locked-terms")
    _action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-locked-terms-action",
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]

    with pytest.raises(CoworkerError) as blocked:
        container.transactions.set_terms(
            owner,
            transaction_id,
            confirmed["review_binding"]["transaction_revision"],
            terms(total=13_500),
        )
    assert blocked.value.code == "transaction_execution_already_bound"


def test_cancelled_transaction_cannot_approve_bound_action(container):
    enable_transactions(container)
    owner = account(container, "tx05-cancel-binding")
    confirmed = reviewed_transaction(container, owner, "tx05-cancel-binding")
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-cancel-binding-action",
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]

    cancelled = container.transactions.transition(
        owner,
        transaction_id,
        confirmed["review_binding"]["transaction_revision"],
        "cancelled",
    )
    assert cancelled["state"] == "cancelled"

    with pytest.raises(CoworkerError) as blocked:
        container.actions.repo.approve(
            owner,
            action["id"],
            action["preview_hash"],
        )
    assert blocked.value.code == "transaction_action_binding_changed"
    assert container.actions.repo.get(owner, action["id"])["state"] == "awaiting_approval"


def test_quote_expiry_is_rechecked_before_bound_action_approval(container):
    enable_transactions(container)
    owner = account(container, "tx05-expired-before-approval")
    created, _ = container.transactions.create(
        owner,
        TransactionDraft(
            transaction_kind="reservation",
            provider="internal",
            currency="USD",
            counterparty="Example Hotel",
        ),
        "tx05-expired-before-approval",
    )
    request = terms(expires_minutes=1)
    saved = container.transactions.set_terms(owner, created["id"], 1, request)
    review = container.transactions.start_review(
        owner,
        created["id"],
        saved["transaction"]["revision"],
    )
    confirmed = container.transactions.confirm_review(
        owner,
        created["id"],
        review["revision"],
        saved["terms"]["terms_sha256"],
    )
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-expired-before-approval-action",
    )

    with container.repository.sessions.begin() as db:
        from services.coworker.models import TransactionTermsSnapshot
        row = db.get(
            TransactionTermsSnapshot,
            (
                confirmed["review_binding"]["transaction_id"],
                confirmed["review_binding"]["terms_revision"],
            ),
        )
        expired_at = utcnow() - timedelta(seconds=1)
        row.quote_expires_at = expired_at
        row.quoted_at = expired_at - timedelta(minutes=1)

    with pytest.raises(CoworkerError) as expired:
        container.actions.repo.approve(
            owner,
            action["id"],
            action["preview_hash"],
        )
    assert expired.value.code == "transaction_quote_expired"


def test_bound_action_claim_rechecks_transaction_state(container):
    enable_transactions(container)
    owner = account(container, "tx05-claim-recheck")
    confirmed = reviewed_transaction(container, owner, "tx05-claim-recheck")
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-claim-recheck-action",
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    container.transactions.transition(
        owner,
        transaction_id,
        confirmed["review_binding"]["transaction_revision"],
        "cancelled",
    )

    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "transaction_action_binding_changed"



def test_review_state_cannot_reopen_after_execution_binding(container):
    enable_transactions(container)
    owner = account(container, "tx05-review-freeze")
    confirmed = reviewed_transaction(container, owner, "tx05-review-freeze")
    _action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-review-freeze-action",
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]

    with pytest.raises(CoworkerError) as blocked:
        container.transactions.start_review(
            owner,
            transaction_id,
            confirmed["review_binding"]["transaction_revision"],
        )
    assert blocked.value.code == "transaction_execution_already_bound"
    current = container.transactions.get(owner, transaction_id)
    assert current["state"] == "awaiting_approval"
    assert current["revision"] == confirmed["review_binding"]["transaction_revision"]



def test_account_erasure_removes_transaction_execution_evidence(container):
    enable_transactions(container)
    owner = account(container, "tx05-erasure")
    confirmed = reviewed_transaction(container, owner, "tx05-erasure")
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-erasure-action",
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    assert container.actions.repo.claim_execution(approved["id"]) is not None
    container.actions.repo.finish(
        action["id"],
        "succeeded",
        receipt={
            "provider": "google",
            "status": "accepted_by_gmail",
            "provider_id": "mail-erasure",
            "message_id": f'<{action["id"]}@shuddho.invalid>',
            "confirmed_at": utcnow().isoformat(),
        },
    )
    container.transactions.sync_external_action(owner, transaction_id)

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.scalar(
            select(TransactionExecutionLink).where(
                TransactionExecutionLink.owner_id == owner
            )
        ) is None
        assert db.scalar(
            select(TransactionReconciliationEvidence).where(
                TransactionReconciliationEvidence.owner_id == owner
            )
        ) is None



def test_quote_expiry_after_approval_blocks_provider_claim(container):
    enable_transactions(container)
    owner = account(container, "tx05-expired-before-claim")
    confirmed = reviewed_transaction(container, owner, "tx05-expired-before-claim")
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-expired-before-claim-action",
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )

    with container.repository.sessions.begin() as db:
        from services.coworker.models import TransactionTermsSnapshot
        row = db.get(
            TransactionTermsSnapshot,
            (
                confirmed["review_binding"]["transaction_id"],
                confirmed["review_binding"]["terms_revision"],
            ),
        )
        expired_at = utcnow() - timedelta(seconds=1)
        row.quote_expires_at = expired_at
        row.quoted_at = expired_at - timedelta(minutes=1)

    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "transaction_quote_expired"
