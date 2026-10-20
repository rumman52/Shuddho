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
from services.coworker.models import TransactionEvent, TransactionExecutionLink, TransactionReconciliationEvidence, TransactionTermsSnapshot, utcnow
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


def reviewed_transaction(container, owner, key="tx05-reviewed", *, expires_minutes=10):
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
    saved = container.transactions.set_terms(
        owner,
        created["id"],
        1,
        terms(expires_minutes=expires_minutes),
    )
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

    # Repeated inconclusive provider checks are not new outcome evidence.
    # A fresh error/timestamp must not create a second unknown settlement.
    container.actions.repo.finish(
        action["id"],
        "outcome_unknown",
        error_code="reconciliation_no_receipt",
    )
    still_same = container.transactions.sync_external_action(owner, transaction_id)
    assert still_same["transaction"]["state"] == "outcome_unknown"
    assert still_same["evidence"]["error_code"] == "provider_timeout"
    assert still_same["evidence"]["evidence_sha256"] == unknown["evidence"]["evidence_sha256"]
    assert len(container.transactions.execution_surface(
        owner,
        transaction_id,
    )["evidence"]) == 1

    # A late unverified failure must not turn uncertain external settlement
    # into an apparent definitive transaction failure or append false evidence.
    container.actions.repo.finish(
        action["id"],
        "failed",
        error_code="worker_restarted",
    )
    still_unknown = container.transactions.sync_external_action(owner, transaction_id)
    assert still_unknown["transaction"]["state"] == "outcome_unknown"
    assert still_unknown["evidence"]["action_state"] == "outcome_unknown"
    assert still_unknown["evidence"]["evidence_sha256"] == unknown["evidence"]["evidence_sha256"]

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



@pytest.mark.parametrize("tampered_field", ["terms", "price"])
def test_sync_rejects_tampered_persisted_terms_before_receipt_projection(
    container,
    tampered_field,
):
    """A matching stored hash does not verify the bytes of a persisted snapshot."""
    enable_transactions(container)
    owner = account(container, f"tx05-sync-snapshot-integrity-{tampered_field}")
    confirmed = reviewed_transaction(
        container,
        owner,
        f"tx05-sync-snapshot-integrity-{tampered_field}",
    )
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        f"tx05-sync-snapshot-integrity-action-{tampered_field}",
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
            "provider_id": "mail-tx05-integrity",
            "confirmed_at": utcnow().isoformat(),
        },
    )

    binding = confirmed["review_binding"]
    with container.repository.sessions.begin() as db:
        row = db.get(
            TransactionTermsSnapshot,
            (binding["transaction_id"], binding["terms_revision"]),
        )
        assert row is not None
        if tampered_field == "terms":
            changed_terms = [dict(item) for item in row.terms]
            changed_terms[0]["value"] = "Tampered room after execution"
            row.terms = changed_terms
        else:
            # Normalization would conceal this changed stored price at hash check.
            row.price = {**row.price, "currency": "usd"}
        # Deliberately retain the old terms_sha256: it matches the execution
        # link, but no longer authenticates the stored canonical terms.

    before = container.transactions.get(owner, transaction_id)
    assert before["state"] == "awaiting_approval"
    with pytest.raises(CoworkerError) as blocked:
        container.transactions.sync_external_action(owner, transaction_id)
    assert blocked.value.code == "transaction_terms_integrity_failed"
    after = container.transactions.get(owner, transaction_id)
    assert after["state"] == before["state"]
    assert after["revision"] == before["revision"]
    # The external surface now rejects corrupted terms itself. Inspect the
    # persisted evidence rows directly to assert that sync added nothing.
    with container.repository.sessions() as db:
        evidence = db.scalars(
            select(TransactionReconciliationEvidence).where(
                TransactionReconciliationEvidence.transaction_id == transaction_id,
                TransactionReconciliationEvidence.owner_id == owner,
            )
        ).all()
    assert evidence == []


