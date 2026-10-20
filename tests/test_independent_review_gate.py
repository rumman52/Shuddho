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
        "submitted_at": "2026-10-20T18:20:00Z",
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
    with pytest.raises(ReviewGateError, match="head changed"):
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


def test_ci_merge_gate_requires_review_and_rechecks_after_review_events():
    from pathlib import Path

    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pull_request_review:" in workflow
    assert "types: [submitted, dismissed]" in workflow
    assert "pull-requests: read" in workflow
    assert "Require independent current-head review" in workflow
    assert "python -m scripts.independent_review_gate" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow


def test_malformed_mixed_review_ids_fail_with_explicit_gate_error():
    with pytest.raises(ReviewGateError, match="Malformed review"):
        require_current_head_review(
            pull(), [review(), {"id": "not-an-integer", "state": "APPROVED"}], HEAD
        )


# These tests control only the remote API boundary. The real live validator and
# current-head policy run unchanged; snapshots model PR changes between reads.
def live_review_api(monkeypatch, final_pull, *, reviews=None, page_size=None, initial_pull=None):
    from scripts import independent_review_gate as gate

    calls = []
    initial_pull = pull() if initial_pull is None else initial_pull
    rows = [review()] if reviews is None else reviews
    if page_size is not None:
        monkeypatch.setattr(gate, "PAGE_SIZE", page_size)

    def get_json(url, token):
        assert token == "test-token"
        calls.append(url)
        if "/reviews?" in url:
            page = int(url.rsplit("page=", 1)[1])
            start = (page - 1) * gate.PAGE_SIZE
            return rows[start : start + gate.PAGE_SIZE]
        if len([call for call in calls if "/reviews?" not in call]) == 1:
            return initial_pull
        if isinstance(final_pull, Exception):
            raise final_pull
        return final_pull

    monkeypatch.setattr(gate, "_get_json", get_json)
    return gate, calls


def test_live_review_rechecks_unchanged_pr_after_all_review_pages(monkeypatch):
    gate, calls = live_review_api(
        monkeypatch, pull(), reviews=[review(), review(id=2, state="COMMENTED")],
        page_size=2,
    )

    assert gate.validate_live_review("owner/repo", 7, HEAD, "test-token") == "independent-maintainer"
    base = "https://api.github.com/repos/owner/repo/pulls/7"
    assert calls == [
        base,
        f"{base}/reviews?per_page=2&page=1",
        f"{base}/reviews?per_page=2&page=2",
        base,
    ]


@pytest.mark.parametrize(
    "final_pull",
    [
        pull(sha=OLD),
        pull(draft=True),
        pull(state="closed"),
        {**pull(), "merged_at": "2026-10-20T17:50:47Z"},
        {**pull(), "user": {"login": "independent-maintainer"}},
        {},
        None,
    ],
    ids=["new-head", "converted-to-draft", "closed", "merged", "self-review", "malformed", "missing"],
)
def test_live_review_denies_pr_changed_while_fetching_reviews(monkeypatch, final_pull):
    gate, _ = live_review_api(monkeypatch, final_pull)

    with pytest.raises(gate.ReviewGateError):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


def test_live_review_denies_final_pr_read_failure(monkeypatch):
    from scripts.independent_review_gate import ReviewGateError

    gate, _ = live_review_api(monkeypatch, ReviewGateError("final snapshot unavailable"))

    with pytest.raises(ReviewGateError, match="final snapshot unavailable"):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


@pytest.mark.parametrize(
    "initial_pull",
    [
        pull(sha=OLD),
        pull(draft=True),
        {**pull(), "user": {"login": "independent-maintainer"}},
    ],
    ids=["initial-head-mismatch", "initial-draft", "initial-self-review"],
)
def test_live_review_cannot_rehabilitate_invalid_initial_snapshot(monkeypatch, initial_pull):
    gate, _ = live_review_api(monkeypatch, pull(), initial_pull=initial_pull)

    with pytest.raises(gate.ReviewGateError):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


@pytest.mark.parametrize("bad_submitted", [None, "not-a-timestamp", "2026-10-20T18:20:00"])
def test_unproven_actionable_review_submission_is_never_an_approval(bad_submitted):
    # APPROVED is not valid evidence if its submission cannot be dated.
    item = review()
    item["submitted_at"] = bad_submitted
    with pytest.raises(ReviewGateError, match="submission"):
        require_current_head_review(pull(), [item], HEAD)


