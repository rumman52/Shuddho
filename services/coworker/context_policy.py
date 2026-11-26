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
    "saved_project_instructions",
    "workspace_document",
    "workspace_artifact",
    "prior_task",
    "durable_memory",
    "external_connector",
)

_SOURCE_BASE = {
    "workspace_document": 1.00,
    "workspace_artifact": 0.98,
    "prior_task": 0.82,
    "durable_memory": 0.72,
    "external_connector": 0.62,
}

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|passwd|secret|client[_ -]?secret)\b"
    r"\s*[:=]\s*"
    # Fully quoted values take priority. Truncated quotes (e.g. a clipped
    # metadata label) fail closed to end-of-line instead of leaking their tail.
    r"(?:"
    r"\"(?:\\.|[^\"\\\r\n])*\"|\"[^\r\n]*|"
    r"'(?:\\.|[^'\\\r\n])*'|'[^\r\n]*|"
    r"\x60(?:\\.|[^\x60\\\r\n])*\x60|\x60[^\r\n]*|"
    r"“(?:\\.|[^”\\\r\n])*”|“[^\r\n]*|"
    r"‘(?:\\.|[^’\\\r\n])*’|‘[^\r\n]*|"
    r"„(?:\\.|[^“\\\r\n])*“|„[^\r\n]*|"
    r"«(?:\\.|[^»\\\r\n])*»|«[^\r\n]*|"
    r"[^\s,;]{6,})"
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
        "formally",
        "professional",
        "professionally",
        "professional tone",
        "businesslike",
        "business tone",
    ),
    "casual": (
        "casual",
        "casually",
        "informal",
        "informally",
        "friendly tone",
        "conversational",
        "relaxed tone",
    ),
}
_VERBOSITY = {
    "concise": ("concise", "concisely", "brief", "briefly", "short", "succinct", "succinctly"),
    "detailed": ("detailed", "comprehensive", "thorough", "in depth", "in-depth"),
}
_DIRECTNESS = {
    "direct": ("direct", "directly", "straightforward"),
    "gentle": ("gentle", "gently", "soft tone", "diplomatic"),
}

_STYLE_DIRECTIVE_LEFT = re.compile(
    r"(?i)(?:^|\b)(?:make|write|keep|use|be|sound|reply|respond|draft|answer|phrase|word)"
    r"(?:\s+(?:this|the|my|your|it))?(?:\s+(?:message|email|reply|response|answer|draft))?"
    r"(?:\s+(?:very|more|less))?\s*$"
)
_STYLE_DIRECTIVE_RIGHT = re.compile(
    r"(?i)^\s*(?:tone|style|voice|writing|message|email|reply|response|answer)\b"
)


def _phrase_matches(text: str, phrase: str) -> list[re.Match]:
    return list(re.finditer(
        r"(?<!\w)" + re.escape(normalized_text(phrase)) + r"(?!\w)",
        normalized_text(text),
        flags=re.UNICODE,
    ))


def _axis_choice(text: str, axis: dict[str, tuple[str, ...]]) -> str | None:
    matches = []
    for choice, phrases in axis.items():
        if any(_phrase_matches(text, phrase) for phrase in phrases):
            matches.append(choice)
    return matches[0] if len(set(matches)) == 1 else None


# A negated style directive is not an affirmative preference. Keep the
# negation span so the generic rule below cannot reinterpret its action verb
# (e.g. "write") as a separate prohibition on all writing.
_NEGATED_STYLE_COMMAND = re.compile(
    r"(?<!\w)(?:do not|don['’]t|never) "
    r"(?:make|write|keep|use|be|sound|reply|respond|draft|answer|phrase|word)"
    r"(?:\s+in)?"
    r"(?:\s+(?:a|an|this|the|my|your|it))?"
    r"(?:\s+(?:message|email|reply|response|answer|draft|report))?"
    r"(?:\s+(?:very|too|more|less))?\s*$"
)
_NEGATED_STYLE_PREDICATE = re.compile(
    r"\b(?:tone|style|voice)\s+(?:(?:should|must|will)\s+not\s+be|is\s+not)\s*$"
)
_NEGATED_STYLE_AVOID = re.compile(r"\bavoid(?:\s+(?:a|an|the))?\s*$")
_STYLE_END = re.compile(r"^\s*(?:$|[.,;:!?)]|(?:and|or|but|for|in|when|with)\b)")


def _explicit_axis_directives(
    text: str, axis: dict[str, tuple[str, ...]],
) -> tuple[set[str], set[str], set[int]]:
    """Recognize bounded style commands, distinguishing affirmation and negation."""
    normalized = normalized_text(text)
    positive: set[str] = set()
    negative: set[str] = set()
    negation_starts: set[int] = set()
    for choice, phrases in axis.items():
        for phrase in phrases:
            for match in _phrase_matches(normalized, phrase):
                left_start = max(0, match.start() - 80)
                left = normalized[left_start:match.start()]
                right = normalized[match.end():match.end() + 40]
                style_label = bool(_STYLE_DIRECTIVE_RIGHT.search(right)) or phrase.endswith(
                    (" tone", " style", " voice")
                )
                command = _NEGATED_STYLE_COMMAND.search(left)
                predicate = _NEGATED_STYLE_PREDICATE.search(left)
                avoid = _NEGATED_STYLE_AVOID.search(left)
                if command or predicate or avoid:
                    if style_label or ((command or predicate) and _STYLE_END.search(right)):
                        negative.add(choice)
                        if command:
                            negation_starts.add(left_start + command.start())
                    # A negated command that describes a topic (e.g. formal
                    # methods) must not fall through as a positive preference.
                    continue
                if (
                    _STYLE_DIRECTIVE_LEFT.search(left)
                    or _STYLE_DIRECTIVE_RIGHT.search(right)
                    or re.search(r"(?i)\b(?:tone|style|voice)\s+(?:should\s+be\s+)?$", left)
                ):
                    positive.add(choice)
    return positive, negative, negation_starts


def memory_conflict(current_instruction: str, key: str, value: str) -> str | None:
    """Return the preference axis that the current instruction explicitly overrides."""
    memory_text = f"{key} {value}"
    axes = (
        ("formality", _FORMALITY),
        ("verbosity", _VERBOSITY),
        ("directness", _DIRECTNESS),
    )
    style_negations: set[int] = set()
    for name, axis in axes:
        positive, negative, negation_starts = _explicit_axis_directives(current_instruction, axis)
        style_negations.update(negation_starts)
        memory_choice = _axis_choice(memory_text, axis)
        if memory_choice is not None and (
            memory_choice in negative or (len(positive) == 1 and memory_choice not in positive)
        ):
            return name

    current = normalized_text(current_instruction)
    # Compare whole words after explicit negation. Memory values and task
    # instructions are already bounded; an arbitrary slice of a set made
    # the result depend on Python's process-specific hash seed.
    remembered_terms = terms(value)
    for match in re.finditer(r"(?<!\w)(?:do not|don['’]t) (\w{4,})(?!\w)", current):
        if match.start() not in style_negations and match.group(1) in remembered_terms:
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
