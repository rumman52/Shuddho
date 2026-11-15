"""Read GitHub Actions results for the exact PR revision tested by CI."""
from __future__ import annotations

import argparse
import os
import re
import time
from urllib.parse import urlencode

from scripts.independent_review_gate import ReviewGateError, _get_json


CI_PATH = ".github/workflows/ci.yml"
TEST_JOBS = (
    "test-and-build", "Frontend tests and builds", "coworker",
    "browser-qualification", "PostgreSQL 18 staging compatibility", "PR head ancestry",
)
SHA = re.compile(r"[0-9a-f]{40}\Z")


def ci_title(number: int, merge_sha: str) -> str:
    return f"PR #{number} CI at {merge_sha}"


def response_items(response: object, key: str) -> list:
    if not isinstance(response, dict):
        raise ReviewGateError("Malformed GitHub CI response")
    items = response.get(key)
    if not isinstance(items, list) or type(response.get("total_count")) is not int or response["total_count"] != len(items):
        raise ReviewGateError("Missing or truncated GitHub CI results")
    if any(not isinstance(item, dict) for item in items):
        raise ReviewGateError("Malformed GitHub CI results")
    return items


def select_ci_run(response: object, number: int, head_sha: str, merge_sha: str) -> dict | None:
    candidates = [
        run for run in response_items(response, "workflow_runs")
        if run.get("path") == CI_PATH
        and run.get("event") == "pull_request"
        and run.get("head_sha") == head_sha
        and run.get("display_title") == ci_title(number, merge_sha)
    ]
    for run in candidates:
        if any(type(run.get(field)) is not int or run[field] < 1 for field in ("id", "run_attempt")):
            raise ReviewGateError("Invalid GitHub CI run identity")
    return max(candidates, key=lambda run: (run["id"], run["run_attempt"]), default=None)


def tested_jobs(response: object, *, complete: bool) -> bool:
    """Wait for pending jobs and reject missing, failed or skipped evidence."""
    jobs = response_items(response, "jobs")
    ready = True
    for name in TEST_JOBS:
        found = [job for job in jobs if job.get("name") == name]
        if len(found) > 1 or (complete and (not found or found[0].get("status") != "completed")):
            raise ReviewGateError(f"Missing or duplicate PR CI job: {name}")
        if not found or found[0].get("status") != "completed":
            ready = False
            continue
        if found[0].get("conclusion") != "success":
            raise ReviewGateError(f"PR CI job did not pass: {name}")
    return ready


def await_tested_pr(repository: str, number: int, head_sha: str, merge_sha: str, token: str) -> int:
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or any(part in {".", ".."} for part in repository.split("/"))
            or number < 1 or not SHA.fullmatch(head_sha) or not SHA.fullmatch(merge_sha) or not token):
        raise ReviewGateError("Invalid repository, PR revision or GitHub token")
    root = f"https://api.github.com/repos/{repository}/actions"
    filters = urlencode({"event": "pull_request", "head_sha": head_sha, "per_page": 100})
    run_url = f"{root}/workflows/ci.yml/runs?{filters}"
    deadline = time.monotonic() + 40 * 60
    while time.monotonic() < deadline:
        run = select_ci_run(_get_json(run_url, token), number, head_sha, merge_sha)
        if run is not None:
            run_id = run["id"]
            complete = run.get("status") == "completed"
            if complete and run.get("conclusion") not in {"success", "failure"}:
                raise ReviewGateError("Exact PR CI run did not finish normally")
            jobs = _get_json(f"{root}/runs/{run_id}/jobs?per_page=100&filter=latest", token)
            if tested_jobs(jobs, complete=complete):
                latest = select_ci_run(_get_json(run_url, token), number, head_sha, merge_sha)
                if latest == run:
                    return run_id
        time.sleep(15)
    raise ReviewGateError("Timed out waiting for passing CI on this exact PR revision")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--merge-sha", required=True)
    args = parser.parse_args()
    try:
        run_id = await_tested_pr(args.repository, args.pull_request, args.head_sha, args.merge_sha, os.environ.get("GITHUB_TOKEN", ""))
    except ReviewGateError as error:
        parser.exit(1, f"PR CI reuse failed: {error}\n")
    print(f"Reused passing PR CI jobs from workflow run {run_id}.")


if __name__ == "__main__":
    main()
