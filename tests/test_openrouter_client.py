from services.llm.shuddho_llm.openrouter_client import DEFAULT_OPENROUTER_MODEL, OpenRouterClient
from services.llm.shuddho_llm.parsing import OpenRouterIssueCategory, parse_openrouter_response


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return FakeResponse(self.payload, status_code=self.status_code)


def test_openrouter_client_missing_key_falls_back_without_crashing() -> None:
    client = OpenRouterClient.from_environment({})

    assert client.has_api_key() is False
    assert client.is_configured() is False
    assert client.is_available() is False
    assert client.model_name == DEFAULT_OPENROUTER_MODEL
    assert client.analyze_sentence("\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964", "standard") == []


def test_openrouter_client_placeholder_key_stays_disabled() -> None:
    client = OpenRouterClient.from_environment({"OPENROUTER_API_KEY": "your_key_here"})

    assert client.has_api_key() is True
    assert client.is_configured() is False
    assert client.is_available() is False
    assert client.model_name == DEFAULT_OPENROUTER_MODEL


def test_parse_openrouter_response_discards_malformed_payload_safely() -> None:
    assert parse_openrouter_response("not-json", sentence="\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964") == []


def test_openrouter_client_ignores_malformed_response_text() -> None:
    client = OpenRouterClient(
        session=FakeSession(
            {
                "choices": [
                    {
                        "message": {
                            "content": "```json\nnot valid\n```",
                        }
                    }
                ]
            }
        ),
        api_key="test-key",
        model_name="openrouter-test",
        timeout_seconds=20,
        enabled=True,
    )

    assert client.analyze_sentence("\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964", "standard") == []


def test_parse_openrouter_response_accepts_valid_json_issues() -> None:
    issues = parse_openrouter_response(
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
    assert issues[0].category == OpenRouterIssueCategory.SPELLING_ERROR
