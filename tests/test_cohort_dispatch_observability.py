from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for dispatch observability tests")
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from services.coworker.models import (
    Account, AgentOutbox, AgentRun, Base, Outbox, Task, WorkerClaim, WorkerInstance, Workspace,
)

NOW = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(minutes=15)
QUEUE = "private-fixture-queue"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    tables = [m.__table__ for m in (Account, Workspace, Task, AgentRun, Outbox, AgentOutbox, WorkerInstance, WorkerClaim)]
    Base.metadata.create_all(engine, tables=tables)
    try:
        with Session(engine) as session:
            for owner in ("member", "outsider"):
                session.add(Account(id=owner, issuer="fixture", subject=owner))
            session.flush()
            for owner in ("member", "outsider"):
                session.add(Workspace(id=owner + "-workspace", owner_id=owner))
            session.flush()
            yield session
    finally:
        engine.dispose()


def admission(db, ident, created, *, owner="member", agent=False, outbox=True):
    common = dict(id=ident, owner_id=owner, workspace_id=owner + "-workspace", idempotency_key=ident,
                  fingerprint="f" * 64, output_language="en", created_at=created, deadline_at=NOW + timedelta(hours=1))
    db.add(AgentRun(**common, goal="synthetic") if agent else Task(**common, instruction="synthetic", notes=""))
    db.flush()
    if outbox:
        db.add(AgentOutbox(run_id=ident) if agent else Outbox(task_id=ident))


def worker(db, ident, heartbeat, *, state="running", queue=QUEUE, started=None):
    db.add(WorkerInstance(id=ident, task_queue=queue, source_revision="a" * 40, state=state,
                          started_at=started or CUTOFF, heartbeat_at=heartbeat))
    db.flush()


def claim(db, ident, resource, at, *, agent=False, queue=QUEUE, worker_id="worker", state="completed"):
    db.add(WorkerClaim(id=ident, worker_id=worker_id, task_queue=queue, resource_id=resource,
                       claim_type="agent_dispatch" if agent else "task_dispatch", state=state,
                       claimed_at=at, completed_at=at if state == "completed" else None))


def collect(db):
    from scripts.cohort_dispatch_observability import collect_dispatch_observability
    return collect_dispatch_observability(db, owners=["member"], task_queue=QUEUE, cutoff=CUTOFF, now=NOW)


def test_admission_to_first_claim_scopes_and_deduplicates(db):
    worker(db, "worker", NOW)
    created = NOW - timedelta(seconds=30)
    for ident in ("claimed", "pending", "wrong-queue", "invalid", "future-claim"):
        admission(db, ident, created)
    admission(db, "other-owner", created, owner="outsider")
    admission(db, "inline", created, outbox=False)
    admission(db, "old", CUTOFF - timedelta(seconds=1))
    admission(db, "future", NOW + timedelta(seconds=1))
    admission(db, "agent", created, agent=True)
    claim(db, "first", "claimed", created + timedelta(milliseconds=1500))
    claim(db, "retry", "claimed", created + timedelta(seconds=9), state="active")
    worker(db, "other-worker", NOW, queue="other-queue")
    claim(db, "foreign-queue", "wrong-queue", created, queue="other-queue", worker_id="other-worker")
    claim(db, "early", "invalid", created - timedelta(seconds=1))
    claim(db, "future-clock", "future-claim", NOW + timedelta(seconds=1))
    claim(db, "other-owner-claim", "other-owner", created)
    claim(db, "inline-claim", "inline", created)
    claim(db, "old-claim", "old", CUTOFF)
    claim(db, "agent-claim", "agent", created + timedelta(seconds=3), agent=True)
    db.flush()
    result = collect(db)
    assert result["dispatch"]["tasks"] == {
        "admissions": 5, "samples": 1, "unobserved": 2, "invalid_clock": 2,
        "p50_ms": 1500, "p95_ms": 1500,
    }
    assert result["dispatch"]["agents"] == {
        "admissions": 1, "samples": 1, "unobserved": 0, "invalid_clock": 0,
        "p50_ms": 3000, "p95_ms": 3000,
    }


def test_worker_heartbeat_exact_boundary_and_unknown_clock(db):
    worker(db, "at-ttl", NOW - timedelta(seconds=15))
    worker(db, "stale", NOW - timedelta(seconds=15, microseconds=1))
    worker(db, "future", NOW + timedelta(microseconds=1))
    worker(db, "before-start", NOW - timedelta(seconds=2), started=NOW - timedelta(seconds=1))
    worker(db, "starting", NOW, state="starting")
    worker(db, "draining", NOW, state="draining")
    worker(db, "retired", NOW, state="drained")
    worker(db, "other", NOW, queue="other-queue")
    assert collect(db)["workers"] == {
        "active_rows": 6, "fresh_running": 1, "stale": 1, "invalid_clock": 2,
        "starting": 1, "draining": 1, "oldest_valid_heartbeat_age_seconds": 15,
    }


def test_empty_window_distinguishes_absent_measurement_from_zero(db):
    result = collect(db)
    empty = {"admissions": 0, "samples": 0, "unobserved": 0, "invalid_clock": 0, "p50_ms": None, "p95_ms": None}
    assert result["dispatch"] == {"tasks": empty, "agents": empty}
    assert result["workers"] == {
        "active_rows": 0, "fresh_running": 0, "stale": 0, "invalid_clock": 0,
        "starting": 0, "draining": 0, "oldest_valid_heartbeat_age_seconds": None,
    }


def test_nearest_rank_and_zero_delay(db):
    worker(db, "worker", NOW)
    for i, delay in enumerate((0, 10, 20, 30, 1000)):
        ident = f"task-{i}"
        admission(db, ident, NOW - timedelta(seconds=5))
        claim(db, "claim-" + ident, ident, NOW - timedelta(seconds=5) + timedelta(milliseconds=delay))
    db.flush()
    result = collect(db)["dispatch"]["tasks"]
    assert result["samples"] == 5
    assert result["p50_ms"] == 20
    assert result["p95_ms"] == 1000
