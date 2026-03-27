from pathlib import Path


def test_env_example_uses_placeholders_only() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "AIza" not in env_example
    assert "GEMINI_API_KEY=your_key_here" in env_example
    assert "GEMINI_MODEL=gemini-3-flash-preview" in env_example
    assert "GEMINI_TIMEOUT_SECONDS=20" in env_example
    assert "SHUDDHO_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173" in env_example
