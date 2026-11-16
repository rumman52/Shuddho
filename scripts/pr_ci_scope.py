"""Choose the PR checks from the complete Git diff. Unknown changes use full CI."""
from __future__ import annotations

import argparse
import os
import re
import subprocess


QUICK_JOBS = ("test-and-build", "PR head ancestry")
FRONTEND_JOBS = (*QUICK_JOBS, "Frontend tests and builds", "browser-qualification")
TEST_JOBS = (*FRONTEND_JOBS, "coworker", "PostgreSQL 18 staging compatibility")
JOBS_BY_SCOPE = {"docs": QUICK_JOBS, "frontend": FRONTEND_JOBS, "full": TEST_JOBS}
FRONTEND_PATH = re.compile(r"apps/(?:web-editor|editor|coworker)/(?:src|test|public)/.+\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def classify_paths(paths: list[str]) -> str:
    scope = "docs"
    for path in paths:
        if path == "README.md" or (path.startswith("docs/") and path.endswith(".md")):
            continue
        if not FRONTEND_PATH.fullmatch(path):
            return "full"
        scope = "frontend"
    return scope if paths else "full"


def required_test_jobs(jobs: list[dict], *, legacy_jobs: tuple[str, ...] = TEST_JOBS) -> tuple[str, ...]:
    """Read the successful scope step and preserve the requirements for older runs."""
    if any(not isinstance(job, dict) for job in jobs):
        raise ValueError("Malformed PR CI jobs")
    build = next((job for job in jobs if job.get("name") == "test-and-build"), None)
    steps = build.get("steps", []) if build else []
    if not isinstance(steps, list):
        raise ValueError("Malformed test-and-build steps")
    markers = [
        step for step in steps if isinstance(step, dict) and isinstance(step.get("name"), str)
        and step["name"].startswith("PR CI scope (")
    ]
    if not markers:
        return legacy_jobs
    scopes = [scope for scope in JOBS_BY_SCOPE if markers[0]["name"] == f"PR CI scope ({scope})"]
    if len(markers) != 1 or len(scopes) != 1 or markers[0].get("conclusion") != "success":
        raise ValueError("Invalid PR CI scope evidence")
    return JOBS_BY_SCOPE[scopes[0]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    if not COMMIT.fullmatch(args.base_sha) or not COMMIT.fullmatch(args.head_sha):
        parser.error("PR scope requires full commit SHAs")
    raw = subprocess.check_output([
        "git", "diff", "--no-renames", "--name-only", "-z", args.base_sha, args.head_sha, "--",
    ])
    scope = classify_paths([os.fsdecode(path) for path in raw.split(b"\0") if path])
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        print(f"scope={scope}", file=output)
    print(f"PR CI scope: {scope}")


if __name__ == "__main__":
    main()
