"""CW-02 real HTTP/process recovery; PostgreSQL + Temporal are mandatory in CI.

Local SQLite runs are useful process/transport checks, not PostgreSQL or live
provider qualification. The provider simulator never contacts an external API.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from coworker_worker_helpers import dispatch_tick
import httpx

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from test_coworker import container, signed_client
from test_coworker_postgres import repository
from test_permission_gateway import enable_boundary
from test_transaction_api import create_payload, terms_payload
from test_transaction_reconciliation import bound_action, enable_transactions
from transaction_process_harness import (
    BOUNDARIES, CONTEXT, CountedProvider, WorkerProcesses, require_disposable_database, service_for,
)
from services.coworker.action_registry import stable_digest
from services.coworker.container import Container
from services.coworker.database import session_factory


@pytest.fixture
def transaction_container(request, tmp_path):
    required = os.getenv("SHUDDHO_TRANSACTION_CHAOS_POSTGRES_REQUIRED") == "true"
    if os.getenv("SHUDDHO_TEST_POSTGRES_URL"):
        # Validate the target BEFORE the shared fixture can run migrations.
        preflight = session_factory(os.environ["SHUDDHO_TEST_POSTGRES_URL"])
        try:
            require_disposable_database(preflight, postgres_required=True)
        finally:
            preflight.kw["bind"].dispose()
        repo = request.getfixturevalue("repository")
        require_disposable_database(repo.sessions, postgres_required=True)
        settings = replace(repo.settings, local_storage_path=tmp_path / "objects",
                           task_queue="cw02-process-" + uuid4().hex)
        value = Container.create(settings)
        request.addfinalizer(value.repository.sessions.kw["bind"].dispose)
    else:
        value = request.getfixturevalue("container")
        require_disposable_database(value.repository.sessions, postgres_required=required)
        value.settings = replace(value.settings, task_queue="cw02-process-" + uuid4().hex)
    enable_transactions(value)
    enable_boundary(value)
    # These fixtures are explicitly synthetic and cannot activate production.
    assert value.settings.environment == "development"
    return value


@pytest.fixture
def processes():
    value = WorkerProcesses()
    yield value
    value.close()


@pytest.fixture
def provider(request):
    options = getattr(request, "param", {})
    value = CountedProvider(**options)
    yield value
    value.close()


def reviewed_action(value, key):
    """Use the authenticated public review/approval boundary, not invented rows."""
    # Reuse the project's real JWT verifier/public API fixture with this backend.
    fixture = signed_client.__wrapped__(value)
    client, headers = next(fixture)
    try:
        auth = headers("cw02-" + key)
        owner = client.get("/api/v1/me", headers=auth).json()["account_id"]
        created = client.post("/api/v1/transactions", json=create_payload(),
                              headers=auth | {"Idempotency-Key": key})
        assert created.status_code == 201
        identity = created.json()["id"]
        saved = client.put(f"/api/v1/transactions/{identity}/terms", headers=auth, json=terms_payload())
        assert saved.status_code == 200
        reviewed = client.post(f"/api/v1/transactions/{identity}/review", headers=auth,
                               json={"expected_revision": saved.json()["transaction"]["revision"]})
        assert reviewed.status_code == 200
        confirmed = client.post(f"/api/v1/transactions/{identity}/review/confirm", headers=auth, json={
            "expected_revision": reviewed.json()["revision"],
            "terms_sha256": saved.json()["terms"]["terms_sha256"],
        })
        assert confirmed.status_code == 200
        action, _link = bound_action(value, owner, confirmed.json(), key + "-action")
        approval = client.post(f'/api/v1/actions/{action["id"]}/approve', headers=auth,
                               json={"preview_hash": action["preview_hash"]})
        assert approval.status_code == 202
        return owner, identity, action
    finally:
        fixture.close()


def assert_evidence(value, provider, owner, transaction_id, action, expected_state,
                    expected_count, record_property, case_id):
    surface = value.transactions.sync_external_action(owner, transaction_id)
    assert surface["transaction"]["state"] == (
        "confirmed" if expected_state == "succeeded" else expected_state
    )
    saved = value.actions.repo.get(owner, action["id"])
    assert saved["state"] == expected_state
    dispatches, mutations, identities = provider.counts()
    assert (dispatches, mutations) == expected_count
    assert identities == [action["id"]] * mutations
    assert saved["preview_hash"] == action["preview_hash"]
    if expected_state == "succeeded":
        assert surface["evidence"]["receipt"]["provider_id"] == "mail-1"
        assert len(surface["evidence"]["receipt_sha256"]) == 64
    else:
        assert surface["evidence"]["receipt"] is None
    assert value.actions.repo.claim_execution(action["id"]) is None
    record_property("transaction_case", json.dumps({
        "schema_version": 1, "evidence_level": "integration_simulated_provider",
        "case_id": case_id, "action_id": action["id"], "approved_identity": action["preview_hash"],
        "source_revision": os.getenv("SHUDDHO_TRANSACTION_CHAOS_SOURCE_REVISION", "local-working-tree"),
        "database": value.repository.sessions.kw["bind"].dialect.name,
        "provider_dispatch_count": dispatches, "provider_mutation_count": mutations,
        "state": expected_state,
        "receipt_sha256": stable_digest(saved["receipt"]) if saved["receipt"] else None,
    }, sort_keys=True))


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_transaction_hard_worker_loss_and_new_pool_recovery(
    transaction_container, processes, provider, boundary, record_property,
):
    value = transaction_container
    owner, transaction_id, action = reviewed_action(value, "process-" + boundary)
    provider.hold_after_apply = boundary == "after_provider_apply"
    process, entered = processes.start(value.settings, provider.origin, action["id"], boundary)
    barrier = provider.applied if boundary == "after_provider_apply" else entered
    assert barrier.wait(25), "Worker never reached the actual dispatch/commit boundary"
    processes.kill(process)
    before = value.actions.repo.get(owner, action["id"])
    assert before["state"] == {
        "before_claim": "queued", "after_claim": "executing",
        "after_provider_apply": "executing", "after_receipt_commit": "succeeded",
    }[boundary]
    provider.release.set()
    restart, _ = processes.start(value.settings, provider.origin, action["id"])
    restart.join(25)
    assert not restart.is_alive() and restart.exitcode == 0
    expected_state = "succeeded" if boundary in {"before_claim", "after_receipt_commit"} else "outcome_unknown"
    expected_count = (0, 0) if boundary == "after_claim" else (1, 1)
    assert_evidence(value, provider, owner, transaction_id, action, expected_state,
                    expected_count, record_property, "worker_crash:" + boundary)


@pytest.mark.parametrize("provider, expected_state, expected_count", [
    ({"fault": "provider_401"}, "failed", (1, 0)),
    ({"fault": "provider_403"}, "failed", (1, 0)),
    ({"fault": "provider_429"}, "failed", (1, 0)),
    ({"fault": "provider_500"}, "outcome_unknown", (1, 1)),
    ({"fault": "malformed_response"}, "outcome_unknown", (1, 1)),
    ({"fault": "lost_provider_response"}, "outcome_unknown", (1, 1)),
], indirect=["provider"])
def test_http_provider_failure_and_repeated_recovery_never_resend(
    transaction_container, provider, expected_state, expected_count, record_property,
):
    value = transaction_container
    owner, transaction_id, action = reviewed_action(value, "http-" + provider.fault)
    service = service_for(value.settings, value.repository.sessions, provider.origin)
    for _ in range(3):
        asyncio.run(service.execute(action["id"]))
    assert_evidence(value, provider, owner, transaction_id, action, expected_state,
                    expected_count, record_property, provider.fault)


@pytest.mark.parametrize("boundary", BOUNDARIES)
@pytest.mark.skipif(os.getenv("SHUDDHO_TEMPORAL_TESTS") != "true", reason="Real Temporal test server required")
def test_transaction_temporal_activity_recovery_after_worker_sigkill(
    transaction_container, processes, provider, boundary, record_property,
):
    from datetime import timedelta
    from temporalio.testing import WorkflowEnvironment
    from services.coworker.workflow import ApprovedActionWorkflow

    async def scenario():
        value = transaction_container
        owner, transaction_id, action = reviewed_action(value, "temporal-" + boundary)
        provider.hold_after_apply = boundary == "after_provider_apply"
        async with await WorkflowEnvironment.start_time_skipping() as env:
            address = env.client.service_client.config.target_host
            process, entered = processes.start(value.settings, provider.origin, action["id"], boundary, address)
            handle = await env.client.start_workflow(
                ApprovedActionWorkflow.run, action["id"], id="shuddho-action-" + action["id"],
                task_queue=value.settings.task_queue, execution_timeout=timedelta(minutes=5),
            )
            barrier = provider.applied if boundary == "after_provider_apply" else entered
            assert await asyncio.to_thread(barrier.wait, 25)
            processes.kill(process)
            provider.release.set()
            polling_gate = CONTEXT.Event()
            processes.start(value.settings, provider.origin, action["id"],
                            temporal_address=address, polling_gate=polling_gate)
            history = await handle.fetch_history()
            scheduled = next(event.activity_task_scheduled_event_attributes
                             for event in history.events
                             if event.HasField("activity_task_scheduled_event_attributes"))
            retry_after = (scheduled.start_to_close_timeout.ToTimedelta()
                           + scheduled.retry_policy.initial_interval.ToTimedelta())
            # SIGKILL leaves the activity unacknowledged. Advance its timeout
            # and first retry only, with the restart deliberately not polling.
            # An unbounded result() unlock can race all the way to the workflow
            # deadline before a newly spawned worker receives its first task.
            # The killed activity retains a test-server time lock: sleep alone
            # blocks in real time. Balance that extra unlock around the bounded
            # sleep, then keep the clock locked throughout restarted polling.
            async with env.time_skipping_unlocked():
                await asyncio.wait_for(env.sleep(retry_after), 20)
            polling_gate.set()
            with env.auto_time_skipping_disabled():
                await asyncio.wait_for(handle.result(), 35)
            expected_state = "succeeded" if boundary in {"before_claim", "after_receipt_commit"} else "outcome_unknown"
            expected_count = (0, 0) if boundary == "after_claim" else (1, 1)
            assert_evidence(value, provider, owner, transaction_id, action, expected_state,
                            expected_count, record_property, "temporal_worker_crash:" + boundary)
            history = (await handle.fetch_history()).to_json()
            for private in ("simulated-access-token", "simulated-refresh-token", "alice@example.test", "Example Hotel"):
                assert private not in history

    asyncio.run(scenario())


def test_public_duplicate_transaction_creation_race_is_one_owned_identity(transaction_container):
    # SQLite ignores FOR UPDATE and cannot prove PostgreSQL admission races.
    # Required CI preflight forbids that fallback before reaching this test.
    if transaction_container.repository.sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Concurrent transaction admission requires real PostgreSQL row locks")
    fixture = signed_client.__wrapped__(transaction_container)
    client, headers = next(fixture)
    try:
        auth = headers("cw02-api-race")
        payload = create_payload()
        key = "cw02-public-race-" + uuid4().hex
        barrier = Barrier(6)
        def submit(_index):
            barrier.wait(10)
            return client.post("/api/v1/transactions", json=payload,
                               headers=auth | {"Idempotency-Key": key})
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(submit, range(6)))
        assert all(response.status_code == 201 for response in responses)
        assert len({response.json()["id"] for response in responses}) == 1
        assert sum(response.headers["idempotent-replayed"] == "false" for response in responses) == 1
        changed = client.post("/api/v1/transactions", json=payload | {"counterparty": "Different Hotel"},
                              headers=auth | {"Idempotency-Key": key})
        assert changed.status_code == 409 and changed.json()["error"]["code"] == "idempotency_conflict"
        hidden = client.get("/api/v1/transactions/" + responses[0].json()["id"], headers=headers("other"))
        assert hidden.status_code == 404
    finally:
        fixture.close()


def test_hard_api_loss_after_commit_replays_same_public_transaction(transaction_container, processes, provider):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from services.coworker.auth import Principal

    value = transaction_container
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {
        "kid": "cw02-api-crash-key", "alg": "RS256", "use": "sig",
    }
    subject = "cw02-api-crash-" + uuid4().hex
    claims = {"iss": value.settings.auth_issuer, "sub": subject, "aud": value.settings.auth_audience,
              "role": "authenticated", "iat": int(time.time()) - 1, "exp": int(time.time()) + 3600}
    auth = {
        "Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256", headers={"kid": public_jwk["kid"]}),
    }
    owner = Principal(claims["iss"], subject, claims["exp"]).account_id
    request_key = "cw02-api-loss-" + uuid4().hex
    payload = create_payload()
    process, origin = processes.start_api(value.settings, public_jwk, request_key)
    with httpx.Client(trust_env=False, timeout=10) as client:
        with pytest.raises(httpx.HTTPError):
            client.post(origin + "/api/v1/transactions", json=payload,
                        headers=auth | {"Idempotency-Key": request_key})
    process.join(10)
    assert process.exitcode == 87, "Fault must occur after create committed, not at startup"
    saved = value.transactions.list(owner)
    assert len(saved) == 1 and saved[0]["state"] == "draft"
    _restart, resumed = processes.start_api(value.settings, public_jwk)
    with httpx.Client(trust_env=False, timeout=10) as client:
        replay = client.post(resumed + "/api/v1/transactions", json=payload,
                             headers=auth | {"Idempotency-Key": request_key})
        assert replay.status_code == 201 and replay.json()["id"] == saved[0]["id"]
        assert replay.headers["idempotent-replayed"] == "true"
        changed = client.post(resumed + "/api/v1/transactions", json=payload | {"counterparty": "Changed Hotel"},
                              headers=auth | {"Idempotency-Key": request_key})
        assert changed.status_code == 409
    assert provider.counts() == (0, 0, [])
    assert len(value.transactions.list(owner)) == 1


@pytest.mark.skipif(os.getenv("SHUDDHO_TEMPORAL_TESTS") != "true", reason="Real Temporal test server required")
def test_temporal_server_outage_preserves_approved_outbox_until_recovery(
    transaction_container, processes, provider, monkeypatch, record_property,
):
    from datetime import timedelta
    from temporalio.service import RPCError
    from temporalio.testing import WorkflowEnvironment
    from services.coworker.models import ExternalAction, utcnow

    async def scenario():
        value = transaction_container
        owner, transaction_id, action = reviewed_action(value, "temporal-outage")
        claim_outbox = value.actions.repo.claim_outbox
        # Target only this fixture's action; other PostgreSQL fixtures share the
        # disposable CI database and must not acquire workflows in this test.
        def claim_target_action(*, worker_id=None):
            identities = claim_outbox(worker_id=worker_id)
            # The repository claims atomically before this test filter runs.
            # Release every unrelated test-fixture claim without dispatching it.
            for identity in identities:
                if identity != action["id"] and worker_id is not None:
                    value.repository.complete_worker_claim(
                        worker_id=worker_id,
                        claim_type="action_dispatch",
                        resource_id=identity,
                    )
            return [identity for identity in identities if identity == action["id"]]
        monkeypatch.setattr(value.actions.repo, "claim_outbox", claim_target_action)
        async with await WorkflowEnvironment.start_time_skipping() as stopped:
            stopped_client = stopped.client
        # The server really exited; this is not an exception-only client mock.
        with pytest.raises(RPCError):
            await asyncio.wait_for(dispatch_tick(value, stopped_client), 15)
        with value.repository.sessions.begin() as db:
            row = db.get(ExternalAction, action["id"])
            assert row.state == "queued" and row.delivered is False and row.started_at is None
            # Advance only this expired dispatch lease rather than sleeping.
            row.lease_until = utcnow() - timedelta(seconds=1)
        assert provider.counts() == (0, 0, [])
        async with await WorkflowEnvironment.start_time_skipping() as recovered:
            processes.start(value.settings, provider.origin, action["id"],
                            temporal_address=recovered.client.service_client.config.target_host)
            await dispatch_tick(value, recovered.client)
            handle = recovered.client.get_workflow_handle("shuddho-action-" + action["id"])
            with recovered.auto_time_skipping_disabled():
                await asyncio.wait_for(handle.result(), 30)
        assert_evidence(value, provider, owner, transaction_id, action, "succeeded", (1, 1),
                        record_property, "temporal_outage")
        assert value.actions.repo.get(owner, action["id"])["state"] == "succeeded"

    asyncio.run(scenario())


@pytest.mark.skipif(os.getenv("SHUDDHO_TEMPORAL_TESTS") != "true", reason="Real Temporal test server required")
def test_postgres_backend_disconnect_after_provider_acceptance_never_resends(
    transaction_container, provider, record_property,
):
    """A real PostgreSQL backend loss at receipt persistence cannot resend a provider mutation."""
    import threading

    from sqlalchemy import event, text
    from temporalio.testing import WorkflowEnvironment
    from test_coworker import FakeModel
    from test_coworker_temporal import make_worker
    from services.coworker.runner import DocumentRunner

    async def scenario():
        value = transaction_container
        engine = value.repository.sessions.kw["bind"]
        if engine.dialect.name != "postgresql":
            pytest.skip("Post-mutation database disconnect qualification requires PostgreSQL")

        owner, _transaction_id, action = reviewed_action(value, "database-disconnect-after-provider")
        service = service_for(value.settings, value.repository.sessions, provider.origin)
        value.actions = service
        adapter = service.providers["google"]
        original_execute = adapter.execute
        original_service_execute = service.execute
        fault = {"armed": False, "injected": False}
        fault_lock = threading.Lock()
        execution_attempts = []

        async def tracked_service_execute(identity):
            with fault_lock:
                execution_attempts.append((identity, fault["injected"]))
            return await original_service_execute(identity)

        def assert_disposable_loopback_backend(sa_connection):
            # Guard the destructive backend-termination call using both SQLAlchemy's
            # configured URL and libpq's effective connection details. In libpq,
            # query-string/environment connection parameters can override the URL host.
            from ipaddress import ip_address

            url = engine.url
            target_overrides = {
                "host", "hostaddr", "port", "service", "servicefile",
                "dbname", "user", "replication", "target_session_attrs",
                "load_balance_hosts",
            }
            assert not (target_overrides & {str(key).lower() for key in url.query}), (
                "Refusing backend termination when PostgreSQL URL query overrides "
                "connection-target parameters"
            )
            assert (
                engine.dialect.name == "postgresql"
                and url.host in {"localhost", "127.0.0.1"}
                and url.database == "shuddho_coworker_test"
                and url.username == "shuddho_test"
            ), "Fault injection requires the configured disposable loopback CI PostgreSQL URL"

            info = sa_connection.connection.driver_connection.info
            assert info.host in {"localhost", "127.0.0.1"}, (
                "Refusing backend termination: effective PostgreSQL host is not loopback"
            )
            if info.hostaddr:
                assert ip_address(info.hostaddr).is_loopback, (
                    "Refusing backend termination: effective PostgreSQL hostaddr is not loopback"
                )
            expected_port = url.port if url.port is not None else 5432
            assert int(info.port) == expected_port, (
                "Refusing backend termination: effective PostgreSQL port differs from the URL"
            )
            assert (info.dbname, info.user) == (
                "shuddho_coworker_test", "shuddho_test"
            ), "Fault injection requires the disposable CI PostgreSQL database and role"

        def terminate_receipt_write(connection, cursor, statement, parameters, context, executemany):
            normalized = statement.lstrip().upper()
            if not normalized.startswith("UPDATE") or "CW_EXTERNAL_ACTIONS" not in normalized:
                return
            if action["id"] not in str(parameters):
                return
            with fault_lock:
                if not fault["armed"] or fault["injected"]:
                    return
                fault["armed"] = False

            # Validate the active write connection and the separate control connection
            # immediately before pg_terminate_backend. Reject host/hostaddr/service
            # overrides and verify libpq's effective endpoint, not only url.host.
            assert_disposable_loopback_backend(connection)
            pid = connection.connection.driver_connection.info.backend_pid
            with engine.connect() as killer:
                assert_disposable_loopback_backend(killer)
                database_name, database_role = killer.execute(
                    text("SELECT current_database(), current_user")
                ).one()
                assert (database_name, database_role) == (
                    "shuddho_coworker_test", "shuddho_test"
                ), "Fault injection requires the disposable CI PostgreSQL database and role"
                assert killer.scalar(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                ) is True
                deadline = time.monotonic() + 5
                while killer.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid = :pid)"),
                    {"pid": pid},
                ):
                    if time.monotonic() >= deadline:
                        raise AssertionError("Target PostgreSQL backend did not terminate")
                    time.sleep(0.01)
            with fault_lock:
                fault["injected"] = True

        async def execute_then_arm(*args, **kwargs):
            receipt = await original_execute(*args, **kwargs)
            # The provider has accepted the send; inject the disconnect only
            # when the worker tries to persist the resulting action receipt.
            with fault_lock:
                fault["armed"] = True
            return receipt

        service.execute = tracked_service_execute
        adapter.execute = execute_then_arm
        event.listen(engine, "before_cursor_execute", terminate_receipt_write)
        try:
            async with await WorkflowEnvironment.start_time_skipping() as env:
                async with make_worker(env, DocumentRunner(value, FakeModel())):
                    await dispatch_tick(value, env.client)
                    handle = env.client.get_workflow_handle("shuddho-action-" + action["id"])
                    async with env.time_skipping_unlocked():
                        await asyncio.wait_for(handle.result(), 35)
        finally:
            event.remove(engine, "before_cursor_execute", terminate_receipt_write)
            adapter.execute = original_execute
            service.execute = original_service_execute

        saved = service.repo.get(owner, action["id"])
        assert fault["injected"] is True, "The targeted PostgreSQL receipt write was not interrupted"
        assert len(execution_attempts) >= 2, (
            "The Temporal execution activity did not retry after the receipt-write disconnect"
        )
        assert execution_attempts[0] == (action["id"], False)
        assert any(identity == action["id"] and injected for identity, injected in execution_attempts[1:]), (
            "No execution activity attempt was observed after the injected PostgreSQL disconnect"
        )
        # This send-only email connector cannot prove whether the provider applied
        # the effect after receipt persistence failed, so uncertainty must be retained.
        assert saved["state"] == "outcome_unknown"
        assert saved["receipt"] is None
        assert provider.counts() == (1, 1, [action["id"]])
        record_property("transaction_case", json.dumps({
            "schema_version": 1,
            "evidence_level": "postgres_temporal_loopback_provider",
            "case_id": "database_disconnect_after_provider_acceptance",
            "action_id": action["id"],
            "approved_identity": action["preview_hash"],
            "source_revision": os.getenv("SHUDDHO_TRANSACTION_CHAOS_SOURCE_REVISION", "local-working-tree"),
            "database": engine.dialect.name,
            "postgres_backend_terminated": fault["injected"],
            "execution_activity_attempts": len(execution_attempts),
            "retry_after_disconnect_observed": any(
                identity == action["id"] and injected
                for identity, injected in execution_attempts[1:]
            ),
            "provider_dispatch_count": provider.counts()[0],
            "provider_mutation_count": provider.counts()[1],
            "state": saved["state"],
            "receipt_sha256": None,
        }, sort_keys=True))

    asyncio.run(scenario())
