"""Read-only PA-10 main-head revalidation after staging environment approval.

The first source_gate job qualifies the dispatch before protected-environment
secrets become eligible. A human environment approval can delay the next job,
so revalidate main again before any Render, Temporal, storage or DB operations.
This is defense in depth, not a substitute for native branch/ruleset controls.
"""
from __future__ import annotations

import argparse
import json
import os
import re

from scripts.main_protection_audit import GovernanceAuditError, _get_json

REPOSITORY = "rumman52/Shuddho"
API_ROOT = "https://api.github.com/repos/" + REPOSITORY


class MainHeadChanged(ValueError):
    """The approved dispatch SHA cannot safely enter provider operations."""


def require_current_main(branch: object, sha: str) -> None:
    if not isinstance(branch, dict) or branch.get("name") != "main":
        raise MainHeadChanged("main branch identity unavailable")
    if branch.get("protected") is not True:
        raise MainHeadChanged("main is not protected")
    commit = branch.get("commit")
    if not isinstance(commit, dict) or commit.get("sha") != sha:
        raise MainHeadChanged("main has advanced since source admission; new approval required")


def inspect_current_main(repository: str, sha: str, token: str) -> None:
    # Reject untrusted endpoint path/host changes and invalid SHA before IO.
    if repository != REPOSITORY or re.fullmatch(r"[0-9a-f]{40}", sha) is None or not token:
        raise MainHeadChanged("invalid repository, dispatch SHA, or missing GitHub token")
    branch = _get_json(API_ROOT + "/branches/main", token)
    require_current_main(branch, sha)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        inspect_current_main(args.repository, args.sha, os.getenv("GITHUB_TOKEN", ""))
    except (MainHeadChanged, GovernanceAuditError) as exc:
        parser.exit(1, f"PA-10 provider-entry revalidation BLOCKED: {exc}\n")
    print(json.dumps({"status": "main_head_revalidated", "sha": args.sha,
                      "staging_qualified": False, "production_qualified": False}))


if __name__ == "__main__":
    main()
