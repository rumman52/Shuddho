"""Security regressions for retrieved context redaction (stdlib-only)."""
from __future__ import annotations

import pytest

from services.coworker.context_policy import filter_sensitive, memory_conflict


@pytest.mark.parametrize(
    ("assignment", "secret"),
    [
        ('api_key="multi word confidential token"', "multi word confidential token"),
        ("password='phrase with spaces'", "phrase with spaces"),
        ("client_secret=`service private value`", "service private value"),
    ],
)
def test_quoted_multiword_secret_assignments_are_fully_redacted(assignment: str, secret: str):
    redacted, reasons = filter_sensitive(f"Before {assignment}; after")
    assert secret not in redacted
    assert "=[REDACTED]" in redacted
    assert redacted.startswith("Before ") and redacted.endswith("; after")
    assert "secret_assignment" in reasons


def test_plain_secret_assignment_and_normal_context_still_work():
    redacted, reasons = filter_sensitive("Deploy api_key=secretvalue123 to staging.")
    assert redacted == "Deploy api_key=[REDACTED] to staging."
    assert reasons == ["secret_assignment"]
    assert filter_sensitive("Public project meeting at noon.") == ("Public project meeting at noon.", [])


@pytest.mark.parametrize(
    "assignment",
    [
        'api_key="incomplete multi word private value',
        "password='unfinished private phrase with spaces",
    ],
)
def test_unterminated_quoted_secret_fails_closed(assignment: str):
    redacted, reasons = filter_sensitive(f"Header {assignment}")
    assert redacted.endswith("=[REDACTED]")
    assert "private" not in redacted
    assert "secret_assignment" in reasons


@pytest.mark.parametrize(
    ("assignment", "safe_assignment"),
    [
        ("api_key=“multi word confidential token”", "api_key=[REDACTED]"),
        ("password=‘phrase with spaces’", "password=[REDACTED]"),
        ("client_secret=“service private value”", "client_secret=[REDACTED]"),
    ],
)
def test_typographic_quoted_secret_assignments_redact_every_word(assignment, safe_assignment):
    redacted, reasons = filter_sensitive(f"Before {assignment}; after")
    assert redacted == f"Before {safe_assignment}; after"
    assert "secret_assignment" in reasons


@pytest.mark.parametrize(
    ("assignment", "safe_assignment"),
    [
        ("api_key=“unfinished confidential multi word token", "api_key=[REDACTED]"),
        ("password=‘unfinished private phrase with spaces", "password=[REDACTED]"),
    ],
)
def test_unterminated_typographic_quote_fails_closed_to_line_end(assignment, safe_assignment):
    redacted, reasons = filter_sensitive(f"Header {assignment}\nPublic follow-up.")
    assert redacted == f"Header {safe_assignment}\nPublic follow-up."
    assert "secret_assignment" in reasons


@pytest.mark.parametrize(
    ("assignment", "expected"),
    [
        ("api_key=„multi word confidential phrase“", "api_key=[REDACTED]"),
        ("password=«multi word confidential phrase»", "password=[REDACTED]"),
    ],
)
def test_low_high_and_guillemet_quoted_secret_assignments_are_fully_redacted(assignment, expected):
    redacted, reasons = filter_sensitive(f"Before {assignment}; after")
    assert redacted == f"Before {expected}; after"
    assert "secret_assignment" in reasons


@pytest.mark.parametrize(
    ("assignment", "expected"),
    [
        ("api_key=„unterminated private phrase", "api_key=[REDACTED]"),
        ("client_secret=«unterminated private phrase", "client_secret=[REDACTED]"),
    ],
)
def test_unterminated_low_high_and_guillemet_quotes_fail_closed(assignment, expected):
    redacted, reasons = filter_sensitive(f"Before {assignment}\nPublic following line.")
    assert redacted == f"Before {expected}\nPublic following line."
    assert "secret_assignment" in reasons


@pytest.mark.parametrize("instruction, remembered", [
    ("Do not reformulate this passage.", "reform"),
    ("Undo not archive.", "archive"),
    ("Don't shortlist candidates.", "short"),
])
def test_explicit_negation_requires_complete_words(instruction, remembered):
    assert memory_conflict(instruction, "project.note", remembered) is None


def test_explicit_negation_checks_all_bounded_memory_terms():
    words = "archive redact export publish annotate upload preserve review verify redactable compile compare summarize revise translate reconcile".split()
    remembered = " ".join(words)
    assert len(set(words)) > 12
    for word in words:
        assert memory_conflict(f"Do not {word}.", "project.note", remembered) == "explicit_negation", word


@pytest.mark.parametrize("instruction", ["Do not archive.", "Don't archive.", "DON’T archive."])
def test_explicit_negation_suppresses_matching_term(instruction):
    assert memory_conflict(instruction, "project.note", "Always archive records.") == "explicit_negation"


def test_positive_style_precedence_is_preserved():
    assert memory_conflict("Make it casual and conversational.", "writing.tone", "Usually write formally.") == "formality"
    assert memory_conflict("Research the casual dining market.", "writing.tone", "Usually write formally.") is None
