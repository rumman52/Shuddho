"""PA-09 binding negotiation commitments through the existing consequential-action ledger."""
import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from action_samples import connected, enable_actions
from test_coworker import account, container

from services.coworker.action_registry import action_spec, validate_approval_scope
from services.coworker.action_schemas import ActionPrepare, NegotiationCommitmentEmail
from services.coworker.errors import CoworkerError
from services.coworker.google_actions import GoogleFailure
from scripts.cohort_release_ledger import (
    PERSONAL_TRANSACTIONS_ARTIFACT_KEYS,
    PERSONAL_TRANSACTIONS_SCHEMA_VERSION,
    sign_entry,
    verify_entries,
)


def payload(**changes):
    value = {
        "kind": "negotiation_commitment_email",
        "to": ["counterparty@example.org"],
        "cc": ["legal@example.org"],
        "bcc": [],
        "subject": "Final commercial terms",
        "body": "We confirm the final terms below and agree to proceed on that basis.",
        "counterparty": "Example Supplier Ltd.",
        "commitment_summary": "Accept the final quoted supply agreement.",
        "terms": [
            {"name": "Price", "value": "USD 5,000"},
            {"name": "Delivery", "value": "30 days"},
            {"name": "Cancellation", "value": "Non-refundable after acceptance"},
        ],
    }
    value.update(changes)
    return value


def enable_transactions(container):
    provider = enable_actions(container)
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
    return provider


def prepare_transaction(container, owner, key="pa09-transaction"):
    connection = connected(container.actions.repo, owner, "email")
    request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": payload(),
    })
    return container.actions.repo.prepare(owner, request, key), connection


def test_personal_transaction_flag_requires_actions_and_trust_boundary(container):
    with pytest.raises(ValueError, match="SHUDDHO_ACTIONS_ENABLED"):
        replace(
            container.settings,
            personal_transactions_enabled=True,
        ).validate()

    enable_actions(container)
    with pytest.raises(ValueError, match="CONNECTOR_TRUST_BOUNDARY"):
        replace(
            container.settings,
            personal_transactions_enabled=True,
        ).validate()


def test_transaction_operation_allowlist_is_fail_closed(container):
    provider = enable_actions(container)

    with pytest.raises(ValueError, match="at least one explicitly qualified"):
        replace(
            container.settings,
            connector_trust_boundary_enabled=True,
            personal_transactions_enabled=True,
        ).validate()

    with pytest.raises(ValueError, match="unregistered operations"):
        replace(
            container.settings,
            connector_trust_boundary_enabled=True,
            personal_transactions_enabled=True,
            transaction_operations=frozenset({"google:not_registered"}),
        ).validate()

    rollback_safe = replace(
        container.settings,
        personal_transactions_enabled=False,
        microsoft_actions_enabled=False,
        transaction_operations=frozenset({"microsoft:negotiation_commitment_email"}),
    )
    rollback_safe.validate()

    with pytest.raises(ValueError, match="Microsoft transaction operations require"):
        replace(
            container.settings,
            connector_trust_boundary_enabled=True,
            personal_transactions_enabled=True,
            transaction_operations=frozenset({"microsoft:negotiation_commitment_email"}),
        ).validate()

    owner = account(container)
    connection = connected(container.actions.repo, owner, "email")
    request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": payload(),
    })
    blocked = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        transaction_operations=frozenset({"microsoft:negotiation_commitment_email"}),
        microsoft_actions_enabled=True,
        microsoft_client_id="client",
        microsoft_client_secret="secret",
        microsoft_redirect_uri="https://app.example.test/oauth/microsoft/callback",
    )
    blocked.validate()
    container.settings = blocked
    container.repository.settings = blocked
    container.actions.repo.settings = blocked
    with pytest.raises(CoworkerError) as denied:
        container.actions.repo.prepare(owner, request, "pa09-operation-denied")
    assert denied.value.code == "personal_transaction_operation_disabled"
    assert provider.sent == []


def test_operation_allowlist_is_rechecked_before_approval(container):
    enable_transactions(container)
    owner = account(container)
    action, _connection = prepare_transaction(
        container,
        owner,
        "pa09-operation-approval-recheck",
    )

    narrowed = replace(
        container.settings,
        transaction_operations=frozenset(),
    )
    container.settings = narrowed
    container.repository.settings = narrowed
    container.actions.repo.settings = narrowed

    with pytest.raises(CoworkerError) as denied:
        container.actions.repo.approve(
            owner,
            action["id"],
            action["preview_hash"],
        )
    assert denied.value.code == "personal_transaction_operation_disabled"
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "awaiting_approval"


def test_operation_allowlist_is_rechecked_before_provider_mutation(container):
    enable_transactions(container)
    owner = account(container)
    action, _connection = prepare_transaction(container, owner, "pa09-operation-recheck")
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])

    narrowed = replace(
        container.settings,
        transaction_operations=frozenset(),
    )
    container.settings = narrowed
    container.repository.settings = narrowed
    container.actions.repo.settings = narrowed
    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "personal_transaction_operation_disabled"


