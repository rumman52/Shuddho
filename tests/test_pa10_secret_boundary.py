"""Static job-boundary regressions: source validation must precede PA-10 secrets.

These tests inspect the checked-in workflow topology. They never trigger a
workflow, request real environment secrets or create Render resources.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    (ROOT / ".github/workflows/pa10-staging-prerequisite-preflight.yml", "preflight", False),
    (ROOT / ".github/workflows/provision-pa10-staging-worker.yml", "provision", True),
)


def job_parts(workflow: str) -> tuple[str, dict[str, str]]:
    start = workflow.index("\njobs:\n")
    prefix, remainder = workflow[:start], workflow[start + len("\njobs:\n"):]
    matches = list(re.finditer(r"(?m)^  ([A-Za-z][A-Za-z0-9_-]*):\s*$", remainder))
    if not matches:
        raise AssertionError("Missing top-level jobs")
    jobs = {
        match.group(1): remainder[match.end():(
            matches[index + 1].start() if index + 1 < len(matches) else len(remainder)
        )]
        for index, match in enumerate(matches)
    }
    return prefix, jobs


class PA10SecretBoundaryTests(unittest.TestCase):
    def test_all_secret_bearing_workflows_first_run_unprivileged_source_check(self):
        for path, privileged, paid in WORKFLOWS:
            with self.subTest(workflow=path.name):
                prefix, jobs = job_parts(path.read_text())
                self.assertEqual(set(jobs), {"source_gate", privileged})
                guard = jobs["source_gate"]
                target = jobs[privileged]

                # No secret material or protected environment can enter the
                # unprivileged gate even when a job or checkout step fails.
                self.assertNotIn("secrets.", prefix)
                self.assertNotIn("environment:", prefix)
                self.assertNotIn("secrets.", guard)
                self.assertNotIn("environment:", guard)
                self.assertNotIn("RENDER_API_KEY", guard)
                self.assertNotIn("SHUDDHO_TEMPORAL_API_KEY", guard)
                self.assertNotIn("render ", guard.lower())

                # Least-privilege GitHub API access is confined to gate.
                self.assertIn("      contents: read\n", guard)
                self.assertIn("      actions: read\n", guard)
                self.assertIn("persist-credentials: false", guard)
                self.assertIn("GITHUB_TOKEN: ${{ github.token }}", guard)
                self.assertIn("python3 -m scripts.pa10_source_gate", guard)
                self.assertIn('--sha "${GITHUB_SHA}"', guard)
                self.assertIn("github.ref == 'refs/heads/main'", guard)
                self.assertIn("github.repository == 'rumman52/Shuddho'", guard)
                self.assertNotIn("actions: read", target)

                # Failures/skips must not schedule an environment-bearing job.
                self.assertRegex(target, r"(?m)^    if:.*needs\.source_gate\.result == 'success'")
                self.assertRegex(target, r"(?m)^    needs: source_gate$")
                self.assertRegex(target, r"(?m)^    environment: pa10-staging$")
                self.assertIn("secrets.PA10_RENDER_API_KEY", target)
                self.assertIn("github.repository == 'rumman52/Shuddho'", target)
                self.assertIn("github.ref == 'refs/heads/main'", target)
                self.assertNotIn("scripts.pa10_source_gate", target)
                if paid:
                    self.assertIn("inputs.confirm == 'PROVISION'", guard)
                    self.assertIn("inputs.confirm == 'PROVISION'", target)
                    self.assertIn("Create or repair shuddho-worker-staging", target)
                else:
                    self.assertNotIn("render services create", target)

    def test_source_gate_has_no_elevated_job_token_permissions(self):
        for path, _, _ in WORKFLOWS:
            with self.subTest(workflow=path.name):
                _, jobs = job_parts(path.read_text())
                gate = jobs["source_gate"]
                permissions = gate.split("    permissions:\n", 1)[1].split("    steps:\n", 1)[0]
                self.assertEqual(
                    {line.strip() for line in permissions.splitlines() if line.strip()},
                    {"contents: read", "actions: read"},
                )


if __name__ == "__main__":
    unittest.main()
