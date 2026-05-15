import importlib
import json
from pathlib import Path
import tomllib


def test_env_example_documents_local_runtime_and_origins() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "SHUDDHO_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173" in env_example
    assert "SHUDDHO_DETECTOR_ENABLED=auto" in env_example
    assert "SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base" in env_example
    assert "SHUDDHO_CORRECTOR_ENABLED=auto" in env_example
    assert "SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base" in env_example
    assert "The API reads only the repo-root .env file" in env_example
    assert "Do not leave a deployed frontend pointing at localhost." in env_example
    assert "api/v1/chat/completions" not in env_example


def test_frontend_source_omits_direct_hosted_model_calls() -> None:
    files_to_scan = [
        Path("apps/web-editor/src/App.tsx"),
        Path("apps/web-editor/src/lib/api.ts"),
        Path("apps/chrome-extension/src/analyzer.ts"),
        Path("apps/chrome-extension/src/popup.ts"),
        Path("apps/chrome-extension/src/content.ts"),
        Path("apps/chrome-extension/src/overlay.ts"),
    ]

    banned_fragments = [
        "api/v1/chat/completions",
        "Authorization\": \"Bearer",
    ]

    for path in files_to_scan:
        content = path.read_text(encoding="utf-8")
        for fragment in banned_fragments:
            assert fragment not in content, f"unexpected hosted-model reference in {path}"


def test_windows_backend_script_uses_repo_root_before_starting_uvicorn() -> None:
    script = Path("run_backend_windows.bat").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in script
    assert "Python 3.11 is the recommended Windows happy path" in script
    assert "repo-root .env was not found" in script
    assert "detector or corrector config" in script
    assert "-m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload" in script


def test_pyproject_includes_ml_packages_and_windows_friendly_torch_strategy() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.11,<3.15"
    dependencies = pyproject["project"]["dependencies"]
    assert "torch>=2.5.1,<3.0.0; sys_platform == 'win32'" in dependencies
    assert "torch>=2.4.0,<3.0.0; sys_platform != 'win32'" in dependencies

    package_find = pyproject["tool"]["setuptools"]["packages"]["find"]
    assert "ml*" in package_find["include"]
    assert "ml*" not in package_find["exclude"]


def test_ml_modules_used_by_backend_startup_are_importable() -> None:
    assert importlib.import_module("ml.detector.runtime").__name__ == "ml.detector.runtime"
    assert importlib.import_module("ml.ranking.pipeline").__name__ == "ml.ranking.pipeline"
    assert importlib.import_module("ml.corrector.model").__name__ == "ml.corrector.model"


def test_root_workspace_includes_gateway_web_and_packages() -> None:
    root_package = json.loads(Path("package.json").read_text(encoding="utf-8"))

    assert root_package["workspaces"] == [
        "apps/web",
        "apps/api",
        "apps/web-editor",
        "apps/chrome-extension",
        "packages/*",
    ]
    assert "dev:python-api" in root_package["scripts"]
    assert "build:agent" not in root_package["scripts"]
    assert "start:agent" not in root_package["scripts"]
