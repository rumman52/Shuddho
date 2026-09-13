"""Regression coverage across the editor API, provider adapter, and persistence."""
import importlib
import json
from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient

from services.api.shuddho_api.llm_deepseek import run_deepseek_check
from services.feedback.shuddho_feedback.store import FeedbackStore
from shared.schemas.python_models import AnalyzeMode, AnalyzeResponse

runtime = importlib.import_module("services.api.shuddho_api.app")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "feedback_store", FeedbackStore(tmp_path / "feedback.db"))
    for name in ("llm_provider_cache", "llm_failures", "llm_circuit_until", "llm_provider_state"):
        monkeypatch.setattr(runtime, name, {})
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "false")
    with TestClient(runtime.app) as api:
        yield api


@pytest.mark.parametrize("camel_case", [True, False])
def test_check_preserves_editor_context(client, monkeypatch, camel_case):
    seen = []

    def analyze(request):
        seen.append(request)
        return AnalyzeResponse(text=request.text, normalized_text=request.text,
                               corrected_text=request.text, suggestions=[])

    monkeypatch.setattr(runtime, "analyze", analyze)
    payload = {
        "text": "আমার Shuddho", "revision": 7, "writingMode": "formal",
        "documentId" if camel_case else "document_id": "document-a",
        "userId" if camel_case else "user_id": "profile-a",
        "personalDictionary" if camel_case else "personal_dictionary": ["Shuddho"],
        "options": {"includeLLM": False, "mode": "fast"},
    }
    response = client.post("/api/check", json=payload)
    assert response.status_code == 200
    assert response.json()["documentId"] == "document-a"
    assert response.json()["revision"] == 7
    assert seen[0].user_id == "profile-a"
    assert seen[0].personal_dictionary == ["Shuddho"]
    assert seen[0].mode == AnalyzeMode.FORMAL


def test_editor_preferences_survive_reopen_without_profile_collisions(client, monkeypatch):
    for profile, word in (("profile-a", "Shuddho"), ("profile-b", "AI Fixers")):
        response = client.put(f"/api/preferences?user_id={profile}", json={
            "user_id": "ignored-body-id", "personal_dictionary": [word],
        })
        assert response.status_code == 200
        assert response.json()["user_id"] == profile
    monkeypatch.setattr(runtime, "feedback_store", FeedbackStore(runtime.feedback_store.database_path))
    assert client.get("/api/preferences?user_id=profile-a").json()["personal_dictionary"] == ["Shuddho"]
    assert client.get("/api/preferences?user_id=profile-b").json()["personal_dictionary"] == ["AI Fixers"]
    assert client.get("/api/preferences?user_id=profile-c").json()["personal_dictionary"] == []
    assert client.get("/api/preferences").status_code == 422
    assert client.put("/api/preferences", json={}).status_code == 422


def test_unknown_legacy_mode_does_not_crash_normalization(client):
    response = client.post("/api/check", json={
        "text": "Hello.", "mode": {"unexpected": True}, "options": {"includeLLM": False},
    })
    assert response.status_code == 200


def test_feedback_uses_the_editor_route_and_preserves_legacy_route(client):
    payload = {"suggestion_id": "s1", "action": "accepted", "text": "She go home.",
               "replacement": "goes", "user_id": "profile-a"}
    for path in ("/api/feedback", "/feedback"):
        response = client.post(path, json=payload)
        assert response.status_code == 200
        assert response.json()["id"] is not None
        assert response.json()["replacement"] == "goes"


def configure_deepseek(monkeypatch, handler):
    monkeypatch.setenv("SHUDDHO_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("SHUDDHO_ENABLE_LLM", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    monkeypatch.setattr(runtime, "run_deepseek_check", partial(
        run_deepseek_check, transport=httpx.MockTransport(handler),
    ))


def test_deepseek_review_flows_through_canonical_api_with_safe_preview(client, monkeypatch):
    calls = []

    def handle(request):
        body = json.loads(request.content)
        user = json.loads(body["messages"][1]["content"])
        calls.append(user)
        review = {
            "requestId": user["requestId"], "correctedText": "She goes abroad without permission.",
            "documentAssessment": {"summary": "Verb agreement", "overallQuality": "good", "language": "en"},
            "suggestions": [{"id": "edit1", "sentenceId": "s_0", "original": "go", "replacement": "goes",
                             "issueType": "grammar", "severity": "medium", "explanation": "Subject agreement.",
                             "confidence": 0.95, "start": 4, "end": 6}],
        }
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(review)}}]})

    configure_deepseek(monkeypatch, handle)
    response = client.post("/api/check", json={"text": "She go home.", "language": "en",
                           "options": {"includeLLM": True, "asyncLLM": False}})
    assert response.status_code == 200
    body = response.json()
    assert len(calls) == 1
    assert body["llm_provider"] == "deepseek"
    assert body["llm_status"] == "completed"
    assert body["llm_response_mode"] == "json_object"
    assert body["ai_valid_suggestion_count"] == 1
    assert body["correctedText"] == "She goes home."
    assert body["suggestions"][0]["suggestedText"] == "goes"
    assert "test-only-placeholder" not in response.text


def test_provider_failure_is_visible_and_local_writing_still_works(client, monkeypatch):
    configure_deepseek(monkeypatch, lambda _: httpx.Response(429))
    response = client.post("/api/check", json={"text": "আমি  আমি ভাত খাই।",
                           "options": {"includeLLM": True, "asyncLLM": False}})
    assert response.status_code == 200
    body = response.json()
    assert body["llm_status"] == "rate_limited"
    assert body["llm_attempted"] is True
    assert body["llm_used"] is False
    assert body["local_suggestion_count"] > 0
    assert body["suggestions"]
    assert "deepseek_http_429" in body["warnings"]


def test_diagnostics_match_deepseek_without_calling_the_provider(client, monkeypatch):
    def never_call(_):
        raise AssertionError("Diagnostics must not spend tokens")

    configure_deepseek(monkeypatch, never_call)
    monkeypatch.setenv("SHUDDHO_GEMMA_RESPONSE_MODE", "json_mime")
    response = client.get("/api/llm/debug")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deepseek"
    assert body["response_mode"] == "json_object"
    assert body["thinking_level"] == "disabled"
    assert body["endpoint"] == "https://api.deepseek.com/chat/completions"
    assert "test-only-placeholder" not in response.text
    assert "gemma_json_mime" not in response.text


def test_rejected_edits_cannot_enter_corrected_preview():
    result = runtime._classify_ai_result_after_validation("Pay 50 today.", {
        "status": "completed", "provider": "deepseek", "model": "deepseek-flash",
        "correctedText": "Pay 500 today.", "suggestions": [{
            "original": "50", "replacement": "500", "issueType": "grammar",
            "start": 4, "end": 6, "confidence": 0.95,
        }],
    })
    assert result["status"] == "completed_rejected"
    assert result["correctedText"] == "Pay 50 today."


def test_deletion_preview_keeps_unicode_offsets():
    result = runtime._classify_ai_result_after_validation("🙂 Hola  mundo.", {
        "status": "completed", "provider": "deepseek", "model": "deepseek-flash",
        "correctedText": "untrusted preview", "suggestions": [{
            "original": " ", "replacement": "", "issueType": "spacing",
            "start": 6, "end": 7, "confidence": 0.95,
        }],
    })
    assert result["status"] == "completed"
    assert result["correctedText"] == "🙂 Hola mundo."
