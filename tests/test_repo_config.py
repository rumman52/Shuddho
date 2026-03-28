from pathlib import Path


def test_env_example_documents_openrouter_and_local_origins() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "OPENROUTER_API_KEY=your_key_here" in env_example
    assert "OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b" in env_example
    assert "OPENROUTER_TIMEOUT_SECONDS=20" in env_example
    assert "SHUDDHO_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173" in env_example
    assert "sk-or-v1-" not in env_example


def test_frontend_source_omits_direct_openrouter_calls() -> None:
    files_to_scan = [
        Path("apps/web-editor/src/App.tsx"),
        Path("apps/web-editor/src/lib/api.ts"),
    ]

    banned_fragments = [
        "openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        "Authorization\": \"Bearer",
    ]

    for path in files_to_scan:
        content = path.read_text(encoding="utf-8")
        for fragment in banned_fragments:
            assert fragment not in content, f"unexpected OpenRouter reference in {path}"


def test_windows_backend_script_uses_repo_root_before_starting_uvicorn() -> None:
    script = Path("run_backend_windows.bat").read_text(encoding="utf-8")

    assert 'cd /d "%~dp0"' in script
    assert "py -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000 --reload" in script