def test_negotiation_schema_requires_one_primary_counterparty_no_bcc_and_unique_terms():
    value = NegotiationCommitmentEmail.model_validate(payload())
    assert value.to == ["counterparty@example.org"]
    assert len(value.terms) == 3

    with pytest.raises(ValidationError, match="exactly one primary counterparty"):
        NegotiationCommitmentEmail.model_validate(
            payload(to=["a@example.org", "b@example.org"])
        )
    with pytest.raises(ValidationError, match="do not allow Bcc"):
        NegotiationCommitmentEmail.model_validate(
            payload(bcc=["hidden@example.org"])
        )
    with pytest.raises(ValidationError, match="unique"):
        NegotiationCommitmentEmail.model_validate(
            payload(terms=[
                {"name": "Price", "value": "USD 5,000"},
                {"name": "price", "value": "USD 4,900"},
            ])
        )


def test_transaction_registry_and_approval_scope_bind_exact_final_terms(container):
    enable_transactions(container)
    owner = account(container)
    action, _connection = prepare_transaction(container, owner)

    spec = action_spec("negotiation_commitment_email", "google")
    assert spec.capability == "email"
    assert spec.transaction_class == "binding_negotiation_commitment"
    assert spec.approval_ttl_seconds == 10 * 60
    assert spec.execution_ttl_seconds == 3 * 60
    assert action["preview"]["version"] == 6
    assert action["preview"]["transaction"] == {
        "class": "binding_negotiation_commitment",
        "approval": "exact_final_terms",
        "changed_terms": "fresh_preview_required",
        "uncertain_outcome": "do_not_retry",
        "provider_idempotency": "provider_specific_only",
    }
    assert action["preview"]["approval_scope"]["contract_version"] == 6
    assert action["preview"]["approval_scope"]["policy"]["transaction"] == action["preview"]["transaction"]
    assert validate_approval_scope(action["preview"]).kind == "negotiation_commitment_email"

    changed = deepcopy(action["preview"])
    changed["payload"]["terms"][0]["value"] = "USD 4,900"
    with pytest.raises(CoworkerError, match="approval scope changed"):
        validate_approval_scope(changed)


def test_transaction_kill_switch_and_idempotency_require_fresh_preview(container):
    enable_actions(container)
    owner = account(container)
    connection = connected(container.actions.repo, owner, "email")
    request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": payload(),
    })
    with pytest.raises(CoworkerError) as disabled:
        container.actions.repo.prepare(owner, request, "pa09-disabled")
    assert disabled.value.code == "personal_transactions_disabled"

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

    prepared = container.actions.repo.prepare(owner, request, "pa09-idempotent")
    assert prepared["state"] == "awaiting_approval"

    changed_request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": payload(terms=[
            {"name": "Price", "value": "USD 4,900"},
            {"name": "Delivery", "value": "30 days"},
        ]),
    })
    with pytest.raises(CoworkerError) as conflict:
        container.actions.repo.prepare(owner, changed_request, "pa09-idempotent")
    assert conflict.value.code == "idempotency_conflict"

    off = replace(settings, personal_transactions_enabled=False)
    container.settings = off
    container.repository.settings = off
    container.actions.repo.settings = off
    with pytest.raises(CoworkerError) as approval_disabled:
        container.actions.repo.approve(owner, prepared["id"], prepared["preview_hash"])
    assert approval_disabled.value.code == "personal_transactions_disabled"


def test_kill_switch_blocks_claim_before_provider_mutation(container):
    enable_transactions(container)
    owner = account(container)
    action, _connection = prepare_transaction(container, owner, "pa09-kill-switch")
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])

    off = replace(container.settings, personal_transactions_enabled=False)
    container.settings = off
    container.repository.settings = off
    container.actions.repo.settings = off

    assert container.actions.repo.claim_execution(approved["id"]) is None
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "personal_transactions_disabled"


def test_google_provider_timeout_after_acceptance_is_never_reclaimed(container):
    provider = enable_transactions(container)
    owner = account(container)
    action, _connection = prepare_transaction(container, owner, "pa09-google")
    approved = container.actions.repo.approve(owner, action["id"], action["preview_hash"])
    claimed = container.actions.repo.claim_execution(approved["id"])
    assert claimed is not None

    provider.lose_reply = True
    with pytest.raises(GoogleFailure):
        asyncio.run(
            container.actions.provider.execute(claimed, "simulated-access-token")
        )
    assert len(provider.sent) == 1

    container.actions.repo.finish(
        approved["id"],
        "outcome_unknown",
        error_code="provider_outcome_unknown",
    )
    assert container.actions.repo.claim_execution(approved["id"]) is None
    assert len(provider.sent) == 1


def test_release_ledger_accepts_exact_pa09_v26_attestation():
    artifact_sha256 = {
        key: str(index + 1) * 64
        for index, key in enumerate(sorted(PERSONAL_TRANSACTIONS_ARTIFACT_KEYS))
    }
    core = {
        "schema_version": PERSONAL_TRANSACTIONS_SCHEMA_VERSION,
        "sequence": 1,
        "created_at": "2026-09-28T10:00:00+00:00",
        "release_id": "coworker-pa09-001",
        "event_type": "personal_transactions_verified",
        "actor_reference": "security-review",
        "change_reference": "pa09-change",
        "current_stage": "canary-5",
        "next_stage": None,
        "artifact_sha256": artifact_sha256,
        "previous_entry_hash": "0" * 64,
    }
    key = b"k" * 32
    entry_hash, tag = sign_entry(core, key)
    result = verify_entries(
        [{**core, "entry_hash": entry_hash, "hmac_sha256": tag}],
        key,
    )
    assert result["verified"] is True
    assert result["entries"] == 1
