import json

import httpx

from services.api.shuddho_api.llm_provider import resolve_llm_config
from services.api.shuddho_api.llm_openrouter import run_openrouter_check
from services.api.shuddho_api.llm_openai import run_openai_check
from services.api.shuddho_api.suggestion_merge import merge_suggestions, validate_ai_suggestions


def test_provider_config_selects_openrouter_key() -> None:
    cfg = resolve_llm_config({"SHUDDHO_ENABLE_LLM": "true", "SHUDDHO_LLM_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "fake-openrouter-key", "OPENROUTER_MODEL": "openai/gpt-oss-120b:free"})
    assert cfg.enabled is True
    assert cfg.configured is True
    assert cfg.provider == "openrouter"
    assert cfg.model == "openai/gpt-oss-120b:free"


def test_provider_config_missing_keys_are_provider_specific() -> None:
    assert "openrouter_api_key_missing" in resolve_llm_config({"SHUDDHO_ENABLE_LLM": "true", "SHUDDHO_LLM_PROVIDER": "openrouter"}).warnings
    assert "openai_api_key_missing" in resolve_llm_config({"SHUDDHO_ENABLE_LLM": "true", "SHUDDHO_LLM_PROVIDER": "openai"}).warnings


def test_provider_config_rejects_openrouter_model_on_openai() -> None:
    cfg = resolve_llm_config({"SHUDDHO_ENABLE_LLM": "true", "SHUDDHO_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk", "OPENAI_MODEL": "openai/gpt-oss-120b:free"})
    assert cfg.configured is False
    assert cfg.status == "unsupported_provider"
    assert "openai_model_id_suspicious_use_openrouter_provider" in cfg.warnings


def test_provider_disabled() -> None:
    cfg = resolve_llm_config({"SHUDDHO_LLM_PROVIDER": "disabled"})
    assert cfg.status == "disabled"
    assert cfg.enabled is False


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
    def json(self):
        return self._payload


class FakeClient:
    calls = []
    responses = []
    def __init__(self, timeout):
        self.timeout = timeout
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def post(self, url, headers=None, json=None):
        self.calls.append(json)
        next_response = self.responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response


def test_openrouter_parses_choices_content_json(monkeypatch) -> None:
    FakeClient.calls = []
    FakeClient.responses = [FakeResponse(200, {"choices": [{"message": {"content": json.dumps({"requestId":"r1","correctedText":"আমি ভাত খাই।","documentAssessment":{"summary":"ok","overallQuality":"good","language":"bn"},"suggestions":[]})}}]})]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
    assert result["called"] is True
    assert result["parsed"] is True
    assert result["status"] == "completed_empty"


def test_openrouter_structured_output_fallback(monkeypatch) -> None:
    FakeClient.calls = []
    FakeClient.responses = [FakeResponse(400, {}), FakeResponse(200, {"choices": [{"message": {"content": "```json\n" + json.dumps({"requestId":"r1","correctedText":"আমি ভাত খাই।","documentAssessment":{"summary":"ok","overallQuality":"good","language":"bn"},"suggestions":[]}) + "\n```"}}]})]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
    assert result["status"] == "completed_empty"
    assert result["response_mode"] == "strict_json_prompt"
    assert "openrouter_structured_output_fallback_used" in result["warnings"]


def test_openrouter_timeout(monkeypatch) -> None:
    FakeClient.calls = []
    FakeClient.responses = [httpx.TimeoutException("slow provider")]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1", timeout_seconds=0.01)
    assert result["status"] == "timeout"
    assert "openrouter_timeout" in result["warnings"]


def test_openrouter_max_completion_tokens_fallback(monkeypatch) -> None:
    FakeClient.calls = []
    payload = {"requestId":"r1","correctedText":"আমি ভাত খাই।","documentAssessment":{"summary":"ok","overallQuality":"good","language":"bn"},"suggestions":[]}
    FakeClient.responses = [
        FakeResponse(400, {"error": {"message": "max_completion_tokens is not supported; use max_tokens"}}),
        FakeResponse(200, {"choices": [{"message": {"content": json.dumps(payload)}}]}),
    ]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
    assert result["status"] == "completed_empty"
    assert "openrouter_max_tokens_fallback_used" in result["warnings"]
    assert "max_tokens" in FakeClient.calls[-1]
    assert "max_completion_tokens" not in FakeClient.calls[-1]


def test_openai_parses_output_blocks(monkeypatch) -> None:
    payload = {"requestId":"r1","correctedText":"I eat rice.","documentAssessment":{"summary":"ok","overallQuality":"good","language":"en"},"suggestions":[]}
    FakeClient.calls = []
    FakeClient.responses = [FakeResponse(200, {"output": [{"content": [{"text": json.dumps(payload)}]}]})]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = run_openai_check("I eat rice.", "gpt-4o-mini", "key", request_id="r1")
    assert result["called"] is True
    assert result["status"] == "completed_empty"


def test_ai_validation_rejects_bad_spans_and_identical() -> None:
    valid, warnings = validate_ai_suggestions("আমি ভাত খাই।", [
        {"id":"a","sentenceId":"s_0","original":"নেই","replacement":"আছে","confidence":0.8},
        {"id":"b","sentenceId":"s_0","original":"ভাত","replacement":"ভাত","confidence":0.8},
    ])
    assert valid == []
    assert "ai_suggestion_original_not_found" in warnings
    assert "ai_suggestion_identical_replacement" in warnings


def test_merge_dedupes_and_keeps_provider() -> None:
    text = "আমি ভাত খাই।"
    local = [{"id":"l1","ruleId":"local.grammar","type":"grammar","severity":"low","originalText":"খাই","suggestedText":"খাই।","replacementOptions":["খাই।"],"explanationBn":"local","span":{"startIndex":8,"endIndex":11},"confidence":0.6,"source":"rule","provider":"local"}]
    ai = [{"id":"a1","original":"খাই","replacement":"খাই।","issueType":"grammar","severity":"medium","explanation":"better","confidence":0.9,"span_start":8,"span_end":11}]
    merged, warnings = merge_suggestions(text, local, ai, "openai", "gpt-4o-mini")
    assert warnings == []
    assert len(merged) == 1
    assert merged[0]["source"] == "hybrid"
    assert merged[0]["provider"] == "openai"
    assert merged[0]["metadata"]["mergeStatus"] == "merged"


def test_openrouter_http_status_mapping(monkeypatch) -> None:
    expected = {
        401: "auth_or_forbidden",
        403: "auth_or_forbidden",
        402: "credits_or_payment_required",
        404: "model_not_found",
        429: "rate_limited",
        503: "provider_error",
    }
    monkeypatch.setattr(httpx, "Client", FakeClient)
    for status_code, expected_status in expected.items():
        FakeClient.calls = []
        # One retry is allowed for 429/503, so provide two responses.
        FakeClient.responses = [FakeResponse(status_code, {"error": {"code": "x"}}), FakeResponse(status_code, {"error": {"code": "x"}})] if status_code in {429, 503} else [FakeResponse(status_code, {"error": {"code": "x"}})]
        result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
        assert result["status"] == expected_status
        assert result["http_status"] == status_code


def test_openrouter_invalid_json_and_schema(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "Client", FakeClient)
    FakeClient.calls = []
    FakeClient.responses = [FakeResponse(200, {"choices": [{"message": {"content": "not json"}}]})]
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
    assert result["status"] == "invalid_json"

    FakeClient.calls = []
    FakeClient.responses = [FakeResponse(200, {"choices": [{"message": {"content": json.dumps({"suggestions": {}})}}]})]
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
    assert result["status"] == "invalid_schema"


def test_openrouter_valid_ai_suggestion_completed(monkeypatch) -> None:
    payload = {
        "requestId":"r1",
        "correctedText":"আমি ভাত খাই।",
        "documentAssessment":{"summary":"ok","overallQuality":"good","language":"bn"},
        "suggestions":[{"id":"a1","sentenceId":"s_0","original":"খাই","replacement":"খাই।","issueType":"punctuation","severity":"medium","explanation":"punctuation","confidence":0.9,"source":"ai","start":8,"end":11}],
    }
    FakeClient.calls = []
    FakeClient.responses = [FakeResponse(200, {"choices": [{"message": {"content": json.dumps(payload)}}]})]
    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = run_openrouter_check("আমি ভাত খাই।", "openai/gpt-oss-120b:free", "key", request_id="r1")
    assert result["status"] == "completed"
    assert len(result["suggestions"]) == 1

def test_ai_validation_resolves_missing_and_incorrect_spans() -> None:
    text = "আমি ভাত খাই। তুমি পানি খাই।"
    valid, warnings = validate_ai_suggestions(text, [
        {"id": "missing-span", "sentenceId": "s_0", "originalText": "ভাত", "replacementText": "ভাতটা", "type": "clarity", "confidence": 0.9},
        {"id": "wrong-span", "sentenceId": "s_1", "original": "খাই", "suggestedText": "খাও", "issueType": "grammar", "confidence": 0.9, "start": 999, "end": 1002},
    ])
    assert warnings == []
    assert [(item["span_start"], item["span_end"]) for item in valid] == [(4, 7), (23, 26)]
    assert valid[0]["replacement"] == "ভাতটা"


def test_merge_canonicalizes_ai_source_as_model() -> None:
    merged, warnings = merge_suggestions(
        "আমি ভাত খাই।",
        [],
        [{"id": "a1", "original": "ভাত", "replacement": "ভাতটা", "issueType": "clarity", "severity": "low", "explanation": "আরও নির্দিষ্ট", "confidence": 0.9, "span_start": 4, "span_end": 7}],
        "openrouter",
        "openai/gpt-oss-120b:free",
    )
    assert warnings == []
    assert merged[0]["source"] == "model"
