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


def test_vercel_config_deploys_web_editor_spa_from_repo_root() -> None:
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))

    assert config["version"] == 2
    assert config["installCommand"] == "npm install"
    assert config["buildCommand"] == "npm run build:web-editor"
    assert config["outputDirectory"] == "apps/web-editor/dist"
    assert config["rewrites"] == [
        {
            "source": "/backend/:path*",
            "destination": "https://shuddho-api.onrender.com/:path*",
        },
        {"source": "/(.*)", "destination": "/index.html"},
    ]

def test_windows_backend_script_uses_repo_root_before_starting_uvicorn() -> None:
    script = Path("run_backend_windows.bat").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in script
    assert "Python 3.11 is the recommended Windows happy path" in script
    assert "repo-root .env was not found" in script
    assert "detector or corrector config" in script
    assert "-m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload" in script


def test_pyproject_keeps_hosted_runtime_lightweight_and_ml_optional() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.11,<3.15"
    dependencies = pyproject["project"]["dependencies"]
    optional_ml = pyproject["project"]["optional-dependencies"]["ml"]
    assert any(item.startswith("google-genai") for item in dependencies)
    assert not any(item.lower().startswith(("torch", "sentencepiece", "transformers")) for item in dependencies)
    assert any(item.startswith("torch") for item in optional_ml)
    assert any(item.startswith("sentencepiece") for item in optional_ml)

    package_find = pyproject["tool"]["setuptools"]["packages"]["find"]
    assert "ml*" in package_find["include"]
    assert "ml*" not in package_find["exclude"]


def test_default_docker_target_is_lightweight_production() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    stages = [line.strip() for line in dockerfile.splitlines() if line.strip().upper().startswith("FROM ")]
    assert any(line.endswith(" AS ml-cpu") for line in stages)
    assert stages[-1].endswith(" AS production")
    production_tail = dockerfile.rsplit("FROM lightweight AS production", 1)[1]
    assert "torch" not in production_tail.lower()


def test_render_docs_use_lightweight_native_install() -> None:
    for filename in ("DEPLOYMENT.md", "DEPLOYMENT-QUICK-FIX.md", "docs/DEPLOYMENT.md", "docs/deployment-render-vercel.md"):
        content = Path(filename).read_text(encoding="utf-8")
        assert "python -m pip install --upgrade pip && python -m pip install --no-cache-dir ." in content
        assert "uv sync --frozen || uv sync" not in content


def test_disabled_corrector_skips_optional_model_download(monkeypatch) -> None:
    from services.analysis.shuddho_analysis.corrector_service import CorrectorService

    monkeypatch.setattr(
        CorrectorService,
        "_download_optional_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("disabled corrector attempted download")),
    )
    service = CorrectorService.from_environment(
        {"SHUDDHO_CORRECTOR_ENABLED": "false", "SHUDDHO_CORRECTOR_MODEL_URL": "https://invalid.example/model"}
    )
    assert service.runtime_status().status == "disabled"


def test_optional_ml_source_remains_available_without_being_a_base_requirement() -> None:
    for path in ("ml/detector/runtime.py", "ml/ranking/pipeline.py", "ml/corrector/model.py"):
        assert Path(path).is_file()


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
