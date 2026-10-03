"""Exercise the actual installer shell against a release-shaped local archive."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
import zipfile


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/provision-pa10-staging-worker.yml"


class RenderCliInstallTests(unittest.TestCase):
    def run_installer(self, corrupt=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, release, binary, runner = [root / name for name in ("checkout", "release", "bin", "runner")]
            for path in (checkout, release, binary, runner):
                path.mkdir()
            (checkout / "README.md").write_text("Repository README\n")
            asset = "cli_2.28.0_linux_amd64.zip"
            with zipfile.ZipFile(release / asset, "w") as archive:
                archive.writestr("README.md", "CLI README\n")
                archive.writestr("cli_v2.28.0", "#!/bin/sh\necho render-test-version\n")
            digest = hashlib.sha256((release / asset).read_bytes()).hexdigest()
            if corrupt:
                digest = "0" * 64
            (release / "cli_2.28.0_SHA256SUMS").write_text(f"{digest}  {asset}\n")
            (binary / "curl").write_text('#!/bin/bash\nset -eu\nurl="${@: -1}"\ncp "$FIXTURE_RELEASE/${url##*/}" .\n')
            (binary / "sudo").write_text('#!/bin/bash\nset -eu\n[[ "$1" == install && "$2" == -m && "$3" == 0755 ]]\ninstall -m 0755 "$4" "$FIXTURE_BIN/render"\n')
            for name in ("curl", "sudo"):
                (binary / name).chmod(0o755)
            workflow = WORKFLOW.read_text()
            step = workflow.split("      - name: Install pinned Render CLI\n", 1)[1].split("\n      - name:", 1)[0]
            shell = textwrap.dedent(step.split("        run: |\n", 1)[1])
            result = subprocess.run(
                ["bash", "-c", shell], cwd=checkout, input="", capture_output=True,
                text=True, timeout=10,
                env={"PATH": f"{binary}:/usr/bin:/bin", "RUNNER_TEMP": str(runner),
                     "FIXTURE_RELEASE": str(release), "FIXTURE_BIN": str(binary)},
            )
            self.assertEqual((checkout / "README.md").read_text(), "Repository README\n")
            if corrupt:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((binary / "render").exists())
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("render-test-version", result.stdout)
                self.assertEqual(sorted(p.name for p in checkout.iterdir()), ["README.md"])

    def test_archive_readme_does_not_collide_with_checkout(self):
        self.run_installer()

    def test_checksum_failure_prevents_install(self):
        self.run_installer(corrupt=True)


if __name__ == "__main__":
    unittest.main()
