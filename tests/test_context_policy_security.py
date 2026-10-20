"""Security regressions for retrieved context redaction (stdlib-only)."""
from __future__ import annotations

import pytest

from services.coworker.context_policy import filter_sensitive


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