@pytest.mark.parametrize("tampered_field", ["terms", "price"])
def test_execution_surface_rejects_stale_digest_and_disables_reconciliation_lookup(
    container,
    tampered_field,
):
    """Read-only reconciliation authority must authenticate bound saved terms."""
    enable_transactions(container)
    owner = account(container, f"tx05-read-surface-integrity-{tampered_field}")
    confirmed = reviewed_transaction(
        container, owner, f"tx05-read-surface-integrity-{tampered_field}"
    )
    action, link = bound_action(
        container, owner, confirmed, f"tx05-read-surface-action-{tampered_field}"
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]

    intact = container.transactions.execution_surface(owner, transaction_id)
    assert intact["link"]["id"] == link["id"]
    assert intact["evidence"] == []

    if tampered_field == "terms":
        tamper_terms_snapshot(container, confirmed)
    else:
        binding = confirmed["review_binding"]
        with container.repository.sessions.begin() as db:
            stored = db.get(
                TransactionTermsSnapshot,
                (binding["transaction_id"], binding["terms_revision"]),
            )
            assert stored is not None
            stored.price = {**stored.price, "currency": "usd"}

    # The execution link, preview and digest column still agree, but the
    # canonical saved terms/price no longer authenticate that digest.
    with pytest.raises(CoworkerError) as surface_blocked:
        container.transactions.execution_surface(owner, transaction_id)
    assert surface_blocked.value.code == "transaction_terms_integrity_failed"

    # This API obtains its provider action ID through execution_surface;
    # corrupt persisted terms must not yield provider-reconciliation authority.
    with pytest.raises(CoworkerError) as lookup_blocked:
        container.transactions.reconciliation_action_id(owner, transaction_id)
    assert lookup_blocked.value.code == "transaction_terms_integrity_failed"

    assert container.actions.repo.get(owner, action["id"])["state"] == "awaiting_approval"
    assert container.transactions.get(owner, transaction_id)["state"] == "awaiting_approval"



@pytest.mark.parametrize(
    "tampered_field",
    ["receipt", "receipt_sha256", "evidence_sha256", "provider", "preview_hash"],
)
def test_tampered_persisted_reconciliation_evidence_blocks_history_and_sync(
    container,
    tampered_field,
):
    """A saved receipt is not trustworthy simply because an evidence row exists."""
    enable_transactions(container)
    owner = account(container, f"tx05-evidence-integrity-{tampered_field}")
    confirmed = reviewed_transaction(
        container, owner, f"tx05-evidence-integrity-{tampered_field}"
    )
    action, _link = bound_action(
        container, owner, confirmed, f"tx05-evidence-action-{tampered_field}"
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]
    approved = container.actions.repo.approve(
        owner, action["id"], action["preview_hash"]
    )
    assert container.actions.repo.claim_execution(approved["id"]) is not None
    receipt = {
        "provider": "google",
        "status": "accepted_by_gmail",
        "provider_id": f"message-{tampered_field}",
        "message_id": f'<{action["id"]}@shuddho.invalid>',
        "confirmed_at": utcnow().isoformat(),
    }
    container.actions.repo.finish(action["id"], "succeeded", receipt=receipt)
    initial = container.transactions.sync_external_action(owner, transaction_id)
    assert initial["transaction"]["state"] == "confirmed"
    assert initial["evidence"]["receipt"] == receipt
    intact = container.transactions.execution_surface(owner, transaction_id)
    assert len(intact["evidence"]) == 1

    # Simulate corrupted persisted evidence while the linked action and its
    # original provider receipt remain unchanged. No connected provider call.
    with container.repository.sessions.begin() as db:
        saved = db.scalar(
            select(TransactionReconciliationEvidence).where(
                TransactionReconciliationEvidence.transaction_id == transaction_id,
                TransactionReconciliationEvidence.owner_id == owner,
            )
        )
        assert saved is not None
        if tampered_field == "receipt":
            saved.receipt = {**saved.receipt, "status": "not_confirmed"}
        elif tampered_field == "receipt_sha256":
            saved.receipt_sha256 = "0" * 64
        elif tampered_field == "evidence_sha256":
            saved.evidence_sha256 = "0" * 64
        elif tampered_field == "provider":
            saved.provider = "microsoft"
        else:
            saved.preview_hash = "0" * 64

    with pytest.raises(CoworkerError) as history_blocked:
        container.transactions.execution_surface(owner, transaction_id)
    assert history_blocked.value.code == "transaction_evidence_integrity_failed"

    # Replaying a completed action must not dedupe against or append past a
    # corrupted reconciliation row, even if its digest no longer matches.
    with pytest.raises(CoworkerError) as replay_blocked:
        container.transactions.sync_external_action(owner, transaction_id)
    assert replay_blocked.value.code == "transaction_evidence_integrity_failed"
    with container.repository.sessions() as db:
        saved_rows = db.scalars(
            select(TransactionReconciliationEvidence).where(
                TransactionReconciliationEvidence.transaction_id == transaction_id,
                TransactionReconciliationEvidence.owner_id == owner,
            )
        ).all()
    assert len(saved_rows) == 1
    assert container.transactions.get(owner, transaction_id)["state"] == "confirmed"


