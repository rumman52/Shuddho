"""Fail closed when the PA-10 staging database is expired or near free-tier expiry.

This read-only admission guard prevents a staging preflight/provisioning job from
starting work against a database that may expire before qualification completes.
It does not back up, upgrade, migrate, or mutate any Render resource.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone


class DatabaseExpiryGateError(ValueError):
    """The database lifecycle metadata is unsafe or cannot be qualified."""


# Current Render CLI/API Postgres plan identifiers. Keep this explicit so a new
# or malformed plan value cannot bypass expiry verification by looking paid.
KNOWN_PLANS = frozenset({
    "free", "starter", "standard", "pro", "pro_plus", "custom",
    "basic_256mb", "basic_1gb", "basic_4gb",
    "pro_4gb", "pro_8gb", "pro_16gb", "pro_32gb", "pro_64gb",
    "pro_128gb", "pro_192gb", "pro_256gb", "pro_384gb", "pro_512gb",
    "accelerated_16gb", "accelerated_32gb", "accelerated_64gb",
    "accelerated_128gb", "accelerated_256gb", "accelerated_384gb",
    "accelerated_512gb", "accelerated_768gb", "accelerated_1024gb",
    "0.1c-256mb", "0.5c-1g", "1c-2g", "1c-4g", "2c-4g",
    "2c-8g", "2c-16g", "4c-16g", "4c-32g", "8c-32g",
    "8c-64g", "16c-64g", "16c-128g", "32c-128g", "32c-256g",
    "48c-192g", "48c-384g", "64c-256g", "64c-512g",
    "96c-384g", "96c-768g", "128c-512g", "128c-1024g",
})
NON_EXPIRING_PLANS = KNOWN_PLANS - {"free", "custom"}


def _parse_expiry(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DatabaseExpiryGateError("database expiry timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise DatabaseExpiryGateError("database expiry timestamp is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatabaseExpiryGateError("database expiry timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def check_database_lifecycle(
    plan: str,
    expires_at: str | None,
    *,
    now: datetime | None = None,
    minimum_remaining_days: int = 7,
) -> dict:
    """Return non-secret lifecycle evidence or fail closed before provider access."""
    if not isinstance(plan, str) or not plan.strip():
        raise DatabaseExpiryGateError("Render database plan is missing")
    if type(minimum_remaining_days) is not int or not 1 <= minimum_remaining_days <= 365:
        raise DatabaseExpiryGateError("minimum remaining days must be an integer in 1..365")

    normalized_plan = plan.strip().lower()
    if normalized_plan not in KNOWN_PLANS:
        raise DatabaseExpiryGateError(
            "Render database plan is unrecognized; current plan metadata requires review"
        )
    if expires_at is None or (isinstance(expires_at, str) and not expires_at.strip()):
        if normalized_plan == "free":
            raise DatabaseExpiryGateError(
                "free-tier database expiry is unavailable; retention cannot be verified"
            )
        if normalized_plan not in NON_EXPIRING_PLANS:
            raise DatabaseExpiryGateError(
                "custom database plan expiry is unavailable; retention cannot be verified"
            )
        return {
            "status": "no_expiry",
            "plan": normalized_plan,
            "expires_at": None,
            "minimum_remaining_days": minimum_remaining_days,
        }

    expiry = _parse_expiry(expires_at)
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
        raise DatabaseExpiryGateError("current time must be timezone-aware")
    remaining = expiry - current.astimezone(timezone.utc)
    if remaining <= timedelta(0):
        raise DatabaseExpiryGateError("staging database has already expired")
    if remaining <= timedelta(days=minimum_remaining_days):
        raise DatabaseExpiryGateError(
            "staging database expires within the "
            f"{minimum_remaining_days}-day safety window; approved backup and retention action required"
        )

    return {
        "status": "clear",
        "plan": normalized_plan,
        "expires_at": expiry.isoformat(),
        "minimum_remaining_days": minimum_remaining_days,
        "remaining_seconds": int(remaining.total_seconds()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--expires-at", default="")
    parser.add_argument("--minimum-remaining-days", type=int, default=7)
    args = parser.parse_args()
    try:
        evidence = check_database_lifecycle(
            args.plan,
            args.expires_at,
            minimum_remaining_days=args.minimum_remaining_days,
        )
    except DatabaseExpiryGateError as exc:
        parser.exit(1, f"PA-10 database lifecycle gate BLOCKED: {exc}\n")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
