"""Fail-closed source qualification for manually dispatched PA-10 staging provisioning.

This is a defense-in-depth *precondition*, not a replacement for native GitHub
branch protection, independent review, or an operated release qualification.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from urllib.parse import urlencode

from scripts.main_protection_audit import GovernanceAuditError, _get_json, inspect_repository

REPOSITORY = "rumman52/Shuddho"
REQUIRED_JOBS = frozenset({"test-and-build", "coworker", "governance-audit", "ci-merge-gate"})


class SourceGateError(ValueError):
    """The dispatched source has not met the read-only staging entry gate."""


def require_qualified_source(branch: object, runs: object, jobs: object, sha: str) -> int:
    """Return the qualified push workflow run ID, or reject incomplete evidence."""
    if not isinstance(branch, dict) or branch.get("name") != "main":
        raise SourceGateError("main branch identity could not be confirmed")
    commit = branch.get("commit")
    if not isinstance(commit, dict) or commit.get("sha") != sha:
        raise SourceGateError("dispatched revision is not the current main head")
    if branch.get("protected") is not True:
        raise SourceGateError("native main branch protection is not enabled")
    if not isinstance(runs, dict) or type(runs.get("total_count")) is not int:
        raise SourceGateError("CI workflow results unavailable")
    records = runs.get("workflow_runs")
    if not isinstance(records, list) or runs["total_count"] < 1 or runs["total_count"] > len(records):
        raise SourceGateError("CI workflow results missing or truncated")
    candidates = [run for run in records if isinstance(run, dict) and run.get("head_sha") == sha]
    if len(candidates) != runs["total_count"]:
        raise SourceGateError("CI workflow results include an unexpected revision")
    latest = max(candidates, key=lambda run: run.get("id") if type(run.get("id")) is int else -1)
    run_id = latest.get("id")
    if (
        type(run_id) is not int or run_id <= 0
        or latest.get("head_branch") != "main"
        or latest.get("event") != "push"
        or latest.get("path") != ".github/workflows/ci.yml"
        or latest.get("status") != "completed"
        or latest.get("conclusion") != "success"
    ):
        raise SourceGateError("latest exact-head main CI workflow is not successful")
    if not isinstance(jobs, dict) or type(jobs.get("total_count")) is not int:
        raise SourceGateError("CI job results unavailable")
    entries = jobs.get("jobs")
    if not isinstance(entries, list) or jobs["total_count"] != len(entries):
        raise SourceGateError("CI job results missing or truncated")
    for name in REQUIRED_JOBS:
        matched = [j for j in entries if isinstance(j, dict) and j.get("name") == name]
        if len(matched) != 1 or matched[0].get("conclusion") != "success" or matched[0].get("status") != "completed":
            raise SourceGateError("mandatory CI job missing, duplicated, skipped, or unsuccessful: " + name)
    return run_id


def inspect_source(repository: str, sha: str, token: str) -> tuple[int, int]:
    if repository != REPOSITORY or re.fullmatch(r"[0-9a-f]{40}", sha) is None or not token:
        raise SourceGateError("invalid repository, source SHA, or missing GitHub token")
    # This existing audit verifies a candidate *native ruleset configuration*;
    # it intentionally does not assert a negative-control merge-button test.
    rule_id = inspect_repository(repository, token)
    root = f"https://api.github.com/repos/{REPOSITORY}"
    branch = _get_json(root + "/branches/main", token)
    query = urlencode({"branch": "main", "event": "push", "head_sha": sha, "per_page": 100})
    runs = _get_json(root + "/actions/workflows/ci.yml/runs?" + query, token)
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        raise SourceGateError("CI workflow results unavailable")
    # Do not fetch jobs for a failed/pending or ambiguous run.
    records = runs["workflow_runs"]
    if not records or any(not isinstance(x, dict) or type(x.get("id")) is not int for x in records):
        raise SourceGateError("CI workflow run list invalid")
    latest = max(records, key=lambda item: item["id"])
    run_id = latest["id"]
    if run_id <= 0:
        raise SourceGateError("invalid CI workflow run identifier")
    jobs = _get_json(root + f"/actions/runs/{run_id}/jobs?per_page=100&filter=latest", token)
    return rule_id, require_qualified_source(branch, runs, jobs, sha)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        rule_id, run_id = inspect_source(args.repository, args.sha, os.getenv("GITHUB_TOKEN", ""))
    except (SourceGateError, GovernanceAuditError) as exc:
        parser.exit(1, f"PA-10 source entry gate BLOCKED: {exc}\n")
    print(json.dumps({"status": "source_preflight_only", "ruleset_id": rule_id, "ci_run_id": run_id,
                      "staging_qualified": False, "production_qualified": False}))


if __name__ == "__main__":
    main()
