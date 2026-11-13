"""Fail closed when a pull request head omits its target branch commit.

This is defense in depth; native protected-main required checks and independent
review are still necessary to prevent bypasses outside GitHub Actions.
"""
from __future__ import annotations

import argparse
import re
import subprocess

_SHA = re.compile(r"[0-9a-f]{40}\Z")


class StalePullRequest(ValueError):
    """The PR cannot be shown to contain the chosen base commit."""


def verify_base_ancestry(base_sha: str, head_sha: str, *, cwd: str | None = None) -> None:
    """Verify the *PR head*, not GitHub Actions' synthetic PR merge commit."""
    if not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha):
        raise StalePullRequest("Invalid base commit SHA; ancestry not verified.")
    if not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha):
        raise StalePullRequest("Invalid PR head SHA; ancestry not verified.")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_sha],
        cwd=cwd, check=False, capture_output=True, text=True,
    )
    if result.returncode == 1:
        raise StalePullRequest(
            "PR head does not contain the target branch commit. Rebase onto the "
            "current base and rerun exact-head checks before review/merge."
        )
    if result.returncode != 0:
        raise StalePullRequest(
            "Cannot verify PR ancestry (commit missing or Git checkout incomplete)."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    try:
        verify_base_ancestry(args.base_sha, args.head_sha)
    except StalePullRequest as exc:
        parser.exit(1, f"PR ancestry gate failed: {exc}\n")
    print("PR ancestry gate passed: exact head includes target base.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
