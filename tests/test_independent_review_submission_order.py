"""V-01 regression: use submitted review chronology, not creation/ID order.

A GitHub PENDING review can be created first and submitted only after a
different review has already been submitted. IDs do not prove submission order.
"""
from __future__ import annotations

import pytest

from scripts.independent_review_gate import ReviewGateError, require_current_head_review


HEAD = "a" * 40


def _pr():
    return {
        "state": "open",
        "draft": False,
        "merged_at": None,
        "head": {"sha": HEAD},
        "user": {"login": "proposing-author"},
    }


def _review(id: int, state: str, submitted: str):
    return {
        "id": id,
        "user": {"login": "independent-maintainer", "type": "User"},
        "state": state,
        "commit_id": HEAD,
        "author_association": "COLLABORATOR",
        "submitted_at": submitted,
    }


def test_late_submitted_change_request_revokes_higher_id_approval():
    # Earlier-created pending change request (#1) is submitted *after*
    # the approval (#2). Sorting by ID instead of submitted_at is unsafe.
    approvals = [
        _review(1, "CHANGES_REQUESTED", "2026-10-22T05:02:00Z"),
        _review(2, "APPROVED", "2026-10-22T05:01:00Z"),
    ]
    with pytest.raises(ReviewGateError, match="changes requested"):
        require_current_head_review(_pr(), approvals, HEAD)


def test_late_submitted_approval_resolves_higher_id_change_request():
    reviews = [
        _review(1, "APPROVED", "2026-10-22T05:02:00Z"),
        _review(2, "CHANGES_REQUESTED", "2026-10-22T05:01:00Z"),
    ]
    assert require_current_head_review(_pr(), reviews, HEAD) == "independent-maintainer"


def test_conflicting_same_timestamp_actionable_reviews_fail_closed():
    reviews = [
        _review(1, "CHANGES_REQUESTED", "2026-10-22T05:01:00Z"),
        _review(2, "APPROVED", "2026-10-22T05:01:00Z"),
    ]
    with pytest.raises(ReviewGateError, match="ambiguous|same timestamp"):
        require_current_head_review(_pr(), reviews, HEAD)


def test_submission_timezones_compare_as_instants():
    # Same wall-time string would give wrong order without UTC offset handling.
    reviews = [
        _review(1, "CHANGES_REQUESTED", "2026-10-22T11:02:00+06:00"),
        _review(2, "APPROVED", "2026-10-22T05:01:00+00:00"),
    ]
    with pytest.raises(ReviewGateError, match="changes requested"):
        require_current_head_review(_pr(), reviews, HEAD)
