"""Mocked source-gate regressions; no network, paid service or credentials."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import pytest

from scripts.pa10_source_gate import SourceGateError, inspect_source, require_qualified_source

SHA = "a" * 40
RUN_ID = 204
ROOT = "https://api.github.com/repos/rumman52/Shuddho"
NAMES = (
    "test-and-build", "coworker", "governance-audit", "ci-merge-gate",
    "Frontend tests and builds", "browser-qualification", "PostgreSQL 18 staging compatibility",
)


def fixture():
    branch = {"name": "main", "protected": True, "commit": {"sha": SHA}}
    runs = {"total_count": 1, "workflow_runs": [{"id": RUN_ID, "head_sha": SHA,
        "head_branch": "main", "event": "push", "path": ".github/workflows/ci.yml",
        "status": "completed", "conclusion": "success"}]}
    jobs = {"total_count": len(NAMES), "jobs": [
        {"id": i, "run_id": RUN_ID, "head_sha": SHA, "name": name,
         "status": "completed", "conclusion": "success"}
        for i, name in enumerate(NAMES, start=1)
    ]}
    return branch, runs, jobs


class GateTests(unittest.TestCase):
    def test_complete_exact_main_passes(self):
        self.assertEqual(require_qualified_source(*fixture(), SHA), RUN_ID)

    def test_unprotected_or_stale_head_fails(self):
        for mutate in (lambda b,r,j: b.update(protected=False),
                       lambda b,r,j: b["commit"].update(sha="b" * 40)):
            with self.subTest(mutate=mutate):
                b,r,j=fixture(); mutate(b,r,j)
                with self.assertRaises(SourceGateError): require_qualified_source(b,r,j,SHA)

    def test_unsuccessful_and_skipped_jobs_fail(self):
        for bad in ("failure", "skipped", "cancelled", None):
            with self.subTest(bad=bad):
                b,r,j=fixture(); j["jobs"][2]["conclusion"]=bad
                with self.assertRaises(SourceGateError): require_qualified_source(b,r,j,SHA)

    def test_missing_duplicate_and_truncated_jobs_fail(self):
        for key in ("missing", "duplicate", "truncated"):
            with self.subTest(key=key):
                b,r,j=fixture()
                if key=="missing": j["jobs"].pop();j["total_count"]-=1
                elif key=="duplicate":j["jobs"].append(copy.copy(j["jobs"][0]));j["total_count"]+=1
                else:j["total_count"]+=1
                with self.assertRaises(SourceGateError): require_qualified_source(b,r,j,SHA)

    def test_wrong_event_workflow_or_pending_fails(self):
        for field,value in (("head_sha","b"*40),("event","pull_request"),
                            ("path",".github/workflows/other.yml"),
                            ("conclusion","failure"),("status","in_progress")):
            with self.subTest(field=field):
                b,r,j=fixture();r["workflow_runs"][0][field]=value
                with self.assertRaises(SourceGateError): require_qualified_source(b,r,j,SHA)

    def test_newer_incomplete_run_cannot_use_older_success(self):
        b,r,j=fixture()
        bad=copy.deepcopy(r["workflow_runs"][0]);bad.update(id=RUN_ID+1,status="in_progress",conclusion=None)
        r["workflow_runs"].append(bad);r["total_count"]=2
        with self.assertRaises(SourceGateError): require_qualified_source(b,r,j,SHA)

    def test_ci_only_source_gate_defers_protection_to_separate_privileged_audit(self):
        b,r,j=fixture()
        b["protected"] = False

        def fake_get(url,token):
            self.assertEqual(token,"test-token")
            if url == ROOT+"/branches/main": return b
            if "/workflows/ci.yml/runs?" in url: return r
            if url == ROOT+f"/actions/runs/{RUN_ID}/jobs?per_page=100&filter=latest": return j
            raise AssertionError(url)

        with patch("scripts.pa10_source_gate.inspect_repository") as audit,\
             patch("scripts.pa10_source_gate._get_json",side_effect=fake_get):
            self.assertEqual(inspect_source("rumman52/Shuddho",SHA,"test-token",ci_only=True),(None,RUN_ID))
            audit.assert_not_called()

    def test_network_fetch_is_pinned_and_matches_selected_run(self):
        b,r,j=fixture()
        def fake_get(url,token):
            self.assertEqual(token,"test-token")
            if url==ROOT+"/branches/main":return b
            if "/workflows/ci.yml/runs?" in url:
                self.assertIn("head_sha="+SHA,url);return r
            if url==ROOT+f"/actions/runs/{RUN_ID}/jobs?per_page=100&filter=latest":return j
            raise AssertionError(url)
        with patch("scripts.pa10_source_gate.inspect_repository",return_value=11),\
             patch("scripts.pa10_source_gate._get_json",side_effect=fake_get):
            self.assertEqual(inspect_source("rumman52/Shuddho",SHA,"test-token"),(11,RUN_ID))
        with patch("scripts.pa10_source_gate.inspect_repository") as audit,\
             patch("scripts.pa10_source_gate._get_json",side_effect=fake_get):
            self.assertEqual(inspect_source("rumman52/Shuddho",SHA,"test-token",ci_only=True),(None,RUN_ID))
            audit.assert_not_called()

    def test_invalid_repo_sha_token_fails_before_external_access(self):
        for repo,sha,token in (("other/repo",SHA,"x"),("rumman52/Shuddho","../xx","x"),
                               ("rumman52/Shuddho",SHA,"")):
            with patch("scripts.pa10_source_gate.inspect_repository") as probe:
                with self.assertRaises(SourceGateError): inspect_source(repo,sha,token)
                probe.assert_not_called()


@pytest.mark.parametrize("name", NAMES[4:])
@pytest.mark.parametrize("conclusion", ["missing", "skipped", "failure"])
def test_source_gate_requires_each_individual_main_job(name, conclusion):
    branch, runs, jobs = fixture()
    row = next(row for row in jobs["jobs"] if row["name"] == name)
    if conclusion == "missing":
        jobs["jobs"].remove(row)
        jobs["total_count"] -= 1
    else:
        row["conclusion"] = conclusion
    with pytest.raises(SourceGateError, match=name):
        require_qualified_source(branch, runs, jobs, SHA)


@pytest.mark.parametrize("field,value", [
    ("run_id", RUN_ID + 1), ("run_id", None), ("run_id", float(RUN_ID)),
    ("head_sha", "b" * 40), ("head_sha", None),
    ("id", 0), ("id", True), ("id", 2),
])
def test_source_gate_rejects_unbound_or_ambiguous_job_records(field, value):
    branch, runs, jobs = fixture()
    jobs["jobs"][0][field] = value
    with pytest.raises(SourceGateError, match="job"):
        require_qualified_source(branch, runs, jobs, SHA)


@pytest.mark.parametrize("kind", ["extra", "duplicate", "invalid_id"])
def test_source_gate_rejects_ambiguous_workflow_run_lists(kind):
    branch, runs, jobs = fixture()
    row = copy.deepcopy(runs["workflow_runs"][0])
    if kind == "extra":
        row["head_sha"] = "b" * 40
    else:
        runs["total_count"] += 1
        if kind == "invalid_id":
            row["id"] = False
    runs["workflow_runs"].append(row)
    with pytest.raises(SourceGateError, match="CI workflow"):
        require_qualified_source(branch, runs, jobs, SHA)


def test_main_source_gate_allows_skipped_pr_only_ancestry():
    branch, runs, jobs = fixture()
    jobs["jobs"].append({"id": 100, "run_id": RUN_ID, "head_sha": SHA,
                         "name": "PR head ancestry", "status": "completed",
                         "conclusion": "skipped"})
    jobs["total_count"] += 1
    assert require_qualified_source(branch, runs, jobs, SHA) == RUN_ID


if __name__=="__main__":unittest.main()
