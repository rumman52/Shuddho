"""Execute the provisioning shell with fake Render responses, never live resources."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/provision-pa10-staging-worker.yml"
SHA = "a" * 40
OWNER = "tea-d6ok4okhg0os73erkdv0"


def shell_step(name: str) -> str:
    step = WORKFLOW.read_text().split(f"      - name: {name}\n", 1)[1]
    step = step.split("\n      - name:", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


def worker(**changes):
    value = {
        "id": "srv-test123", "name": "shuddho-worker-staging",
        "type": "background_worker", "ownerId": OWNER,
        "repo": "https://github.com/rumman52/Shuddho",
        "serviceDetails": {"region": "oregon"},
    }
    return value | changes


class WorkerProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = os.environ | {
            "PATH": f"{self.root}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(self.root),
            "GITHUB_REPOSITORY": "rumman52/Shuddho", "GITHUB_REF_NAME": "main",
            "GITHUB_SHA": SHA, "RENDER_WORKSPACE_ID": OWNER,
            "RENDER_API_KEY": "test-only-render", "SHUDDHO_TEMPORAL_ADDRESS": "example:7233",
            "SHUDDHO_TEMPORAL_NAMESPACE": "test-only", "SHUDDHO_TEMPORAL_API_KEY": "test-only-temporal",
            "AWS_ACCESS_KEY_ID": "test-only-access", "AWS_SECRET_ACCESS_KEY": "test-only-secret",
            "SHUDDHO_COWORKER_DATABASE_URL": "postgresql://test-only",
            "WORKER_ID": "srv-test123",
            "GITHUB_OUTPUT": str(self.root / "output"),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary"),
            "RENDER_CALLS": str(self.root / "calls"),
            "FAKE_SERVICES": "[]", "FAKE_CREATED": json.dumps(worker()),
            "FAKE_DEPLOY": json.dumps({"id": "dep-test123", "status": "live", "commit": {"id": SHA}}),
        }
        render = self.root / "render"
        render.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import json, os, sys
            args = sys.argv[1:]
            with open(os.environ['RENDER_CALLS'], 'a') as output:
                output.write(json.dumps(args[:2]) + '\\n')
            if args[:2] == ['services', '--output']:
                print(os.environ['FAKE_SERVICES'])
            elif args[:2] == ['services', 'create']:
                print(os.environ['FAKE_CREATED'])
            elif args[:2] == ['services', 'update']:
                print('{}')
            elif args[:2] == ['deploys', 'create']:
                assert args[args.index('--commit') + 1] == os.environ['GITHUB_SHA']
                assert '--wait' in args
                print(os.environ['FAKE_DEPLOY'])
                sys.exit(int(os.environ.get('FAKE_DEPLOY_EXIT', '0')))
            else:
                sys.exit('Unexpected Render command')
            """))
        render.chmod(0o755)

    def run_step(self, name, **env):
        return subprocess.run(["bash", "-c", shell_step(name)], env=self.env | env,
                              capture_output=True, text=True, timeout=10)

    def test_missing_secrets_fail_without_printing_values(self):
        for key in ("RENDER_API_KEY", "SHUDDHO_TEMPORAL_ADDRESS", "SHUDDHO_TEMPORAL_NAMESPACE",
                    "SHUDDHO_TEMPORAL_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            with self.subTest(key=key):
                result = self.run_step("Guard staging-only execution and required secrets", **{key: ""})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stdout)
                self.assertNotIn("test-only-secret", result.stdout + result.stderr)
        self.assertFalse((self.root / "calls").exists())

    def test_guard_rejects_wrong_repository_branch_and_http_address(self):
        for values in ({"GITHUB_REPOSITORY": "other/repo"}, {"GITHUB_REF_NAME": "feature"},
                       {"SHUDDHO_TEMPORAL_ADDRESS": "https://example:7233"}):
            self.assertNotEqual(self.run_step("Guard staging-only execution and required secrets", **values).returncode, 0)
        self.assertEqual(self.run_step("Guard staging-only execution and required secrets").returncode, 0)

    def test_create_and_repair_target_worker(self):
        for services in ([], [{"service": worker()}]):
            with self.subTest(services=services):
                result = self.run_step("Create or repair shuddho-worker-staging", FAKE_SERVICES=json.dumps(services))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("worker_id=srv-test123", (self.root / "output").read_text())

    def test_ambiguous_and_unrelated_workers_are_not_mutated(self):
        cases = [[worker(), worker(id="srv-second")]]
        cases += [[worker(**change)] for change in (
            {"type": "web_service"}, {"ownerId": "tea-other"},
            {"repo": "https://github.com/other/repo"}, {"serviceDetails": {"region": "frankfurt"}},
        )]
        for services in cases:
            with self.subTest(services=services):
                (self.root / "calls").unlink(missing_ok=True)
                result = self.run_step("Create or repair shuddho-worker-staging", FAKE_SERVICES=json.dumps(services))
                self.assertNotEqual(result.returncode, 0)
                calls = (self.root / "calls").read_text()
                self.assertNotIn('"create"', calls)
                self.assertNotIn('"update"', calls)

    def test_malformed_create_response_fails(self):
        for value in ({}, worker(id="not-a-service"), worker(type="web_service")):
            result = self.run_step("Create or repair shuddho-worker-staging", FAKE_CREATED=json.dumps(value))
            self.assertNotEqual(result.returncode, 0)

    def test_exact_live_deploy_passes(self):
        result = self.run_step("Deploy exact main revision and require migration success")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["commit"], SHA)

    def test_failed_mismatched_and_malformed_deploys_fail(self):
        for value in (
            {"id": "dep-test123", "status": "live", "commit": {"id": "b" * 40}},
            {"id": "dep-test123", "status": "build_failed", "commit": {"id": SHA}},
            {"id": "dep-test123", "status": "live"}, {},
        ):
            result = self.run_step("Deploy exact main revision and require migration success", FAKE_DEPLOY=json.dumps(value))
            self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.run_step("Deploy exact main revision and require migration success", FAKE_DEPLOY_EXIT="1").returncode, 0)

    def test_summary_preserves_identifiers_without_running_commands(self):
        result = self.run_step("Emit non-secret worker reference")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        summary = (self.root / "summary").read_text()
        for value in ("`shuddho-worker-staging`", "`srv-test123`", f"`{SHA}`", "`shuddho-documents-v1`", "NOT VERIFIED"):
            self.assertIn(value, summary)


if __name__ == "__main__":
    unittest.main()
