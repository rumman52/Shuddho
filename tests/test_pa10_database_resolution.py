"""Run both checked-in database-resolution steps without provider access.

The Render CLI alone is replaced. Bash, jq, and the real lifecycle gate execute
as they do in Actions, so an admission failure must actually stop the shell
before the sensitive connection-info request or GitHub output publication.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github/workflows/pa10-staging-prerequisite-preflight.yml",
    ROOT / ".github/workflows/provision-pa10-staging-worker.yml",
)
DATABASE_URL = "postgresql://fixture-user:fixture-password@fixture.invalid/staging"


def resolution_script(workflow: Path) -> str:
    step = workflow.read_text().split(
        "      - name: Resolve private Render Postgres URL\n", 1
    )[1].split("\n      - name:", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


class DatabaseResolutionTests(unittest.TestCase):
    def run_resolution(self, workflow, metadata, *, cli_exit=0, sensitive=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "calls.jsonl"
            output = root / "github-output"
            render = root / "render"
            render.write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import json, os, sys
                args = sys.argv[1:]
                with open(os.environ['RENDER_CALLS'], 'a') as stream:
                    stream.write(json.dumps(args) + '\\n')
                if args == ['pg', 'get', 'shuddho-staging-db', '--output', 'json']:
                    print(os.environ['RENDER_METADATA'])
                    sys.exit(int(os.environ['RENDER_METADATA_EXIT']))
                if args == ['pg', 'get', 'shuddho-staging-db',
                            '--include-sensitive-connection-info', '--output', 'json']:
                    print(os.environ['RENDER_SENSITIVE'])
                    sys.exit(0)
                sys.exit('Unexpected Render command')
                """))
            render.chmod(0o755)
            if sensitive is None:
                sensitive = {"data": {"connectionInfo": {
                    "internalConnectionString": DATABASE_URL,
                }}}
            result = subprocess.run(
                ["bash", "-c", resolution_script(workflow)],
                cwd=ROOT,
                env=os.environ | {
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "RENDER_CALLS": str(calls),
                    "RENDER_METADATA": metadata,
                    "RENDER_METADATA_EXIT": str(cli_exit),
                    "RENDER_SENSITIVE": json.dumps(sensitive),
                    "GITHUB_OUTPUT": str(output),
                },
                capture_output=True,
                text=True,
                timeout=10,
            )
            return (
                result,
                [json.loads(line) for line in calls.read_text().splitlines()],
                output.read_text() if output.exists() else None,
            )

    def test_unsafe_metadata_stops_before_sensitive_request_and_output(self):
        current = datetime.now(timezone.utc)
        cases = {
            "near expiry": {"data": {"plan": "free", "expiresAt": (
                current + timedelta(days=6)
            ).isoformat()}},
            "expired": {"data": {"plan": "free", "expiresAt": (
                current - timedelta(seconds=1)
            ).isoformat()}},
            "free without expiry": {"data": {"plan": "free"}},
            "custom without expiry": {"data": {"plan": "custom"}},
            "unknown plan": {"data": {"plan": "unreviewed-plan"}},
            "missing plan": {"data": {}},
            "missing envelope": {"plan": "starter"},
            "invalid timestamp": {"data": {"plan": "free", "expiresAt": "invalid"}},
            "naive timestamp": {"data": {"plan": "free", "expiresAt": (
                current + timedelta(days=14)
            ).replace(tzinfo=None).isoformat()}},
        }
        for workflow in WORKFLOWS:
            for label, metadata in cases.items():
                with self.subTest(workflow=workflow.name, case=label):
                    result, calls, output = self.run_resolution(workflow, json.dumps(metadata))
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(calls, [[
                        "pg", "get", "shuddho-staging-db", "--output", "json",
                    ]])
                    self.assertIsNone(output)
                    self.assertNotIn(DATABASE_URL, result.stdout + result.stderr)

    def test_invalid_json_and_cli_failure_stop_before_sensitive_request(self):
        for workflow in WORKFLOWS:
            for metadata, cli_exit in (("not-json", 0), ("{}", 23)):
                with self.subTest(workflow=workflow.name, cli_exit=cli_exit):
                    result, calls, output = self.run_resolution(
                        workflow, metadata, cli_exit=cli_exit,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(len(calls), 1)
                    self.assertNotIn("--include-sensitive-connection-info", calls[0])
                    self.assertIsNone(output)

    def test_safe_metadata_retrieves_then_masks_and_publishes_private_url(self):
        safe_expiry = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        for workflow in WORKFLOWS:
            for metadata in (
                {"data": {"plan": "free", "expiresAt": safe_expiry}},
                {"data": {"plan": "starter", "expiresAt": None}},
            ):
                with self.subTest(workflow=workflow.name, metadata=metadata):
                    result, calls, output = self.run_resolution(workflow, json.dumps(metadata))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(len(calls), 2)
                    self.assertNotIn("--include-sensitive-connection-info", calls[0])
                    self.assertIn("--include-sensitive-connection-info", calls[1])
                    self.assertIn(f"::add-mask::{DATABASE_URL}\n", result.stdout)
                    self.assertEqual(output, f"database_url<<EOF\n{DATABASE_URL}\nEOF\n")

    def test_missing_private_connection_string_never_publishes_output(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                result, calls, output = self.run_resolution(
                    workflow, json.dumps({"data": {"plan": "starter"}}),
                    sensitive={"data": {}},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 2)
                self.assertIsNone(output)


if __name__ == "__main__":
    unittest.main()
