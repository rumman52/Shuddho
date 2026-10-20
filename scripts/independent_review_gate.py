"""Fail-closed V-01 gate: current-head approval by an independent maintainer.

The job is defense in depth, NOT a substitute for enforced repository
branch protection or GitHub's native required-review rules.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ReviewGateError(ValueError):
    """An independent current-head review cannot be established."""


TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED", "PENDING"})
PAGE_SIZE = 100
MAX_PAGES = 10


def require_current_head_review(
    pull_request: dict, reviews: list[dict], expected_head_sha: str
) -> str:
    """Return the independent approver login or fail without trusting prior revisions."""
    if not isinstance(pull_request, dict) or not isinstance(reviews, list):
        raise ReviewGateError("Malformed pull request or review response")
    head = pull_request.get("head")
    author = pull_request.get("user")
    if (
        pull_request.get("state") != "open"
        or pull_request.get("draft") is not False
        or pull_request.get("merged_at") is not None
        or not isinstance(head, dict)
        or not isinstance(author, dict)
        or not isinstance(author.get("login"), str)
        or not author["login"]
        or not isinstance(head.get("sha"), str)
        or not expected_head_sha
    ):
        raise ReviewGateError("Pull request is not an open non-draft revision")
    if head["sha"] != expected_head_sha:
        raise ReviewGateError("Pull request head changed since the workflow started")

    # Validate before sorting: reject malformed/duplicate GitHub review IDs
    # and undated actionable reviews instead of inferring approval authority.
    seen_ids: set[int] = set()
    for item in reviews:
        if (
            not isinstance(item, dict)
            or type(item.get("id")) is not int
            or not isinstance(item.get("user"), dict)
            or not isinstance(item["user"].get("login"), str)
            or not item["user"]["login"]
            or item.get("state") not in REVIEW_STATES
        ):
            raise ReviewGateError("Malformed review data")
        if item["id"] in seen_ids:
            raise ReviewGateError("duplicate review ID")
        seen_ids.add(item["id"])
        if item["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            submitted = item.get("submitted_at")
            if not isinstance(submitted, str):
                raise ReviewGateError("Missing review submission timestamp")
            try:
                submitted_at = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ReviewGateError("Malformed review submission timestamp") from exc
            if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
                raise ReviewGateError("Review submission timestamp lacks timezone")

    latest: dict[str, dict] = {}
    for item in sorted(reviews, key=lambda r: r["id"]):
        if item["state"] in {"PENDING", "COMMENTED"}:
            continue
        latest[item["user"]["login"].casefold()] = item

    approved: list[str] = []
    for login, item in latest.items():
        user = item["user"]
        if (
            login == author["login"].casefold()
            or user.get("type") != "User"
            or login.endswith("[bot]")
            or item.get("author_association") not in TRUSTED_ASSOCIATIONS
        ):
            continue
        if item["state"] == "CHANGES_REQUESTED":
            raise ReviewGateError("Independent maintainer changes requested")
        if item["state"] == "APPROVED" and item.get("commit_id") == expected_head_sha:
            approved.append(user["login"])

    if not approved:
        raise ReviewGateError("No independent maintainer approval on the current head")
    return sorted(approved, key=str.casefold)[0]


def _get_json(url: str, token: str):
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shuddho-independent-review-gate",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, ValueError, OSError) as exc:
        status = getattr(exc, "code", "unavailable")
        raise ReviewGateError(f"GitHub review evidence unavailable (status={status})") from exc


def _read_review_pages(base: str, token: str) -> list[dict]:
    """Fetch a bounded, full PR review listing or fail closed on pagination."""
    reviews = []
    for page in range(1, MAX_PAGES + 1):
        result = _get_json(f"{base}/reviews?per_page={PAGE_SIZE}&page={page}", token)
        if not isinstance(result, list) or len(result) > PAGE_SIZE:
            raise ReviewGateError("Malformed GitHub review page")
        reviews.extend(result)
        if len(result) < PAGE_SIZE:
            return reviews
    raise ReviewGateError("Review history exceeds bounded pagination limit")


def validate_live_review(
    repository: str, number: int, expected_head_sha: str, token: str
) -> str:
    if (
        repository.count("/") != 1
        or not all(part and all(c.isascii() and (c.isalnum() or c in "._-") for c in part)
                   for part in repository.split("/"))
        or number < 1
        or not expected_head_sha
        or not token
    ):
        raise ReviewGateError("Missing or invalid review-gate inputs")
    base = f"https://api.github.com/repos/{repository}/pulls/{number}"
    pull_request = _get_json(base, token)
    reviews = _read_review_pages(base, token)
    require_current_head_review(pull_request, reviews, expected_head_sha)

    # PR state and review submissions are separate API reads, not an atomic
    # snapshot. Reject stale PR evidence after review-page pagination.
    current_pull_request = _get_json(base, token)
    require_current_head_review(current_pull_request, reviews, expected_head_sha)

    # A review can be dismissed or a change request submitted without the PR
    # head changing. A final PR-only read cannot detect this. Fail closed if
    # any review-page evidence changed while the gate was evaluating it.
    confirmed_reviews = _read_review_pages(base, token)
    if confirmed_reviews != reviews:
        raise ReviewGateError("Review evidence changed during validation")
    require_current_head_review(
        current_pull_request, confirmed_reviews, expected_head_sha
    )

    # Recheck the PR one last time *after* the confirmation review-page reads;
    # otherwise its head/author/state could change during the second fetch.
    final_pull_request = _get_json(base, token)
    return require_current_head_review(
        final_pull_request, confirmed_reviews, expected_head_sha
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    try:
        reviewer = validate_live_review(
            args.repository,
            args.pull_request,
            args.head_sha,
            os.environ.get("GITHUB_TOKEN", ""),
        )
    except ReviewGateError as exc:
        parser.exit(1, f"Independent review gate failed: {exc}\n")
    print(f"Independent current-head maintainer review confirmed: {reviewer}")


if __name__ == "__main__":
    main()
