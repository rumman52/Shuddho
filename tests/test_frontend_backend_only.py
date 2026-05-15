from pathlib import Path


def test_frontend_uses_backend_only_calls() -> None:
    app_source = Path("apps/web-editor/src/App.tsx").read_text(encoding="utf-8")
    api_source = Path("apps/web-editor/src/lib/api.ts").read_text(encoding="utf-8")
    extension_source = Path("apps/chrome-extension/src/analyzer.ts").read_text(encoding="utf-8")
    popup_source = Path("apps/chrome-extension/src/popup.ts").read_text(encoding="utf-8")
    combined_source = f"{app_source}\n{api_source}\n{extension_source}\n{popup_source}"

    banned_fragments = [
        "api/v1/chat/completions",
        'Authorization": "Bearer',
        "requests.post(",
    ]

    for fragment in banned_fragments:
        assert fragment not in combined_source

    assert '"/analyze"' in api_source
    assert '"/api/events"' in api_source
    assert '"/health/deep"' in api_source


def test_frontend_status_copy_disables_fake_browser_suggestions_by_default() -> None:
    app_source = Path("apps/web-editor/src/App.tsx").read_text(encoding="utf-8")
    runtime_status_source = Path("apps/web-editor/src/lib/runtimeStatus.ts").read_text(encoding="utf-8")
    api_source = Path("apps/web-editor/src/lib/api.ts").read_text(encoding="utf-8")
    web_env_example = Path("apps/web-editor/.env.example").read_text(encoding="utf-8")

    assert "Backend is not connected. Contextual Bengali correction is disabled." in app_source
    assert "frontend_local_fallback_enabled" in app_source
    assert "apiConfiguration.localFallbackEnabled" in app_source
    assert "createUnavailableAnalysis" in app_source
    assert "No high-confidence correction found." in app_source
    assert "Backend offline, suggestions disabled" in runtime_status_source
    assert "Dev-only browser fallback" in runtime_status_source
    assert "localFallbackEnabled" in api_source
    assert "VITE_ENABLE_LOCAL_FALLBACK" in api_source
    assert "VITE_ENABLE_LOCAL_FALLBACK=false" in web_env_example


def test_extension_and_popup_runtime_copy_remains_backend_truthful() -> None:
    popup_source = Path("apps/chrome-extension/src/popup.ts").read_text(encoding="utf-8")

    assert "Backend live" in popup_source
    assert "detector unavailable" in popup_source
    assert "corrector unavailable" in popup_source
    assert "smart analysis paused" in popup_source
