"""Canonical integrity verification for stored transaction terms snapshots."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from pydantic import ValidationError

from .errors import CoworkerError
from .transaction_schemas import TransactionTermsDraft


def fingerprint_json(value: dict) -> str:
    """Use the repository's stable JSON fingerprint format."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def canonical_terms_payload(request: TransactionTermsDraft) -> dict:
    """Build the exact versioned payload that TX-03 hashes at write time."""
    terms = sorted(
        [{"name": item.name, "value": item.value} for item in request.terms],
        key=lambda item: (item["name"].casefold(), item["name"], item["value"]),
    )
    return {
        "schema_version": 1,
        "terms": terms,
        "price": request.price.model_dump(mode="json"),
        "provider_quote_id": request.provider_quote_id,
        "quoted_at": request.quoted_at.astimezone(timezone.utc).isoformat(),
        "quote_expires_at": request.quote_expires_at.astimezone(timezone.utc).isoformat(),
    }


def _snapshot_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("Stored quote timestamp is not a datetime")
    # SQLite returns timezone-aware columns as naive datetimes. The repository's
    # established convention interprets those persisted UTC values as UTC.
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def verify_stored_terms_snapshot_integrity(snapshot) -> None:
    """Fail closed if persisted terms, price, or redundant columns drift."""
    try:
        request = TransactionTermsDraft.model_validate(
            {
                "terms": snapshot.terms,
                "price": snapshot.price,
                "provider_quote_id": snapshot.provider_quote_id,
                "quoted_at": _snapshot_datetime(snapshot.quoted_at),
                "quote_expires_at": _snapshot_datetime(snapshot.quote_expires_at),
            }
        )
        canonical_payload = canonical_terms_payload(request)
        expected_digest = fingerprint_json(canonical_payload)
    except (ValidationError, AttributeError, TypeError, ValueError, OverflowError):
        raise CoworkerError(
            "transaction_terms_integrity_failed",
            "The stored transaction terms failed integrity verification. Refresh the terms before review or approval.",
            409,
        ) from None

    stored_digest = getattr(snapshot, "terms_sha256", None)
    if (
        not isinstance(stored_digest, str)
        or len(stored_digest) != 64
        or not stored_digest.isascii()
        or not hmac.compare_digest(expected_digest, stored_digest)
        # Pydantic intentionally normalizes user input (trimming text and
        # uppercasing currencies). That normalization is correct on initial
        # write, but must not hide changes to an already-persisted snapshot.
        # The write path stores sorted, fully canonical terms and price.
        or snapshot.terms != canonical_payload["terms"]
        or snapshot.price != canonical_payload["price"]
        or snapshot.provider_quote_id != request.provider_quote_id
        or getattr(snapshot, "currency", None) != request.price.currency
        or type(getattr(snapshot, "total_minor", None)) is not int
        or snapshot.total_minor != request.price.total_minor
    ):
        raise CoworkerError(
            "transaction_terms_integrity_failed",
            "The stored transaction terms failed integrity verification. Refresh the terms before review or approval.",
            409,
        )
