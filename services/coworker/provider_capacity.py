from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, func, select, text

from .errors import CoworkerError
from .models import ProviderDailyUsage, ProviderLease, utcnow


# One transaction-wide lock serializes capacity admission across all worker replicas.
# PostgreSQL advisory locks are scoped to this database connection/transaction and
# require no external Redis/control-plane dependency.
PROVIDER_ADMISSION_LOCK = 674231989144703


def lease_key(kind: str, resource_id: str, sequence: int) -> str:
    if kind not in {"draft", "planner"}:
        raise ValueError("Unsupported provider lease kind.")
    if not resource_id or sequence < 1:
        raise ValueError("Provider lease resource and sequence are required.")
    return f"{kind}:{resource_id}:{sequence}"


def _serialize(db) -> None:
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": PROVIDER_ADMISSION_LOCK},
        )


def _cleanup_expired(db, now) -> int:
    result = db.execute(delete(ProviderLease).where(ProviderLease.expires_at <= now))
    return int(result.rowcount or 0)


def acquire_provider_lease(
    db,
    settings,
    *,
    owner_id: str,
    kind: str,
    resource_id: str,
    sequence: int,
    reserved_tokens: int,
) -> str:
    if not isinstance(reserved_tokens, int) or isinstance(reserved_tokens, bool) or reserved_tokens < 1:
        raise CoworkerError("provider_reservation", "The provider reservation is invalid.", 500)

    key = lease_key(kind, resource_id, sequence)
    now = utcnow()
    _serialize(db)
    _cleanup_expired(db, now)

    existing = db.scalar(
        select(ProviderLease).where(ProviderLease.lease_key == key)
    )
    if existing is not None:
        if existing.owner_id != owner_id or existing.reserved_tokens != reserved_tokens:
            raise CoworkerError("provider_reservation", "The provider reservation could not be recovered.", 409)
        return existing.id

    active_calls = int(db.scalar(select(func.count()).select_from(ProviderLease)) or 0)
    owner_calls = int(db.scalar(
        select(func.count()).select_from(ProviderLease).where(ProviderLease.owner_id == owner_id)
    ) or 0)
    reserved = int(db.scalar(select(func.coalesce(func.sum(ProviderLease.reserved_tokens), 0))) or 0)
    owner_reserved = int(db.scalar(
        select(func.coalesce(func.sum(ProviderLease.reserved_tokens), 0)).where(
            ProviderLease.owner_id == owner_id
        )
    ) or 0)

    day = now.date().isoformat()
    daily = db.get(ProviderDailyUsage, day)
    if daily is None:
        daily = ProviderDailyUsage(day=day, allocated_tokens=0)
        db.add(daily)
        db.flush()
    if daily.allocated_tokens + reserved_tokens > settings.provider_daily_token_budget:
        raise CoworkerError(
            "provider_daily_budget",
            "The shared model budget for today has been reached. Try again later.",
            429,
        )

    if (
        active_calls >= settings.provider_max_concurrent_calls
        or reserved + reserved_tokens > settings.provider_max_reserved_tokens
    ):
        raise CoworkerError(
            "provider_capacity_busy",
            "Model capacity is temporarily busy. This work will retry shortly.",
            429,
        )
    if (
        owner_calls >= settings.provider_max_concurrent_per_workspace
        or owner_reserved + reserved_tokens > settings.provider_max_reserved_tokens_per_workspace
    ):
        raise CoworkerError(
            "workspace_provider_busy",
            "This workspace already has model work in progress. It will retry shortly.",
            429,
        )

    lease = ProviderLease(
        id=str(uuid4()),
        lease_key=key,
        owner_id=owner_id,
        kind=kind,
        resource_id=resource_id,
        sequence=sequence,
        reserved_tokens=reserved_tokens,
        expires_at=now + timedelta(seconds=settings.provider_lease_seconds),
    )
    db.add(lease)
    daily.allocated_tokens += reserved_tokens
    db.flush()
    return lease.id


def settle_provider_lease(
    db,
    *,
    kind: str,
    resource_id: str,
    sequence: int,
    actual_tokens: int | None,
) -> None:
    key = lease_key(kind, resource_id, sequence)
    _serialize(db)
    lease = db.scalar(
        select(ProviderLease).where(ProviderLease.lease_key == key)
    )
    if lease is None:
        return
    charged = (
        actual_tokens
        if isinstance(actual_tokens, int)
        and not isinstance(actual_tokens, bool)
        and actual_tokens >= 0
        else lease.reserved_tokens
    )
    created_at = lease.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    day = created_at.astimezone(timezone.utc).date().isoformat()
    daily = db.get(ProviderDailyUsage, day)
    if daily is None:
        daily = ProviderDailyUsage(day=day, allocated_tokens=lease.reserved_tokens)
        db.add(daily)
        db.flush()
    daily.allocated_tokens += charged - lease.reserved_tokens
    db.delete(lease)


def release_provider_lease(db, *, kind: str, resource_id: str, sequence: int) -> None:
    settle_provider_lease(
        db,
        kind=kind,
        resource_id=resource_id,
        sequence=sequence,
        actual_tokens=None,
    )


def provider_capacity_snapshot(db) -> dict:
    now = utcnow()
    _serialize(db)
    expired = _cleanup_expired(db, now)
    active = int(db.scalar(select(func.count()).select_from(ProviderLease)) or 0)
    reserved = int(db.scalar(select(func.coalesce(func.sum(ProviderLease.reserved_tokens), 0))) or 0)
    daily = db.get(ProviderDailyUsage, now.date().isoformat())
    oldest = db.scalar(select(func.min(ProviderLease.created_at)))
    oldest_age_seconds = 0
    if oldest is not None:
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=now.tzinfo)
        oldest_age_seconds = max(0, int((now - oldest).total_seconds()))
    return {
        "active_calls": active,
        "reserved_tokens": reserved,
        "oldest_lease_age_seconds": oldest_age_seconds,
        "expired_leases_reaped": expired,
        "daily_allocated_tokens": int(daily.allocated_tokens) if daily is not None else 0,
    }
