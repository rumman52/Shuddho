"""Deterministic Core Agent context-quality policy.

This module deliberately contains no model calls. It ranks, filters, redacts,
deduplicates and detects a small set of explicit preference contradictions
before context reaches a planner or drafting model.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable


CONTEXT_HIERARCHY = (
    "current_user_message",
    "current_run",
    "workspace_document",
    "prior_task",
    "durable_memory",
    "external_connector",
)

_SOURCE_BASE = {
    "workspace_document": 1.00,
    "prior_task": 0.82,
    "durable_memory": 0.72,
    "external_connector": 0.62,
}

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|passwd|secret|client[_ -]?secret)\b"
    r"\s*[:=]\s*([^\s,;]{6,})"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def normalized_text(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", str(value or "")).casefold().split()
    )


def terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\w+", normalized_text(value), flags=re.UNICODE)
        if len(token) >= 3
    }


def content_fingerprint(value: str) -> str:
    return hashlib.sha256(normalized_text(value).encode("utf-8")).hexdigest()


def _luhn(number: str) -> bool:
    digits = [int(char) for char in number if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def filter_sensitive(value: str) -> tuple[str, list[str]]:
    """Remove high-risk secrets/payment identifiers from retrieved context.

    The current user message is intentionally not passed through this function;
    this protects retrieved/persisted context from silently re-exposing secrets.
    """
    text = str(value or "")
    reasons: list[str] = []

    def replace(pattern: re.Pattern, marker: str, reason: str) -> None:
        nonlocal text
        updated, count = pattern.subn(marker, text)
        if count:
            text = updated
            reasons.append(reason)

    replace(_PRIVATE_KEY, "[REDACTED PRIVATE KEY]", "private_key")
    replace(_BEARER, "Bearer [REDACTED]", "bearer_token")
    replace(_JWT, "[REDACTED TOKEN]", "jwt")
    replace(_AWS_KEY, "[REDACTED ACCESS KEY]", "access_key")

    def secret_assignment(match: re.Match) -> str:
        reasons.append("secret_assignment")
        return f"{match.group(1)}=[REDACTED]"

    text = _SECRET_ASSIGNMENT.sub(secret_assignment, text)

    def card(match: re.Match) -> str:
        raw = match.group(0)
        if _luhn(raw):
            reasons.append("payment_card")
            return "[REDACTED PAYMENT CARD]"
        return raw

    text = _CARD_CANDIDATE.sub(card, text)
    return text, sorted(set(reasons))


def lexical_relevance(query: str, value: str) -> float:
    query_terms = terms(query)
    if not query_terms:
        return 0.0
    value_terms = terms(value)
    if not value_terms:
        return 0.0
    overlap = len(query_terms & value_terms)
    if overlap == 0:
        return 0.0
    query_coverage = overlap / len(query_terms)
    value_coverage = overlap / max(1, min(len(value_terms), len(query_terms) * 2))
    phrase_bonus = 0.10 if normalized_text(query) in normalized_text(value) else 0.0
    return min(1.0, 0.65 * query_coverage + 0.25 * value_coverage + phrase_bonus)


def recency_score(
    updated_at: datetime | None,
    *,
    now: datetime,
    max_age_seconds: int | None,
) -> float:
    if updated_at is None or max_age_seconds is None:
        return 1.0
    current = _aware(now)
    observed = _aware(updated_at)
    age = max(0.0, (current - observed).total_seconds())
    if age >= max_age_seconds:
        return 0.0
    return max(0.0, 1.0 - age / max_age_seconds)


def is_stale(
    updated_at: datetime | None,
    *,
    now: datetime,
    max_age_seconds: int | None,
) -> bool:
    return recency_score(updated_at, now=now, max_age_seconds=max_age_seconds) <= 0.0


def relevance_score(
    query: str,
    value: str,
    *,
    source_type: str,
    updated_at: datetime | None,
    now: datetime,
    max_age_seconds: int | None,
) -> float:
    lexical = lexical_relevance(query, value)
    recency = recency_score(
        updated_at,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    base = _SOURCE_BASE.get(source_type, 0.5)
    # Lexical match is dominant, but explicitly selected sources remain usable
    # even when the user's wording changes between turns.
    score = 0.68 * lexical + 0.20 * recency + 0.12 * base
    return round(min(1.0, max(0.0, score)), 4)


_FORMALITY = {
    "formal": (
        "formal",
        "professionally",
        "professional tone",
        "businesslike",
        "business tone",
    ),
    "casual": (
        "casual",
        "informal",
        "friendly tone",
        "conversational",
        "relaxed tone",
    ),
}
_VERBOSITY = {
    "concise": ("concise", "brief", "short", "succinct"),
    "detailed": ("detailed", "comprehensive", "thorough", "in depth", "in-depth"),
}
_DIRECTNESS = {
    "direct": ("direct", "straightforward"),
    "gentle": ("gentle", "soft tone", "diplomatic"),
}


def _axis_choice(text: str, axis: dict[str, tuple[str, ...]]) -> str | None:
    normalized = normalized_text(text)
    matches = []
    for choice, phrases in axis.items():
        if any(phrase in normalized for phrase in phrases):
            matches.append(choice)
    return matches[0] if len(set(matches)) == 1 else None


def memory_conflict(current_instruction: str, key: str, value: str) -> str | None:
    """Return the preference axis that the current instruction explicitly overrides."""
    memory_text = f"{key} {value}"
    axes = (
        ("formality", _FORMALITY),
        ("verbosity", _VERBOSITY),
        ("directness", _DIRECTNESS),
    )
    for name, axis in axes:
        current_choice = _axis_choice(current_instruction, axis)
        memory_choice = _axis_choice(memory_text, axis)
        if current_choice is not None and memory_choice is not None and current_choice != memory_choice:
            return name

    current = normalized_text(current_instruction)
    remembered = normalized_text(value)
    # A bounded generic override rule for explicit negation. We require a
    # meaningful remembered phrase to appear after "do not"/"don't" so normal
    # topic overlap does not suppress memory accidentally.
    remembered_terms = [term for term in terms(remembered) if len(term) >= 4]
    for term in remembered_terms[:12]:
        if f"do not {term}" in current or f"don't {term}" in current:
            return "explicit_negation"
    return None


def dedupe_texts(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = content_fingerprint(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