@pytest.mark.parametrize(
    "tamper",
    ["sequence_gap", "revision_mismatch", "event_digest", "missing_evidence"],
)
def test_tx05_saved_evidence_history_must_match_transaction_event_ledger(
    container,
    tamper,
):
    """Receipt hashes alone cannot authenticate the event order or revision."""
    enable_transactions(container)
    owner = account(container, f"tx05-ledger-{tamper}")
    confirmed = reviewed_transaction(container, owner, f"tx05-ledger-{tamper}")
    action, _link = bound_action(
        container, owner, confirmed, f"tx05-ledger-action-{tamper}"
    )
    transaction_id = confirmed["review_binding"]["transaction_id"]
    approved = container.actions.repo.approve(
        owner, action["id"], action["preview_hash"]
    )
    assert container.actions.repo.claim_execution(approved["id"]) is not None
    receipt = {
        "provider": "google",
        "status": "accepted_by_gmail",
        "provider_id": f"tx05-ledger-{tamper}",
        "message_id": f'<{action["id"]}@shuddho.invalid>',
        "confirmed_at": utcnow().isoformat(),
    }
    container.actions.repo.finish(action["id"], "succeeded", receipt=receipt)
    saved = container.transactions.sync_external_action(owner, transaction_id)
    assert saved["transaction"]["state"] == "confirmed"
    assert len(container.transactions.execution_surface(owner, transaction_id)["evidence"]) == 1

    # Tamper with metadata outside evidence_sha256 or delete only the evidence,
    # keeping its immutable-looking transaction event intact.
    with container.repository.sessions.begin() as db:
        evidence = db.scalar(
            select(TransactionReconciliationEvidence).where(
                TransactionReconciliationEvidence.transaction_id == transaction_id,
                TransactionReconciliationEvidence.owner_id == owner,
            )
        )
        event = db.scalar(
            select(TransactionEvent).where(
                TransactionEvent.transaction_id == transaction_id,
                TransactionEvent.owner_id == owner,
                TransactionEvent.event_type == "transaction_execution_observed",
            )
        )
        assert evidence is not None and event is not None
        assert event.details["evidence_sha256"] == evidence.evidence_sha256
        if tamper == "sequence_gap":
            evidence.sequence = 9
        elif tamper == "revision_mismatch":
            evidence.transaction_revision += 9
        elif tamper == "event_digest":
            event.details = {**event.details, "evidence_sha256": "0" * 64}
        else:
            db.delete(evidence)

    # The historical ledger must be validated before serving receipt history
    # or allowing a replay to change state/append another observation.
    with pytest.raises(CoworkerError) as history_error:
        container.transactions.execution_surface(owner, transaction_id)
    assert history_error.value.code == "transaction_evidence_integrity_failed"
    with pytest.raises(CoworkerError) as replay_error:
        container.transactions.sync_external_action(owner, transaction_id)
    assert replay_error.value.code == "transaction_evidence_integrity_failed"
    assert container.transactions.get(owner, transaction_id)["state"] == "confirmed"


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


