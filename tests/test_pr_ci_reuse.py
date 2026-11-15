from pathlib import Path

import pytest

from scripts import pr_ci_reuse as reuse
from scripts.independent_review_gate import ReviewGateError


HEAD = "a" * 40
MERGE = "b" * 40


def run(**changes):
    return {
        "id": 20, "run_attempt": 1, "path": reuse.CI_PATH, "event": "pull_request",
        "head_sha": HEAD, "display_title": reuse.ci_title(4, MERGE),
        "status": "completed", "conclusion": "failure", **changes,
    }


def response(key, items):
    return {key: items, "total_count": len(items)}


def jobs():
    return [{"name": name, "status": "completed", "conclusion": "success"} for name in reuse.TEST_JOBS]


@pytest.mark.parametrize("changes", [
    {"head_sha": "c" * 40}, {"display_title": reuse.ci_title(4, "c" * 40)},
    {"display_title": reuse.ci_title(5, MERGE)}, {"event": "pull_request_review"},
    {"path": ".github/workflows/other.yml"},
])
def test_only_exact_pr_and_test_merge_commit_are_reusable(changes):
    assert reuse.select_ci_run(response("workflow_runs", [run(**changes)]), 4, HEAD, MERGE) is None


def test_newer_attempt_wins_and_technical_results_can_pass_without_prior_approval(monkeypatch):
    older = run(status="completed", conclusion="success")
    pending = run(id=21, status="in_progress", conclusion=None)
    recent = run(id=21)
    snapshots = iter([pending, recent, recent])
    seen = []

    def read(url, token):
        assert token == "fixture"
        if "/workflows/ci.yml/runs?" in url:
            assert f"head_sha={HEAD}" in url
            return response("workflow_runs", [older, next(snapshots)])
        assert url.endswith("/runs/21/jobs?per_page=100&filter=latest")
        values = jobs()
        if not seen:
            values[-1].update(status="in_progress", conclusion=None)
        seen.append(url)
        return response("jobs", values)

    monkeypatch.setattr(reuse, "_get_json", read)
    monkeypatch.setattr(reuse.time, "sleep", lambda _: None)
    assert reuse.await_tested_pr("owner/repo", 4, HEAD, MERGE, "fixture") == 21
    assert len(seen) == 2


@pytest.mark.parametrize("mode", ["failed", "skipped", "missing", "duplicate", "truncated"])
def test_reuse_fails_closed_without_all_passing_jobs(mode):
    values = jobs()
    if mode in {"failed", "skipped"}:
        values[0]["conclusion"] = "failure" if mode == "failed" else "skipped"
    elif mode == "missing":
        values.pop()
    elif mode == "duplicate":
        values.append(values[0])
    payload = response("jobs", values)
    if mode == "truncated":
        payload["total_count"] += 1
    with pytest.raises(ReviewGateError):
        reuse.tested_jobs(payload, complete=True)


def test_review_run_keeps_required_check_names_and_polls_without_running_suites():
    workflow = Path(".github/workflows/ci.yml").read_text()
    assert "github.event_name == 'pull_request_review' && 'review' || 'checks'" in workflow
    for name in ("test-and-build", "frontend", "coworker", "browser-qualification", "postgres-18-qualification"):
        job = workflow.split(f"\n  {name}:\n", 1)[1].split("    steps:\n", 1)[0]
        assert "if: github.event_name != 'pull_request_review'" in job
    for name in ("test-and-build", "coworker"):
        assert f"'Omitted {name} on review' || '{name}'" in workflow
    reuse_step, review_step = workflow.split("      - name: Reuse exact PR test results on a review", 1)[1].split("      - name: Require independent current-head review", 1)
    assert "if: github.event_name == 'pull_request_review'" in reuse_step
    assert "--head-sha \"$PR_HEAD_SHA\" --merge-sha \"$GITHUB_SHA\"" in reuse_step
    assert "scripts.independent_review_gate" in review_step
