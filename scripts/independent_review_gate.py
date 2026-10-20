"""Fail-closed V-01 gate: current-head approval by an independent maintainer.

The job is defense in depth, NOT a substitute for enforced repository
branch protection or GitHub's native required-review rules.
"""
from __future__ import annotations

import argparse
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

    # Validate before sorting: untrusted mixed-type IDs must fail closed
    # as ReviewGateError rather than raising an uncontrolled TypeError.
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
    reviews = []
    for page in range(1, MAX_PAGES + 1):
        result = _get_json(f"{base}/reviews?per_page={PAGE_SIZE}&page={page}", token)
        if not isinstance(result, list) or len(result) > PAGE_SIZE:
            raise ReviewGateError("Malformed GitHub review page")
        reviews.extend(result)
        if len(result) < PAGE_SIZE:
            # Preserve the initial snapshot check, but do not accept it as
            # current authority after one or more awaited review-page reads.
            require_current_head_review(pull_request, reviews, expected_head_sha)
            current_pull_request = _get_json(base, token)
            return require_current_head_review(
                current_pull_request, reviews, expected_head_sha
            )
    raise ReviewGateError("Review history exceeds bounded pagination limit")


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
