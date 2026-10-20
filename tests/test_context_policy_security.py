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
