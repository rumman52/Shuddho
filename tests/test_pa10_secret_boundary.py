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
                expected_jobs = {"source_gate", "ruleset_audit", privileged}
                if paid:
                    expected_jobs.add("verify_database")
                self.assertEqual(set(jobs), expected_jobs)
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
                self.assertIn("--ci-only", guard)
                self.assertIn("github.ref == 'refs/heads/main'", guard)
                self.assertIn("github.repository == 'rumman52/Shuddho'", guard)
                self.assertNotIn("actions: read", target)

                # Failures/skips must not schedule an environment-bearing job.
                self.assertRegex(target, r"(?m)^    if:.*needs\.source_gate\.result == 'success'")
                expected_needs = "[source_gate, ruleset_audit, verify_database]" if paid else "[source_gate, ruleset_audit]"
                self.assertIn(f"\n    needs: {expected_needs}\n", target)
                self.assertRegex(target, r"(?m)^    if:.*needs\.ruleset_audit\.result == 'success'")
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

    def test_paid_provisioning_requires_a_separate_read_only_database_check(self):
        _, jobs = job_parts(WORKFLOWS[1][0].read_text())
        check = jobs["verify_database"]
        self.assertIn("\n    needs: [source_gate, ruleset_audit]\n", check)
        self.assertRegex(check, r"(?m)^    if:.*needs\.source_gate\.result == 'success'")
        self.assertRegex(check, r"(?m)^    if:.*needs\.ruleset_audit\.result == 'success'")
        self.assertIn("\n    environment: pa10-staging\n", check)
        self.assertIn("persist-credentials: false", check)
        audit = "uses: ./.github/actions/audit-main-ruleset"
        setup, readiness = check.split("- name: Verify live staging database before paid provisioning", 1)
        self.assertIn(audit, setup)
        self.assertIn("secrets.V01_RULESET_APP_PRIVATE_KEY", setup)
        self.assertNotIn("PA10_STAGING_DATABASE_URL", setup)
        self.assertEqual(readiness.count("secrets."), 1)
        self.assertIn("secrets.PA10_STAGING_DATABASE_URL", readiness)
        self.assertIn("SHUDDHO_COWORKER_ENV: staging", readiness)
        self.assertLess(readiness.index("_validate_postgresql_url("), readiness.index("services.coworker.migrate --check"))
        self.assertRegex(jobs["provision"], r"(?m)^    if:.*needs\.verify_database\.result == 'success'")

    def test_live_ruleset_audit_is_confined_to_main_and_staging_environments(self):
        for path, privileged, paid in WORKFLOWS:
            with self.subTest(workflow=path.name):
                prefix, jobs = job_parts(path.read_text())
                audit = jobs["ruleset_audit"]
                self.assertIn("\n    needs: source_gate\n", audit)
                self.assertRegex(audit, r"(?m)^    if:.*needs\.source_gate\.result == 'success'")
                self.assertIn("github.repository == 'rumman52/Shuddho'", audit)
                self.assertIn("github.ref == 'refs/heads/main'", audit)
                if paid:
                    self.assertIn("inputs.confirm == 'PROVISION'", audit)
                self.assertIn("environment: v01-governance", audit)
                self.assertIn("persist-credentials: false", audit)
                self.assertIn("uses: ./.github/actions/audit-main-ruleset", audit)
                self.assertIn("secrets.V01_RULESET_APP_PRIVATE_KEY", audit)
                self.assertNotIn("PA10_", audit)
                self.assertNotIn("V01_RULESET_APP_", prefix + jobs["source_gate"])
                self.assertIn("secrets.V01_RULESET_APP_PRIVATE_KEY", jobs[privileged])
                if paid:
                    self.assertIn("secrets.V01_RULESET_APP_PRIVATE_KEY", jobs["verify_database"])

    def test_main_is_rechecked_after_approval_and_before_provider_side_effects(self):
        audit = "uses: ./.github/actions/audit-main-ruleset"
        for path, privileged, paid in WORKFLOWS:
            with self.subTest(workflow=path.name):
                _, jobs = job_parts(path.read_text())
                source = jobs["source_gate"]
                target = jobs[privileged]
                self.assertNotIn("pa10_main_head_guard", source)
                self.assertIn("persist-credentials: false", target)
                positions = [match.start() for match in re.finditer(re.escape(audit), target)]
                self.assertEqual(len(positions), 3 if paid else 1)
                self.assertLess(target.index("- name: Guard staging-only execution"), positions[0])
                if paid:
                    check = jobs["verify_database"]
                    self.assertEqual(check.count(audit), 1)
                    self.assertLess(check.index(audit), check.index("- name: Verify live staging database before paid provisioning"))
                    self.assertLess(positions[0], target.index("- name: Require Render access before"))
                    self.assertLess(positions[1], target.index("- name: Create or repair shuddho-worker-staging"))
                    self.assertLess(positions[2], target.index("- name: Deploy exact main revision and require database readiness"))
                else:
                    self.assertLess(positions[0], target.index("- name: Set up Python"))

    def test_staging_database_secret_is_confined_to_steps_using_it(self):
        connection = "SHUDDHO_COWORKER_DATABASE_URL: ${{ secrets.PA10_STAGING_DATABASE_URL }}"
        for path, privileged, paid in WORKFLOWS:
            with self.subTest(workflow=path.name):
                prefix, jobs = job_parts(path.read_text())
                self.assertNotIn("PA10_STAGING_DATABASE_URL", prefix + jobs["source_gate"])
                target = jobs[privileged]
                self.assertNotIn("PA10_STAGING_DATABASE_URL", target.split("    steps:", 1)[0])
                self.assertNotIn("render pg get", target)
                self.assertNotIn("steps.postgres.outputs", target)
                preflight = target.split("      - name: Validate staging prerequisites", 1)[1]
                preflight = preflight.split("      - name:", 1)[0]
                self.assertIn(connection, preflight)
                self.assertEqual(target.count(connection), 2 if paid else 1)
                if paid:
                    reconcile = target.split("      - name: Reconcile reviewed worker environment", 1)[1]
                    self.assertIn(connection, reconcile.split("      - name:", 1)[0])

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