def test_quote_expiry_is_rechecked_before_bound_action_approval(container, monkeypatch):
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

    # Advance only the action boundary clock: the signed quote remains immutable.
    # Rewriting quote timestamps would correctly fail integrity verification.
    future = utcnow() + timedelta(minutes=2)
    monkeypatch.setattr("services.coworker.action_repository.utcnow", lambda: future)

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





def tamper_terms_snapshot(container, confirmed):
    binding = confirmed["review_binding"]
    with container.repository.sessions.begin() as db:
        row = db.get(
            TransactionTermsSnapshot,
            (binding["transaction_id"], binding["terms_revision"]),
        )
        assert row is not None
        changed_terms = [dict(item) for item in row.terms]
        changed_terms[0]["value"] = "Tampered room description"
        row.terms = changed_terms


def test_tampered_terms_block_bound_action_approval(container):
    enable_transactions(container)
    owner = account(container, "tx05-tampered-before-approval")
    confirmed = reviewed_transaction(container, owner, "tx05-tampered-before-approval")
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-tampered-before-approval-action",
    )
    tamper_terms_snapshot(container, confirmed)

    with pytest.raises(CoworkerError) as blocked:
        container.actions.repo.approve(
            owner,
            action["id"],
            action["preview_hash"],
        )
    assert blocked.value.code == "transaction_terms_integrity_failed"
    assert container.actions.repo.get(owner, action["id"])["state"] == "awaiting_approval"


def test_tampered_terms_after_approval_block_provider_execution(container):
    enable_transactions(container)
    owner = account(container, "tx05-tampered-after-approval")
    confirmed = reviewed_transaction(container, owner, "tx05-tampered-after-approval")
    action, _link = bound_action(
        container,
        owner,
        confirmed,
        "tx05-tampered-after-approval-action",
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    tamper_terms_snapshot(container, confirmed)

    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "transaction_terms_integrity_failed"


def test_noncanonical_stored_price_after_approval_blocks_provider_claim(container):
    """A formatting-only DB edit must not slip past the bound action guard."""
    enable_transactions(container)
    owner = account(container, "tx05-noncanonical-price-after-approval")
    confirmed = reviewed_transaction(container, owner, "tx05-noncanonical-price-after-approval")
    action, _link = bound_action(
        container, owner, confirmed, "tx05-noncanonical-price-after-approval-action"
    )
    approved = container.actions.repo.approve(
        owner, action["id"], action["preview_hash"]
    )
    binding = confirmed["review_binding"]
    with container.repository.sessions.begin() as db:
        row = db.get(
            TransactionTermsSnapshot,
            (binding["transaction_id"], binding["terms_revision"]),
        )
        assert row is not None
        row.price = {**row.price, "currency": "usd"}

    # Pydantic would canonicalize "usd" to "USD", leaving the old hash
    # unchanged; the already-approved persisted price must still be exact.
    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "transaction_terms_integrity_failed"


def test_quote_expiry_after_approval_blocks_provider_claim(container, monkeypatch):
    enable_transactions(container)
    owner = account(container, "tx05-expired-before-claim")
    confirmed = reviewed_transaction(
        container,
        owner,
        "tx05-expired-before-claim",
        expires_minutes=1,
    )
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

    # Keep the approved snapshot hash valid; simulate expiry without rewriting it.
    # The action execution TTL is three minutes, so advance by only two.
    future = utcnow() + timedelta(minutes=2)
    monkeypatch.setattr("services.coworker.action_repository.utcnow", lambda: future)

    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "transaction_quote_expired"
