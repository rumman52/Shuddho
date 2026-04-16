from pathlib import Path


def test_frontend_uses_backend_only_calls() -> None:
    app_source = Path("apps/web-editor/src/App.tsx").read_text(encoding="utf-8")
    api_source = Path("apps/web-editor/src/lib/api.ts").read_text(encoding="utf-8")
    extension_source = Path("apps/chrome-extension/src/analyzer.ts").read_text(encoding="utf-8")
    popup_source = Path("apps/chrome-extension/src/popup.ts").read_text(encoding="utf-8")
    combined_source = f"{app_source}\n{api_source}\n{extension_source}\n{popup_source}"

    banned_fragments = [
        "OPENROUTER_API_KEY",
        "openrouter.ai/api/v1/chat/completions",
        "Authorization\": \"Bearer",
        "requests.post(",
    ]

    for fragment in banned_fragments:
        assert fragment not in combined_source

    assert '"/analyze"' in api_source
    assert '"/feedback"' in api_source


def test_frontend_status_copy_makes_backend_vs_fallback_honest() -> None:
    app_source = Path("apps/web-editor/src/App.tsx").read_text(encoding="utf-8")
    popup_source = Path("apps/chrome-extension/src/popup.ts").read_text(encoding="utf-8")

    assert "Backend live" in app_source
    assert "Backend unreachable — local fallback only" in app_source
    assert "Backend live but detector disabled" in app_source
    assert "Backend live but OpenRouter unavailable" in app_source
    assert "Local fallback checks" in app_source
    assert "contextual backend corrections are turned off" in app_source
    assert "Backend live but detector disabled" in popup_source
    assert "Backend live but OpenRouter unavailable" in popup_source
    assert "Backend unreachable — smart analysis paused" in popup_source
