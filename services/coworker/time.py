"""Shared UTC datetime helpers for Coworker services.

Keep these semantics stable across model timestamps and service-layer expiry
checks: naive values are interpreted as UTC, while already-aware values are
preserved as supplied.
"""
from __future__ import annotations

from datetime import datetime, timezone


def aware(value: datetime) -> datetime:
    """Attach UTC to a naive datetime; preserve an aware datetime unchanged."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def utcnow() -> datetime:
    """Return the current UTC instant as a timezone-aware datetime."""
    return datetime.now(timezone.utc)
