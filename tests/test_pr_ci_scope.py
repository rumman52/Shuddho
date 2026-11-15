import subprocess
import sys
from pathlib import Path

import pytest

from scripts.pr_ci_scope import classify_paths


@pytest.mark.parametrize(("paths", "expected"), [
    (["README.md", "docs/guides/quickstart.md"], "docs"),
    (["apps/web-editor/src/App.tsx", "docs/guides/quickstart.md"], "frontend"),
    (["apps/coworker/test/navigation.test.mjs", "apps/editor/public/logo.png"], "frontend"),
    (["apps/web-editor/src/App.tsx", "package-lock.json"], "full"),
    (["apps/web-editor/vite.config.ts"], "full"),
    (["services/api/shuddho_api/app.py"], "full"),
    (["docs/staging-evidence.template.json"], "full"),
    (["infra/render.staging.yaml", ".github/workflows/ci.yml"], "full"),
    ([], "full"),
])
def test_ci_uses_full_suite_for_changes_outside_the_allowlist(paths, expected):
    assert classify_paths(paths) == expected


def test_renaming_backend_code_to_documentation_still_runs_full_ci(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.email", "ci@example.test")
    git("config", "user.name", "CI Test")
    module = tmp_path / "backend.py"
    module.write_text("def example():\n    return True\n")
    git("add", ".")
    git("commit", "-qm", "Backend")
    base = git("rev-parse", "HEAD")
    (tmp_path / "docs").mkdir()
    git("mv", "backend.py", "docs/backend.md")
    git("commit", "-qm", "Rename backend as documentation")
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    script = Path(__file__).resolve().parents[1] / "scripts/pr_ci_scope.py"
    subprocess.run([
        sys.executable, str(script), "--base-sha", base, "--head-sha", git("rev-parse", "HEAD"),
    ], cwd=tmp_path, check=True)
    assert output.read_text() == "scope=full\n"
