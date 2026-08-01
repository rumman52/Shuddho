import json
import sys
import types

import pytest
from collections import UserDict

from services.api.shuddho_api.ai_review_schema import extract_json_payload
from services.api.shuddho_api.llm_gemma import run_gemma_check
from services.api.shuddho_api.llm_provider import DEFAULT_GEMMA_MODEL, resolve_llm_config
from services.api.shuddho_api.gemma_response_mode import resolve_gemma_response_mode


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
        FunctionDeclaration=constructor, AutomaticFunctionCallingConfig=constructor,
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
    monkeypatch.setenv("SHUDDHO_ALLOW_LEGACY_GEMMA_RESPONSE_MODE", "true")
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
    assert calls[0]["config"].automatic_function_calling.disable is True
    assert "Call submit_shuddho_review exactly once" in calls[0]["config"].system_instruction
    assert "Return only JSON" not in calls[0]["config"].system_instruction


class _FunctionOnlyResponse:
    candidates = []
    usage_metadata = None
    def __init__(self, payload):
        self.function_calls = [types.SimpleNamespace(name="submit_shuddho_review", args=payload)]
    @property
    def text(self):
        raise ValueError("function responses have no text")


def _canonical_payload():
    return {"requestId": "r1", "correctedText": "আমি ভাত খাই।", "documentAssessment": {"summary": "ঠিক", "overallQuality": "good", "language": "bn"}, "suggestions": []}


def test_function_call_never_reads_raising_text(monkeypatch) -> None:
    _install_fake_sdk(monkeypatch, response=_FunctionOnlyResponse(_canonical_payload()))
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == "completed_empty"
    assert result["diagnostics"]["function_call_count"] == 1


def test_candidate_part_mapping_arguments(monkeypatch) -> None:
    call = types.SimpleNamespace(name="submit_shuddho_review", args=UserDict(_canonical_payload()))
    part = types.SimpleNamespace(function_call=call)
    candidate = types.SimpleNamespace(content=types.SimpleNamespace(parts=[part]), finish_reason="STOP")
    response = types.SimpleNamespace(function_calls=[], candidates=[candidate], usage_metadata=None)
    _install_fake_sdk(monkeypatch, response=response)
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["parsed"] is True
    assert result["diagnostics"]["has_function_call"] is True


def test_wrong_and_missing_function_calls_are_schema_errors(monkeypatch) -> None:
    wrong = types.SimpleNamespace(function_calls=[types.SimpleNamespace(name="other", args={})], candidates=[], usage_metadata=None)
    _install_fake_sdk(monkeypatch, response=wrong)
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == "invalid_schema"
    assert result["warnings"][0] == "gemma_unexpected_function_call"


def test_stale_production_json_mode_is_overridden() -> None:
    mode = resolve_gemma_response_mode({"SHUDDHO_GEMMA_RESPONSE_MODE": "json_mime"})
    assert mode.requested == "json_mime"
    assert mode.effective == "function_call"
    assert "gemma_legacy_response_mode_overridden" in mode.warnings


@pytest.mark.parametrize((content, status, shape), [
    (json.dumps([_canonical_payload()], ensure_ascii=False), "completed_empty", "one_element_canonical_array"),
    ("42", "invalid_schema", "unsupported_top_level"),
    ("not-json", "invalid_json", None),
])
def test_legacy_json_classification(monkeypatch, content, status, shape) -> None:
    monkeypatch.setenv("SHUDDHO_GEMMA_RESPONSE_MODE", "json_mime")
    monkeypatch.setenv("SHUDDHO_ALLOW_LEGACY_GEMMA_RESPONSE_MODE", "true")
    _install_fake_sdk(monkeypatch, response=types.SimpleNamespace(text=content, candidates=[], usage_metadata=None))
    result = run_gemma_check("আমি ভাত খাই।", DEFAULT_GEMMA_MODEL, "test-key", request_id="r1")
    assert result["status"] == status
    if shape:
        assert result["diagnostics"]["payload_shape"] == shape


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
    monkeypatch.setenv("SHUDDHO_ALLOW_LEGACY_GEMMA_RESPONSE_MODE", "true")
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
