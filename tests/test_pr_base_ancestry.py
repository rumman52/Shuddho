"""Tests against real local Git DAGs: do not trust a PR merge checkout."""
from pathlib import Path
import subprocess

import pytest

from scripts.pr_base_ancestry import StalePullRequest, verify_base_ancestry


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          text=True, capture_output=True).stdout.strip()


def dag(tmp_path: Path) -> tuple[str, str, str]:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Synthetic CI")
    git(tmp_path, "config", "user.email", "ci@example.test")
    (tmp_path / "first.txt").write_text("root\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "first")
    original = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "-c", "feature")
    (tmp_path / "feature.txt").write_text("feature\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "feature")
    head = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "main")
    (tmp_path / "base.txt").write_text("new main\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "new main")
    new_base = git(tmp_path, "rev-parse", "HEAD")
    return original, head, new_base


def test_stale_head_fails_even_if_github_would_create_merge_commit(tmp_path):
    original, head, newer_base = dag(tmp_path)
    verify_base_ancestry(original, head, cwd=str(tmp_path))
    with pytest.raises(StalePullRequest, match="does not contain"):
        verify_base_ancestry(newer_base, head, cwd=str(tmp_path))


def test_rebased_head_passes(tmp_path):
    _, _, new_base = dag(tmp_path)
    git(tmp_path, "switch", "feature")
    git(tmp_path, "merge", "--no-edit", "main")
    refreshed = git(tmp_path, "rev-parse", "HEAD")
    verify_base_ancestry(new_base, refreshed, cwd=str(tmp_path))


def test_missing_and_malformed_commits_fail_closed(tmp_path):
    original, head, _ = dag(tmp_path)
    for base in ("", "a" * 39, "x" * 40, "a" * 40):
        with pytest.raises(StalePullRequest):
            verify_base_ancestry(base, head, cwd=str(tmp_path))
    for bad_head in ("", "1" * 41, "abc; touch /tmp/unwanted", "b" * 40):
        with pytest.raises(StalePullRequest):
            verify_base_ancestry(original, bad_head, cwd=str(tmp_path))
