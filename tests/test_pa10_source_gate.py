"""Mocked source-gate regressions; no network, paid service or credentials."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from scripts.pa10_source_gate import SourceGateError, inspect_source, require_qualified_source

SHA = "a" * 40
RUN_ID = 204
ROOT = "https://api.github.com/repos/rumman52/Shuddho"
NAMES = ("test-and-build", "coworker", "governance-audit", "ci-merge-gate")


def fixture():
    branch = {"name": "main", "protected": True, "commit": {"sha": SHA}}
    runs = {"total_count": 1, "workflow_runs": [{"id": RUN_ID, "head_sha": SHA,
        "head_branch": "main", "event": "push", "path": ".github/workflows/ci.yml",
        "status": "completed", "conclusion": "success"}]}
    jobs = {"total_count": 4, "jobs": [{"name": x, "status": "completed", "conclusion": "success"} for x in NAMES]}
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

    def test_invalid_repo_sha_token_fails_before_external_access(self):
        for repo,sha,token in (("other/repo",SHA,"x"),("rumman52/Shuddho","../xx","x"),
                               ("rumman52/Shuddho",SHA,"")):
            with patch("scripts.pa10_source_gate.inspect_repository") as probe:
                with self.assertRaises(SourceGateError): inspect_source(repo,sha,token)
                probe.assert_not_called()


if __name__=="__main__":unittest.main()
