import asyncio
import gzip
import json

import httpx
import pytest

from services.api.shuddho_api.llm_deepseek import MAX_RESPONSE_BYTES, run_deepseek_check


def review_payload(text="She go home.", request_id="review-1"):
    return {
        "requestId": request_id, "correctedText": "She goes home.",
        "documentAssessment": {"summary": "Verb agreement", "overallQuality": "good", "language": "en"},
        "suggestions": [{
            "id": "s1", "sentenceId": "s_0", "original": "go", "replacement": "goes",
            "issueType": "grammar", "severity": "medium", "explanation": "Use goes with she.",
            "confidence": 0.95, "start": 4, "end": 6,
        }],
    }


def envelope(payload=None, finish_reason="stop"):
    return {
        "model": "deepseek-flash", "choices": [{
            "finish_reason": finish_reason,
            "message": {"content": json.dumps(payload if payload is not None else review_payload())},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "prompt_cache_hit_tokens": 10},
    }


def run(handler, **kwargs):
    return run_deepseek_check(
        text=kwargs.pop("text", "She go home."), request_id="review-1",
        api_key="test-only-placeholder", transport=httpx.MockTransport(handler), **kwargs,
    )


def test_review_uses_json_non_thinking_and_keeps_credentials_out_of_results():
    calls = []

    def handle(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-only-placeholder"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        assert "tools" not in payload
        assert 256 <= payload["max_tokens"] <= 8192
        assert json.loads(payload["messages"][1]["content"])["fullText"] == "She go home."
        return httpx.Response(200, json=envelope())

    result = run(handle)
    assert result["status"] == "completed"
    assert result["suggestions"][0]["replacement"] == "goes"
    assert result["usage"]["total_tokens"] == 150
    assert result["response_mode"] == "json_object"
    assert result["diagnostics"]["effective_model"] == "deepseek-flash"
    assert len(calls) == 1
    assert "test-only-placeholder" not in json.dumps(result)


def test_gzip_response_is_decoded_once():
    result = run(lambda _: httpx.Response(
        200, content=gzip.compress(json.dumps(envelope()).encode()), headers={"content-encoding": "gzip"},
    ))
    assert result["status"] == "completed"


@pytest.mark.parametrize("finish_reason", ["tool_calls", "unexpected", None])
def test_unexpected_completion_never_becomes_a_clean_review(finish_reason):
    result = run(lambda _: httpx.Response(200, json=envelope(finish_reason=finish_reason)))
    assert result["status"] == "invalid_schema"
    assert result["parsed"] is False


@pytest.mark.parametrize("code,status", [
    (401, "auth_or_forbidden"), (403, "auth_or_forbidden"),
    (402, "credits_or_payment_required"), (404, "model_not_found"),
    (429, "rate_limited"), (503, "provider_error"), (504, "timeout"),
])
def test_provider_errors_are_safe_and_do_not_retry_implicitly(code, status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(code, text="private echo test-only-placeholder", headers={"retry-after": "3"})

    result = run(handle)
    assert result["status"] == status
    assert result["http_status"] == code
    assert result["retry_after_seconds"] == 3
    assert len(calls) == 1
    assert "private echo" not in json.dumps(result)
    assert "test-only-placeholder" not in json.dumps(result)


@pytest.mark.parametrize("wire,status", [
    ("not-json", "invalid_json"),
    (json.dumps({"choices": []}), "invalid_schema"),
    (json.dumps(envelope(finish_reason="length")), "truncated"),
    (json.dumps(envelope(finish_reason="content_filter")), "content_filter"),
])
def test_invalid_and_truncated_results_do_not_become_clean_reviews(wire, status):
    result = run(lambda _: httpx.Response(200, text=wire))
    assert result["status"] == status
    assert result["suggestions"] == []
    assert result["correctedText"] is None


def test_malformed_suggestion_is_not_silently_dropped():
    payload = review_payload()
    payload["suggestions"][0]["confidence"] = 4
    result = run(lambda _: httpx.Response(200, json=envelope(payload)))
    assert result["status"] == "invalid_schema"
    assert result["ai_raw_suggestion_count"] == 1


def test_request_id_mismatch_is_rejected():
    result = run(lambda _: httpx.Response(200, json=envelope(review_payload(request_id="another-request"))))
    assert result["status"] == "invalid_schema"


def test_span_deletion_and_non_bangla_assessment_are_supported():
    payload = {
        "requestId": "review-1", "correctedText": "Hola!",
        "documentAssessment": {"summary": "Puntuación", "overallQuality": "good", "language": "es"},
        "suggestions": [{
            "id": "delete-1", "sentenceId": "s_0", "original": "!", "replacement": "",
            "issueType": "punctuation", "severity": "low", "explanation": "Elimina el signo repetido.",
            "confidence": 0.95, "start": 5, "end": 6,
        }],
    }
    result = run(lambda _: httpx.Response(200, json=envelope(payload)), text="Hola!!")
    assert result["status"] == "completed"
    assert result["suggestions"][0]["replacement"] == ""
    assert result["documentAssessment"]["language"] == "es"


class EndlessKeepAlive(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self):
        while True:
            await asyncio.sleep(0.005)
            yield b" "

    async def aclose(self):
        self.closed = True


def test_total_deadline_covers_keep_alive_body_and_closes_connection():
    stream = EndlessKeepAlive()
    result = run(lambda _: httpx.Response(200, stream=stream), timeout_seconds=0.03)
    assert result["status"] == "timeout"
    assert stream.closed


def test_oversized_response_is_bounded():
    result = run(lambda _: httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)))
    assert result["status"] == "invalid_schema"
    assert "deepseek_response_too_large" in result["warnings"]


def test_missing_key_never_calls_transport():
    def unexpected(_):
        pytest.fail("No HTTP request should be made without a key")

    result = run_deepseek_check("Hello", transport=httpx.MockTransport(unexpected))
    assert result["status"] == "missing_key"
    assert result["called"] is False
