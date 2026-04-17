from services.llm.shuddho_llm.openrouter_client import DEFAULT_OPENROUTER_MODEL, OpenRouterClient
from services.llm.shuddho_llm.parsing import OpenRouterIssueCategory, parse_openrouter_response


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.calls: list[tuple[tuple, dict]] = []
        self.get_calls: list[tuple[tuple, dict]] = []

    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.get_calls.append((args, kwargs))
        return FakeResponse({"data": []}, status_code=200)

    def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append((args, kwargs))
        return FakeResponse(self.payload, status_code=self.status_code)


def test_openrouter_client_missing_key_falls_back_without_crashing() -> None:
    client = OpenRouterClient.from_environment({})

    assert client.has_api_key() is False
    assert client.is_configured() is False
    assert client.is_available() is False
    assert client.model_name == DEFAULT_OPENROUTER_MODEL
    assert client.analyze_sentence("আমি বাংলা লিখি।", "standard") == []


def test_openrouter_client_placeholder_key_stays_disabled() -> None:
    client = OpenRouterClient.from_environment({"OPENROUTER_API_KEY": "your_key_here"})

    assert client.has_api_key() is True
    assert client.is_configured() is False
    assert client.is_available() is False
    assert client.model_name == DEFAULT_OPENROUTER_MODEL


def test_parse_openrouter_response_discards_malformed_payload_safely() -> None:
    assert parse_openrouter_response("not-json", sentence="আমি বাংলা লিখি।") == []


def test_openrouter_client_ignores_malformed_response_text() -> None:
    session = FakeSession(
        {
            "choices": [
                {
                    "message": {
                        "content": "```json\nnot valid\n```",
                    }
                }
            ]
        }
    )
    client = OpenRouterClient(
        session=session,
        api_key="test-key",
        model_name="openrouter-test",
        timeout_seconds=20,
        enabled=True,
    )

    assert client.analyze_sentence("আমি বাংলা লিখি।", "standard") == []
    assert session.calls[0][1]["json"]["response_format"]["json_schema"]["strict"] is True
    assert session.get_calls


def test_parse_openrouter_response_accepts_valid_json_issues() -> None:
    issues = parse_openrouter_response(
        """
        {
          "issues": [
            {
              "category": "spelling",
              "subtype": "spelling_error",
              "span_text": "আমরাআ",
              "replacement": "আমরা",
              "explanation_bn": "এখানে অতিরিক্ত অক্ষর আছে।",
              "confidence": 0.96,
              "occurrence_index": 0,
              "anchor_before": null,
              "anchor_after": " আসি।"
            }
          ]
        }
        """,
        sentence="আমরাআ আসি।",
    )

    assert len(issues) == 1
    assert issues[0].category == OpenRouterIssueCategory.SPELLING_ERROR
    assert issues[0].subtype == "spelling_error"
    assert issues[0].start == 0
    assert issues[0].end == 5


def test_parse_openrouter_response_discards_ambiguous_span_text_matches_without_occurrence_or_anchors() -> None:
    issues = parse_openrouter_response(
        """
        {
          "issues": [
            {
              "category": "grammar",
              "subtype": "repeated_word",
              "span_text": "আমি",
              "replacement": "আমরা",
              "explanation_bn": "একই শব্দ পুনরাবৃত্ত হয়েছে।",
              "confidence": 0.94,
              "occurrence_index": null,
              "anchor_before": null,
              "anchor_after": null
            }
          ]
        }
        """,
        sentence="আমি আমি স্কুলে যাই।",
    )

    assert issues == []


def test_parse_openrouter_response_uses_occurrence_index_for_repeated_span_text() -> None:
    issues = parse_openrouter_response(
        """
        {
          "issues": [
            {
              "category": "grammar",
              "subtype": "pronoun_verb_agreement",
              "span_text": "আমি",
              "replacement": "আমরা",
              "explanation_bn": "'আমি' এর বদলে 'আমরা' দরকার।",
              "confidence": 0.95,
              "occurrence_index": 1,
              "anchor_before": "আমি ",
              "anchor_after": " স্কুলে"
            }
          ]
        }
        """,
        sentence="আমি আমি স্কুলে যাই।",
    )

    assert len(issues) == 1
    assert issues[0].start == 4
    assert issues[0].end == 7
    assert issues[0].occurrence_index == 1


def test_parse_openrouter_response_uses_anchor_triplet_for_repeated_bengali_word() -> None:
    issues = parse_openrouter_response(
        """
        {
          "issues": [
            {
              "category": "grammar",
              "subtype": "repeated_word",
              "span_text": "আজও",
              "replacement": "আজ",
              "explanation_bn": "'আজও' নয়, এখানে 'আজ' হবে।",
              "confidence": 0.96,
              "occurrence_index": null,
              "anchor_before": "আজও ",
              "anchor_after": " ভালো।"
            }
          ]
        }
        """,
        sentence="আজও আজও ভালো।",
    )

    assert len(issues) == 1
    assert issues[0].start == 4
    assert issues[0].end == 7
