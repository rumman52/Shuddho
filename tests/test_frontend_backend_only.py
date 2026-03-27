from pathlib import Path


def test_frontend_uses_backend_only_calls() -> None:
    app_source = Path("apps/web-editor/src/App.tsx").read_text(encoding="utf-8")
    api_source = Path("apps/web-editor/src/lib/api.ts").read_text(encoding="utf-8")
    combined_source = f"{app_source}\n{api_source}"

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
