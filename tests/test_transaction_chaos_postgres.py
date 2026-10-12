"""CW-02: PostgreSQL fault boundaries for one reviewed transaction execution.

These tests use a real dedicated PostgreSQL database. Provider dispatch is NOT
performed and they do not certify Temporal, network faults, or staging providers.
"""
from __future__ import annotations

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")
pytestmark = [
    pytest.mark.coworker_integration,
    pytest.mark.skipif(
        not os.getenv("SHUDDHO_TEST_POSTGRES_URL"),
        reason="Dedicated PostgreSQL test database required",
    ),
]

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from action_samples import connected
from test_coworker_postgres import owner, repository
from test_personal_transactions import payload as commitment_payload
from test_transaction_reconciliation import bound_action, reviewed_transaction

from services.coworker.action_repository import ActionRepository
from services.coworker.action_schemas import ActionPrepare
from services.coworker.errors import CoworkerError
from services.coworker.models import ExternalAction, TransactionExecutionLink, utcnow
from services.coworker.transaction_repository import TransactionRepository


def transaction_services(repository):
    """Wire production repositories to the *real* test PostgreSQL session pool."""
    settings = replace(
        repository.settings,
        actions_enabled=True,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        transaction_operations=frozenset({"google:negotiation_commitment_email"}),
        connector_encryption_key=base64.urlsafe_b64encode(bytes([0x22]) * 32).decode(),
    )
    settings.validate()
    return SimpleNamespace(
        actions=SimpleNamespace(repo=ActionRepository(repository.sessions, settings)),
        transactions=TransactionRepository(repository.sessions, settings),
    )


def reviewed_bound(repository, key):
    services = transaction_services(repository)
    identity = owner(repository)
    review = reviewed_transaction(services, identity, key)
    action, link = bound_action(services, identity, review, key + "-action")
    return services, identity, review, action, link


def test_postgres_parallel_duplicate_bind_and_claim_once(repository):
    services, identity, review, action, linked = reviewed_bound(repository, "cw02-postgres-replay")
    binding = review["review_binding"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        replays = list(pool.map(
            lambda _: services.transactions.bind_external_action(
                identity, binding["transaction_id"], binding["transaction_revision"], action["id"],
            ),
            range(6),
        ))
    assert all(result == linked for result in replays)
    services.actions.repo.approve(identity, action["id"], action["preview_hash"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: services.actions.repo.claim_execution(action["id"]), range(6)))
    assert sum(result is not None for result in claims) == 1
    assert services.actions.repo.claim_execution(action["id"]) is None
    with repository.sessions() as db:
        assert db.scalar(select(func.count()).select_from(TransactionExecutionLink).where(
            TransactionExecutionLink.transaction_id == binding["transaction_id"],
        )) == 1


def test_postgres_different_action_cannot_steal_reviewed_transaction(repository):
    services, identity, review, action, _ = reviewed_bound(repository, "cw02-postgres-conflict")
    binding = review["review_binding"]
    connection = connected(services.actions.repo, identity, "email")
    second = services.actions.repo.prepare(
        identity,
        ActionPrepare.model_validate({
            "connection_id": connection["id"],
            "payload": commitment_payload(),
        }),
        "cw02-postgres-another-action",
        transaction_binding={
            "transaction_id": binding["transaction_id"],
            "transaction_revision": binding["transaction_revision"],
            "terms_revision": binding["terms_revision"],
            "terms_sha256": binding["terms_sha256"],
        },
    )
    with pytest.raises(CoworkerError) as conflict:
        services.transactions.bind_external_action(
            identity, binding["transaction_id"], binding["transaction_revision"], second["id"],
        )
    assert conflict.value.code == "transaction_execution_already_bound"
    with pytest.raises(CoworkerError) as unbound:
        services.actions.repo.approve(identity, second["id"], second["preview_hash"])
    assert unbound.value.code == "transaction_action_binding_changed"
    assert services.actions.repo.claim_execution(second["id"]) is None


@pytest.mark.parametrize("approve_first", [False, True])
def test_postgres_expired_approval_or_claim_has_no_execution( repository, approve_first):
    services, identity, _review, action, _ = reviewed_bound(repository, "cw02-expiry-" + str(approve_first))
    if approve_first:
        services.actions.repo.approve(identity, action["id"], action["preview_hash"])
    with repository.sessions.begin() as db:
        db.get(ExternalAction, action["id"]).expires_at = utcnow() - timedelta(seconds=2)
    if approve_first:
        assert services.actions.repo.claim_execution(action["id"]) is None
    else:
        with pytest.raises(CoworkerError) as denied:
            services.actions.repo.approve(identity, action["id"], action["preview_hash"])
        assert denied.value.code == "approval_expired"
    with repository.sessions() as db:
        assert db.get(ExternalAction, action["id"]).state in {"awaiting_approval", "expired"}


def test_postgres_terminated_backend_rolls_back_uncommitted_claim(repository):
    """A killed PG session cannot commit a partial execution claim.

    Kill only this test's selected PostgreSQL backend, NOT the server or any
    other process. A provider was never contacted in this test.
    """
    services, identity, _review, action, _ = reviewed_bound(repository, "cw02-backend-lost")
    services.actions.repo.approve(identity, action["id"], action["preview_hash"])
    engine = repository.sessions.kw["bind"]
    with pytest.raises(DBAPIError):
        with repository.sessions.begin() as db:
            row = db.scalar(
                select(ExternalAction).where(ExternalAction.id == action["id"]).with_for_update()
            )
            assert row.state == "queued"
            row.state = "executing"
            db.flush()
            pid = db.scalar(text("SELECT pg_backend_pid()"))
            with engine.connect() as killer:
                assert killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}) is True
            db.execute(text("SELECT 1"))
    # This is a pre-commit fault: the database must have rolled back the claim.
    with repository.sessions() as db:
        assert db.get(ExternalAction, action["id"]).state == "queued"
    assert services.actions.repo.claim_execution(action["id"]) is not None
    assert services.actions.repo.claim_execution(action["id"]) is None
