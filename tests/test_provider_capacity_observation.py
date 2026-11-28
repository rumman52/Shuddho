from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from services.coworker import provider_capacity as capacity
from services.coworker.models import Account, Base, ProviderDailyUsage, ProviderLease

NOW = datetime(2026, 11, 28, 8, tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    tables = [model.__table__ for model in (Account, ProviderLease, ProviderDailyUsage)]
    Base.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(capacity, "utcnow", lambda: NOW)
    try:
        with Session(engine) as session:
            session.add(Account(id="owner", issuer="fixture", subject="owner"))
            session.commit()
            yield session
    finally:
        engine.dispose()


def lease(db, ident, *, age, remaining, tokens):
    db.add(ProviderLease(
        id=ident, lease_key=f"draft:{ident}:1", owner_id="owner", kind="draft",
        resource_id=ident, sequence=1, reserved_tokens=tokens,
        created_at=NOW - timedelta(seconds=age), expires_at=NOW + timedelta(seconds=remaining),
    ))


def seed(db):
    lease(db, "expired", age=200, remaining=-1, tokens=100)
    lease(db, "boundary", age=100, remaining=0, tokens=200)
    lease(db, "active", age=20, remaining=10, tokens=30)
    lease(db, "active2", age=10, remaining=20, tokens=70)
    db.add(ProviderDailyUsage(day=NOW.date().isoformat(), allocated_tokens=400))
    db.add(ProviderDailyUsage(day=(NOW.date() - timedelta(days=1)).isoformat(), allocated_tokens=999))
    db.commit()


def test_snapshot_does_not_delete_expired_rows(db):
    seed(db)
    value = capacity.provider_capacity_snapshot(db)
    db.commit()
    assert set(db.scalars(select(ProviderLease.id))) == {"expired", "boundary", "active", "active2"}
    assert value["active_calls"] == 2
    assert value["reserved_tokens"] == 100
    assert value["oldest_lease_age_seconds"] == 20
    assert value["daily_allocated_tokens"] == 400
    assert value["expired_leases_reaped"] == 0
    assert value["expired_leases_observed"] == 2


def test_snapshot_uses_read_only_database_connection(db):
    seed(db)
    db.execute(text("PRAGMA query_only=ON"))
    try:
        assert capacity.provider_capacity_snapshot(db)["active_calls"] == 2
    finally:
        db.rollback()
        db.execute(text("PRAGMA query_only=OFF"))


def test_snapshot_is_one_select_without_admission_lock(db, monkeypatch):
    seed(db)
    statements = []
    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.strip().split()[0].upper())
    def forbid_lock(_db):
        pytest.fail("Observation took the admission lock")
    monkeypatch.setattr(capacity, "_serialize", forbid_lock)
    event.listen(db.bind, "before_cursor_execute", record)
    try:
        capacity.provider_capacity_snapshot(db)
    finally:
        event.remove(db.bind, "before_cursor_execute", record)
    assert statements == ["SELECT"]


def test_snapshot_preserves_late_settlement_accounting(db):
    seed(db)
    capacity.provider_capacity_snapshot(db)
    capacity.settle_provider_lease(db, kind="draft", resource_id="expired", sequence=1, actual_tokens=40)
    db.commit()
    assert db.get(ProviderDailyUsage, NOW.date().isoformat()).allocated_tokens == 340
    assert db.get(ProviderLease, "expired") is None


def test_empty_snapshot_is_measured_zero(db):
    value = capacity.provider_capacity_snapshot(db)
    assert value == {
        "active_calls": 0, "reserved_tokens": 0, "oldest_lease_age_seconds": 0,
        "expired_leases_reaped": 0, "expired_leases_observed": 0, "daily_allocated_tokens": 0,
    }


def test_admission_still_reaps_expired_leases(db):
    seed(db)
    settings = SimpleNamespace(provider_daily_token_budget=1000, provider_max_concurrent_calls=10,
                               provider_max_reserved_tokens=1000, provider_max_concurrent_per_workspace=10,
                               provider_max_reserved_tokens_per_workspace=1000, provider_lease_seconds=60)
    capacity.acquire_provider_lease(db, settings, owner_id="owner", kind="draft",
                                    resource_id="new", sequence=1, reserved_tokens=5)
    db.commit()
    assert db.get(ProviderLease, "expired") is None
    assert db.get(ProviderLease, "boundary") is None
    assert db.get(ProviderDailyUsage, NOW.date().isoformat()).allocated_tokens == 405
