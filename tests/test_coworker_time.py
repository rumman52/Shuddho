"""Shared Coworker UTC helpers must be importable by Fly services.

These tests pin the legacy semantics used by repository/model timestamps:
naive datetimes are interpreted as UTC; aware datetimes are preserved.
"""
from datetime import datetime, timedelta, timezone

from services.coworker.time import aware, utcnow


def test_aware_attaches_utc_to_naive_datetime_without_changing_clock_value():
    value = datetime(2026, 11, 9, 12, 30, 0)

    result = aware(value)

    assert result.replace(tzinfo=None) == value
    assert result.tzinfo is timezone.utc


def test_aware_preserves_an_already_aware_datetime_and_its_offset():
    offset = timezone(timedelta(hours=6))
    value = datetime(2026, 11, 9, 18, 30, 0, tzinfo=offset)

    result = aware(value)

    assert result is value
    assert result.utcoffset() == timedelta(hours=6)


def test_utcnow_returns_timezone_aware_utc_datetime():
    before = datetime.now(timezone.utc)

    result = utcnow()

    after = datetime.now(timezone.utc)
    assert before <= result <= after
    assert result.tzinfo is timezone.utc
