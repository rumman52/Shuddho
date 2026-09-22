from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select, text

from .errors import CoworkerError
from .models import ProviderLease, utcnow


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

    existing = db.get(ProviderLease, key)
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
    db.flush()
    return lease.id


def release_provider_lease(db, *, kind: str, resource_id: str, sequence: int) -> None:
    key = lease_key(kind, resource_id, sequence)
    _serialize(db)
    db.execute(delete(ProviderLease).where(ProviderLease.lease_key == key))


def provider_capacity_snapshot(db) -> dict:
    now = utcnow()
    _serialize(db)
    expired = _cleanup_expired(db, now)
    active = int(db.scalar(select(func.count()).select_from(ProviderLease)) or 0)
    reserved = int(db.scalar(select(func.coalesce(func.sum(ProviderLease.reserved_tokens), 0))) or 0)
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
    }
