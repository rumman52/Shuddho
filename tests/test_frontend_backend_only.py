from pathlib import Path


def test_frontend_does_not_reference_gemini_sdk_or_api_keys() -> None:
    app_source = Path("apps/web-editor/src/App.tsx").read_text(encoding="utf-8")
    api_source = Path("apps/web-editor/src/lib/api.ts").read_text(encoding="utf-8")

    combined_source = f"{app_source}\n{api_source}"

    assert "GEMINI_API_KEY" not in combined_source
    assert "google.genai" not in combined_source
    assert "aistudio.google.com" not in combined_source
    assert "generativelanguage.googleapis.com" not in combined_source
