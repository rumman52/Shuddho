import json
import sys
import types

import pytest

from services.api.shuddho_api.ai_review_schema import extract_json_payload
from services.api.shuddho_api.llm_gemma import run_gemma_check
from services.api.shuddho_api.llm_provider import DEFAULT_GEMMA_MODEL, resolve_llm_config


def test_gemma_selected_by_default_and_default_model() -> None:
    cfg = resolve_llm_config({"GOOGLE_API_KEY": "test-key"})
    assert cfg.provider == "gemma"
    assert cfg.model == DEFAULT_GEMMA_MODEL == "gemma-4-26b-a4b-it"
    assert cfg.configured is True


def test_custom_gemma_model_works() -> None:
    cfg = resolve_llm_config({"GOOGLE_API_KEY": "test-key", "GEMMA_MODEL": "gemma-custom-it"})
    assert cfg.configured is True
    assert cfg.model == "gemma-custom-it"


def test_missing_google_api_key_is_clear() -> None:
    cfg = resolve_llm_config({"SHUDDHO_ENABLE_LLM": "true"})
    assert cfg.status == "missing_key"
    assert "google_api_key_missing" in cfg.warnings


@pytest.mark.parametrize("provider", ["openrouter", "openai", "qwen", "gemini"])
def test_other_generative_providers_are_rejected(provider: str) -> None:
    cfg = resolve_llm_config({"SHUDDHO_ENABLE_LLM": "true", "SHUDDHO_LLM_PROVIDER": provider, "GOOGLE_API_KEY": "test-key"})
    assert cfg.configured is False
    assert cfg.status == "unsupported_provider"
    assert "unsupported_llm_provider_gemma_only" in cfg.warnings


def test_gemini_model_is_rejected() -> None:
    cfg = resolve_llm_config({"GOOGLE_API_KEY": "test-key", "GEMMA_MODEL": "gemini-2.5-flash"})
    assert cfg.configured is False
    assert cfg.status == "unsupported_provider"
    assert "unsupported_model_gemma_only" in cfg.warnings


def _install_fake_sdk(monkeypatch, response=None, error=None):
    calls = []
    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            if error is not None:
                raise error
            return response
    class Client:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.models = Models()
    constructor = lambda **kw: types.SimpleNamespace(**kw)
    types_mod = types.SimpleNamespace(
        HttpOptions=constructor, HttpRetryOptions=constructor,
        GenerateContentConfig=constructor, ThinkingConfig=constructor,
        Tool=constructor, ToolConfig=constructor, FunctionCallingConfig=constructor,
    )
    # Match the official SDK module contract used by production:
    # ``from google import genai`` and ``from google.genai import types``.
    genai = types.SimpleNamespace(Client=Client, types=types_mod)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)
    return calls


def test_existing_json_parsing_and_official_sdk_call(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_GEMMA_RESPONSE_MODE", "json_mime")
    payload = {"requestId": "r1", "correctedText": "আমি ভাত খাই।", "documentAssessment": {"summary": "ঠিক", "overallQuality": "good", "language": "bn"}, "suggestions": []}
    response = types.SimpleNamespace(text=json.dumps(payload, ensure_ascii=False), usage_metadata=None)
    calls = _install_fake_sdk(monkeypatch, response=response)
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == "completed_empty"
    assert result["parsed"] is True
    assert calls[0]["model"] == DEFAULT_GEMMA_MODEL
    assert "contents" in calls[0]


def test_function_call_is_preferred_and_validated(monkeypatch) -> None:
    payload = {"requestId": "r1", "correctedText": "আমি ভাত খাই।", "documentAssessment": {"summary": "ঠিক", "overallQuality": "good", "language": "bn"}, "suggestions": []}
    response = types.SimpleNamespace(function_calls=[types.SimpleNamespace(name="submit_shuddho_review", args=payload)], candidates=[], usage_metadata={"prompt_token_count": 10, "candidates_token_count": 5, "total_token_count": 15})
    calls = _install_fake_sdk(monkeypatch, response=response)
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == "completed_empty"
    assert result["response_mode"] == "function_call"
    assert result["usage"]["output_tokens"] == 5
    assert calls[0]["config"].tool_config.function_calling_config.mode == "ANY"


@pytest.mark.parametrize("wrapped", [
    '```json\n{"requestId":"r"}\n```',
    'Here is the result: {"requestId":"r"} thanks.',
    '"{\\"requestId\\":\\"r\\"}"',
    'prefix {"requestId":"r","correctedText":"বাংলা {ভাষা} \\\"ভালো\\\""} trailing {"ignored":true}',
])
def test_deterministic_json_compatibility_extraction(wrapped) -> None:
    assert extract_json_payload(wrapped)["requestId"] == "r"


def test_truncation_is_not_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("SHUDDHO_GEMMA_RESPONSE_MODE", "json_mime")
    response = types.SimpleNamespace(text='{"requestId":', candidates=[types.SimpleNamespace(finish_reason="MAX_TOKENS")], usage_metadata={"candidates_token_count": 9})
    _install_fake_sdk(monkeypatch, response=response)
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == "truncated"
    assert result["usage"]["output_tokens"] == 9
    assert "provider output" not in str(result).lower()


def test_gemma_api_failure_returns_existing_error_shape(monkeypatch) -> None:
    error = Exception("service unavailable")
    error.status_code = 503
    _install_fake_sdk(monkeypatch, error=error)
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == "provider_error"
    assert result["called"] is True
    assert result["provider"] == "gemma"
    assert result["suggestions"] == []
    assert "gemma_provider_or_server_error" in result["warnings"]


def test_direct_provider_rejects_non_gemma_model_before_api_call() -> None:
    result = run_gemma_check("আমি ভাত খাই।", "gemini-2.5-flash", "test-key")
    assert result["status"] == "unsupported_provider"
    assert result["called"] is False


def test_no_generative_fallback_is_configured() -> None:
    cfg = resolve_llm_config({"GOOGLE_API_KEY": "test-key", "SHUDDHO_LLM_FALLBACK_PROVIDER": "openai"})
    assert cfg.fallback_provider is None
    assert cfg.fallback_configured is False
