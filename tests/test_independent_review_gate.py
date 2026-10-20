"""V-01: independent review is a mandatory final-head merge condition."""
from __future__ import annotations

import pytest

from scripts.independent_review_gate import ReviewGateError, require_current_head_review


HEAD = "a" * 40
OLD = "b" * 40


def pull(*, sha=HEAD, draft=False, state="open"):
    return {
        "state": state,
        "draft": draft,
        "merged_at": None,
        "head": {"sha": sha},
        "user": {"login": "proposing-author"},
    }


def review(
    *,
    id=1,
    login="independent-maintainer",
    state="APPROVED",
    sha=HEAD,
    association="COLLABORATOR",
    type="User",
):
    return {
        "id": id,
        "user": {"login": login, "type": type},
        "state": state,
        "commit_id": sha,
        "author_association": association,
    }


def test_one_independent_maintainer_approval_of_current_head_passes():
    assert require_current_head_review(pull(), [review()], HEAD) == "independent-maintainer"


@pytest.mark.parametrize(
    "reviews",
    [
        [],
        [review(sha=OLD)],
        [review(login="proposing-author")],
        [review(login="Proposing-Author")],
        [review(type="Bot")],
        [review(login="dependabot[bot]")],
        [review(association="NONE")],
        [review(association="CONTRIBUTOR")],
        [review(state="COMMENTED")],
        [review(state="DISMISSED")],
        [review(state="CHANGES_REQUESTED")],
        [review(state="PENDING")],
    ],
)
def test_missing_or_ineligible_approval_fails_closed(reviews):
    with pytest.raises(ReviewGateError):
        require_current_head_review(pull(), reviews, HEAD)


def test_stale_previous_approval_cannot_survive_new_commit():
    with pytest.raises(ReviewGateError, match="current head"):
        require_current_head_review(pull(sha=OLD), [review(sha=OLD)], HEAD)
    with pytest.raises(ReviewGateError):
        require_current_head_review(pull(), [review(sha=OLD), review(id=2, state="COMMENTED")], HEAD)


def test_latest_dismissal_or_change_request_revokes_prior_approval():
    for state in ("DISMISSED", "CHANGES_REQUESTED"):
        with pytest.raises(ReviewGateError):
            require_current_head_review(
                pull(), [review(id=1), review(id=2, state=state)], HEAD
            )


def test_open_change_request_by_other_maintainer_blocks_an_approval():
    with pytest.raises(ReviewGateError, match="changes requested"):
        require_current_head_review(
            pull(), [
                review(id=1, login="alice"),
                review(id=2, login="bob", state="CHANGES_REQUESTED"),
            ], HEAD
        )


def test_later_current_head_approval_replaces_change_request():
    assert require_current_head_review(
        pull(),
        [
            review(id=1, state="CHANGES_REQUESTED"),
            review(id=2, state="APPROVED"),
        ],
        HEAD,
    ) == "independent-maintainer"


@pytest.mark.parametrize("draft,state", [(True, "open"), (False, "closed")])
def test_draft_or_closed_pr_fails(draft, state):
    with pytest.raises(ReviewGateError):
        require_current_head_review(pull(draft=draft, state=state), [review()], HEAD)


def test_malformed_review_or_pr_fails_closed():
    for reviews in ([None], [{"state": "APPROVED"}], [{"id": "x"}]):
        with pytest.raises(ReviewGateError):
            require_current_head_review(pull(), reviews, HEAD)
    with pytest.raises(ReviewGateError):
        require_current_head_review({}, [review()], HEAD)


def test_reviewer_comment_does_not_withdraw_previous_approval():
    assert require_current_head_review(
        pull(), [review(id=1), review(id=2, state="COMMENTED")], HEAD
    ) == "independent-maintainer"