def test_actionable_approval_without_submission_field_fails_closed():
    item = review()
    del item["submitted_at"]
    with pytest.raises(ReviewGateError, match="submission"):
        require_current_head_review(pull(), [item], HEAD)


def test_malformed_dismissed_review_cannot_be_ignored_beside_good_approval():
    dismissed = review(id=2, login="other-maintainer", state="DISMISSED")
    dismissed.pop("submitted_at")
    with pytest.raises(ReviewGateError, match="submission"):
        require_current_head_review(pull(), [review(), dismissed], HEAD)


def test_duplicate_review_ids_across_review_pages_fail_closed():
    # GitHub review ids are globally unique; conflicting duplicates must not
    # be used to infer a latest approval.
    with pytest.raises(ReviewGateError, match="duplicate"):
        require_current_head_review(pull(), [review(), review(id=1, login="other")], HEAD)


def test_pending_and_comment_reviews_need_not_have_submission_timestamps():
    pending = review(id=2, state="PENDING", login="other")
    pending.pop("submitted_at")
    comment = review(id=3, state="COMMENTED", login="other")
    comment.pop("submitted_at")
    assert require_current_head_review(pull(), [review(), pending, comment], HEAD) == "independent-maintainer"


def test_live_review_denies_dismissal_inserted_during_validation(monkeypatch):
    from scripts import independent_review_gate as gate

    reads = {"reviews": 0}

    def get_json(url, token):
        assert token == "test-token"
        if "/reviews?" not in url:
            return pull()
        reads["reviews"] += 1
        if reads["reviews"] == 1:
            return [review()]
        return [review(), review(id=2, state="DISMISSED")]

    monkeypatch.setattr(gate, "_get_json", get_json)
    with pytest.raises(gate.ReviewGateError, match="changed|approval|review"):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


def test_live_review_denies_new_change_request_during_validation(monkeypatch):
    from scripts import independent_review_gate as gate

    reads = {"reviews": 0}

    def get_json(url, token):
        if "/reviews?" not in url:
            return pull()
        reads["reviews"] += 1
        if reads["reviews"] == 1:
            return [review(login="alice")]
        return [review(login="alice"), review(id=2, login="bob", state="CHANGES_REQUESTED")]

    monkeypatch.setattr(gate, "_get_json", get_json)
    with pytest.raises(gate.ReviewGateError, match="changed|changes requested"):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


def test_live_review_rechecks_pr_after_second_review_read(monkeypatch):
    from scripts import independent_review_gate as gate

    calls = {"pr": 0}

    def get_json(url, token):
        if "/reviews?" in url:
            return [review()]
        calls["pr"] += 1
        return pull(sha=OLD) if calls["pr"] >= 3 else pull()

    monkeypatch.setattr(gate, "_get_json", get_json)
    with pytest.raises(gate.ReviewGateError, match="head changed"):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


def test_live_review_requires_second_review_read_to_succeed(monkeypatch):
    from scripts import independent_review_gate as gate

    calls = {"reviews": 0}

    def get_json(url, token):
        if "/reviews?" not in url:
            return pull()
        calls["reviews"] += 1
        if calls["reviews"] == 1:
            return [review()]
        raise gate.ReviewGateError("confirmation review evidence unavailable")

    monkeypatch.setattr(gate, "_get_json", get_json)
    with pytest.raises(gate.ReviewGateError, match="confirmation review evidence unavailable"):
        gate.validate_live_review("owner/repo", 7, HEAD, "test-token")


def test_live_review_stable_two_snapshots_validate_successfully(monkeypatch):
    from scripts import independent_review_gate as gate

    calls = []

    def get_json(url, token):
        calls.append(url)
        return [review()] if "/reviews?" in url else pull()

    monkeypatch.setattr(gate, "_get_json", get_json)
    assert gate.validate_live_review("owner/repo", 7, HEAD, "test-token") == "independent-maintainer"
    assert sum("/reviews?" in call for call in calls) == 2
    assert sum("/reviews?" not in call for call in calls) == 3
