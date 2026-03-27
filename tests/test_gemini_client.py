from services.llm.shuddho_llm.client import DEFAULT_GEMINI_MODEL, GeminiClient
from services.llm.shuddho_llm.parsing import GeminiIssueCategory, parse_gemini_response


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate_content(self, **kwargs):  # type: ignore[no-untyped-def]
        return FakeResponse(self.text)


class FakeApiClient:
    def __init__(self, text: str) -> None:
        self.models = FakeModels(text)


def test_gemini_client_missing_key_falls_back_without_crashing() -> None:
    client = GeminiClient.from_environment({})

    assert client.is_available() is False
    assert client.model_name == DEFAULT_GEMINI_MODEL
    assert client.analyze_sentence("\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964", "standard") == []


def test_parse_gemini_response_discards_malformed_payload_safely() -> None:
    assert parse_gemini_response("not-json", sentence="\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964") == []


def test_gemini_client_ignores_malformed_response_text() -> None:
    client = GeminiClient(
        api_client=FakeApiClient("```json\nnot valid\n```"),
        model_name="gemini-test",
        timeout_seconds=20,
        enabled=True,
    )

    assert client.analyze_sentence("\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964", "standard") == []


def test_parse_gemini_response_accepts_valid_json_issues() -> None:
    issues = parse_gemini_response(
        """
        {
          "issues": [
            {
              "start": 0,
              "end": 5,
              "original": "\u0986\u09ae\u09b0\u09be\u09be",
              "replacement": "\u0986\u09ae\u09b0\u09be",
              "category": "spelling_error",
              "confidence": 0.96,
              "reason_bn": "\u098f\u0996\u09be\u09a8\u09c7 \u0985\u09a4\u09bf\u09b0\u09bf\u0995\u09cd\u09a4 \u0985\u0995\u09cd\u09b7\u09b0 \u0986\u099b\u09c7\u0964"
            }
          ]
        }
        """,
        sentence="\u0986\u09ae\u09b0\u09be\u09be \u0986\u09b8\u09bf\u0964",
    )

    assert len(issues) == 1
    assert issues[0].category == GeminiIssueCategory.SPELLING_ERROR
