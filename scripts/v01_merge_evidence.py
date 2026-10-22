"""Read-only V-01 post-merge evidence audit; this never authorizes merging.

Usage: python -m scripts.v01_merge_evidence --repository owner/repo --pr 519 --run 39471452728
Optional GITHUB_TOKEN is used only in read-only API requests. No credentials are printed.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


REQUIRED_JOBS = ("test-and-build", "coworker", "ci-merge-gate")
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
HEX_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
PAGE_SIZE = 100
MAX_PAGES = 10


class EvidenceError(ValueError):
    """Evidence missing or malformed; the result must not be called safe."""


def _when(value: object) -> datetime:
    if not isinstance(value, str):
        raise EvidenceError("missing timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("timestamp must have an offset")
    return parsed


def inspect_premerge_evidence(pr: dict, run: dict, jobs: list, reviews: list) -> dict:
    """Classify evidence; no incident observed is NOT native branch-rule proof."""
    if not isinstance(pr, dict) or not isinstance(run, dict) or not isinstance(jobs, list) or not isinstance(reviews, list):
        raise EvidenceError("invalid GitHub response shape")
    head = pr.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not HEX_SHA.fullmatch(sha):
        raise EvidenceError("invalid PR head")
    if run.get("head_sha") != sha:
        raise EvidenceError("workflow is not for the PR final head")
    # GitHub can associate the same commit with multiple branches/PRs. Head SHA
    # alone cannot establish that these check results came from this PR.
    base = pr.get("base")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    base_repo = base.get("repo") if isinstance(base, dict) else None
    run_head_repo = run.get("head_repository")
    run_base_repo = run.get("repository")
    if (
        not isinstance(head.get("ref"), str)
        or not head["ref"]
        or not isinstance(head_repo, dict)
        or type(head_repo.get("id")) is not int
        or not isinstance(base_repo, dict)
        or type(base_repo.get("id")) is not int
        or not isinstance(run.get("head_branch"), str)
        or not run["head_branch"]
        or not isinstance(run_head_repo, dict)
        or type(run_head_repo.get("id")) is not int
        or not isinstance(run_base_repo, dict)
        or type(run_base_repo.get("id")) is not int
    ):
        raise EvidenceError("missing PR/workflow branch or repository provenance")
    if (
        run["head_branch"] != head["ref"]
        or run_head_repo["id"] != head_repo["id"]
        or run_base_repo["id"] != base_repo["id"]
    ):
        raise EvidenceError("workflow provenance does not match PR branch/repositories")
    if run.get("event") not in {"pull_request", "pull_request_review"}:
        raise EvidenceError("workflow is not a PR review/check event")
    if run.get("status") != "completed":
        raise EvidenceError("workflow not completed")
    merged_at = _when(pr.get("merged_at"))
    if run.get("conclusion") not in {"success", "failure", "cancelled", "timed_out", "action_required", "neutral", "skipped", "stale"}:
        raise EvidenceError("invalid workflow conclusion")

    job_by_name = {}
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("name"), str):
            raise EvidenceError("invalid job")
        if job["name"] in job_by_name:
            raise EvidenceError("duplicate job name")
        job_by_name[job["name"]] = job
    if any(name not in job_by_name for name in REQUIRED_JOBS):
        raise EvidenceError("missing required job evidence")

    findings = []
    job_finished = {}
    for name in REQUIRED_JOBS:
        job = job_by_name[name]
        if job.get("status") != "completed" or not isinstance(job.get("conclusion"), str):
            raise EvidenceError(f"incomplete job evidence: {name}")
        finished = _when(job.get("completed_at"))
        job_finished[name] = finished
        if job["conclusion"] != "success":
            findings.append(f"{name}:{job['conclusion']}")
        if finished > merged_at:
            findings.append(f"{name}:completed_after_merge")
    if run["conclusion"] != "success":
        findings.append(f"workflow:{run['conclusion']}")

    author = pr.get("user") or {}
    if not isinstance(author, dict):
        raise EvidenceError("invalid author")
    author_login = author.get("login", "")
    if not isinstance(author_login, str) or not author_login:
        raise EvidenceError("invalid author")
    latest = {}
    seen_ids = set()
    for review in reviews:
        if not isinstance(review, dict) or type(review.get("id")) is not int or review["id"] in seen_ids:
            raise EvidenceError("invalid or duplicated review")
        seen_ids.add(review["id"])
        user = review.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("login"), str) or not user["login"]:
            raise EvidenceError("invalid reviewer")
        if review.get("state") not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED", "PENDING"}:
            raise EvidenceError("invalid review state")
        if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            if _when(review.get("submitted_at")) > merged_at:
                continue
        if review["state"] not in {"COMMENTED", "PENDING"}:
            key = user["login"].casefold()
            if key not in latest or latest[key]["id"] < review["id"]:
                latest[key] = review

    approvers = []
    approval_times = []
    change_requests = []
    for login, review in latest.items():
        user = review["user"]
        if (login == author_login.casefold() or user.get("type") != "User"
            or login.endswith("[bot]") or review.get("author_association") not in TRUSTED_ASSOCIATIONS):
            continue
        if review["state"] == "CHANGES_REQUESTED":
            change_requests.append(login)
        if review["state"] == "APPROVED" and review.get("commit_id") == sha:
            approvers.append(login)
            approval_times.append(_when(review["submitted_at"]))
    if change_requests:
        findings.append("outstanding_independent_changes_requested")
    if not approvers:
        findings.append("no_independent_current_head_approval")
    elif all(when > job_finished["ci-merge-gate"] for when in approval_times):
        # The successful final review may exist by merge time, but none of
        # those approvals was available when this particular CI gate ended.
        # Historical evidence alone cannot establish a later gate re-run.
        findings.append("ci-merge-gate:completed_before_independent_approval")

    return {
        "classification": "observed_governance_incident" if findings else "no_incident_in_supplied_evidence",
        "pull_request": pr.get("number"),
        "head_sha": sha,
        "merged_at": pr["merged_at"],
        "findings": findings,
        "limitations": [
            "native_policy_not_verified",
            "point_in_time_api_evidence_not_a_merge_lock",
            "reviewer_permission_at_merge_not_independently_verified",
        ],
    }


class _NoCredentialRedirect(HTTPRedirectHandler):
    """Reject 30x responses instead of forwarding GitHub credentials."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_json(url: str, token: str):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "shuddho-v01-readonly-audit"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        # urllib's default redirect handler copies Authorization to the target
        # host. Never follow a redirect while collecting governance evidence.
        with build_opener(_NoCredentialRedirect()).open(Request(url, headers=headers), timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise EvidenceError("GitHub evidence read failed") from exc


def _pages(base: str, token: str, key: str | None = None) -> list:
    all_items = []
    for page in range(1, MAX_PAGES + 1):
        value = _get_json(f"{base}{'&' if '?' in base else '?'}per_page={PAGE_SIZE}&page={page}", token)
        if key is not None:
            if not isinstance(value, dict):
                raise EvidenceError("malformed paginated response")
            value = value.get(key)
        if not isinstance(value, list) or len(value) > PAGE_SIZE:
            raise EvidenceError("malformed paginated list")
        all_items.extend(value)
        if len(value) < PAGE_SIZE:
            return all_items
    raise EvidenceError("evidence exceeds pagination bound")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--run", type=int, required=True)
    args = parser.parse_args()
    if not REPO.fullmatch(args.repository) or args.pr < 1 or args.run < 1:
        parser.error("invalid repo/PR/run")
    root = f"https://api.github.com/repos/{args.repository}"
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        pr = _get_json(f"{root}/pulls/{args.pr}", token)
        run = _get_json(f"{root}/actions/runs/{args.run}", token)
        jobs = _pages(f"{root}/actions/runs/{args.run}/jobs", token, "jobs")
        reviews = _pages(f"{root}/pulls/{args.pr}/reviews", token)
        report = inspect_premerge_evidence(pr, run, jobs, reviews)
    except EvidenceError as exc:
        print(json.dumps({"classification": "evidence_unavailable", "reason": str(exc), "native_policy_verified": False}))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
