"""Exercise the actual preflight summary shell without provider credentials."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/pa10-staging-prerequisite-preflight.yml"
)


class PreflightSummaryTests(unittest.TestCase):
    def test_summary_preserves_literal_labels_without_executing_them(self):
        workflow = WORKFLOW.read_text()
        step = workflow.split(
            "      - name: Emit non-secret readiness summary\n", 1
        )[1].split("\n      - name:", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.md"
            calls = root / "unexpected-commands"
            labels = ("shuddho-documents-v1", "s3", "shuddho-coworker-staging")
            for label in labels:
                command = root / label
                command.write_text(
                    '#!/bin/sh\nprintf "called\\n" >> "$UNEXPECTED_COMMANDS"\n'
                    "exit 73\n"
                )
                command.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", "-c", script],
                env={
                    "PATH": f"{root}:/usr/bin:/bin",
                    "GITHUB_STEP_SUMMARY": str(summary),
                    "UNEXPECTED_COMMANDS": str(calls),
                },
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(calls.exists(), "Summary labels were executed as commands")
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.stdout, "")
            rendered = summary.read_text()
            for line in (
                "- Task queue: `shuddho-documents-v1`",
                "- Storage backend: `s3`",
                "- Bucket: `shuddho-coworker-staging`",
                "- This workflow performs no Render provisioning, provider calls, or paid-resource creation",
            ):
                self.assertIn(line, rendered)


if __name__ == "__main__":
    unittest.main()
