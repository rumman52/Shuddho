from pathlib import Path

from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.llm.shuddho_llm.openrouter_client import OpenRouterHint
from services.llm.shuddho_llm.parsing import OpenRouterIssue, OpenRouterIssueCategory
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, SuggestionSource


class RecordingOpenRouterClient:
    def __init__(self, issues_by_sentence: dict[str, list[OpenRouterIssue]] | None = None, *, available: bool = True) -> None:
        self.issues_by_sentence = issues_by_sentence or {}
        self.available = available
        self.calls: list[tuple[str, str, list[OpenRouterHint]]] = []
        self.model_name = "openrouter-test"

    def is_configured(self) -> bool:
        return self.available

    def is_available(self) -> bool:
        return self.available

    def runtime_status(self):
        return type(
            "OpenRouterStatus",
            (),
            {
                "configured": self.available,
                "available": self.available,
                "status": "ready" if self.available else "missing_api_key",
                "reason": None if self.available else "OPENROUTER_API_KEY is missing from the repo-root environment.",
                "model": self.model_name,
                "api_key_present": self.available,
                "timeout_seconds": 20,
                "probed": False,
                "probe_success": None,
                "probe_status": None,
                "probe_reason": None,
                "probe_checked_at": None,
            },
        )()

    def analyze_sentence(self, sentence: str, mode: str, *, local_hints: list[OpenRouterHint] | None = None) -> list[OpenRouterIssue]:
        self.calls.append((sentence, mode, list(local_hints or [])))
        return list(self.issues_by_sentence.get(sentence, []))


def test_pipeline_routes_only_suspicious_sentences_to_openrouter(tmp_path: Path) -> None:
    openrouter_client = RecordingOpenRouterClient()
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    pipeline.analyze(
        "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964 \u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964",
        mode=AnalyzeMode.STANDARD,
    )

    assert [call[0] for call in openrouter_client.calls] == ["\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"]


def test_pipeline_strict_mode_routes_all_eligible_sentences_to_openrouter(tmp_path: Path) -> None:
    openrouter_client = RecordingOpenRouterClient()
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    pipeline.analyze(
        "\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964 \u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964",
        mode=AnalyzeMode.STRICT,
    )

    assert [call[0] for call in openrouter_client.calls] == [
        "\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964",
        "\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964",
    ]


def test_pipeline_standard_mode_routes_first_eligible_sentence_when_local_rules_are_quiet(tmp_path: Path) -> None:
    openrouter_client = RecordingOpenRouterClient()
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    pipeline.analyze(
        "\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964",
        mode=AnalyzeMode.STANDARD,
    )

    assert [call[0] for call in openrouter_client.calls] == ["\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964"]


def test_pipeline_still_works_when_openrouter_is_unavailable(tmp_path: Path) -> None:
    openrouter_client = RecordingOpenRouterClient(available=False)
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    response = pipeline.analyze("\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964", mode=AnalyzeMode.STANDARD)

    assert any(suggestion.rule_id == "REP_001" for suggestion in response.suggestions)
    assert openrouter_client.calls == []


def test_pipeline_hides_low_confidence_openrouter_suggestions(tmp_path: Path) -> None:
    sentence = "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"
    openrouter_client = RecordingOpenRouterClient(
        {
            sentence: [
                OpenRouterIssue(
                    **_issue_kwargs(
                        start=0,
                        end=7,
                        original="\u0986\u09ae\u09bf \u0986\u09ae\u09bf",
                        replacement="\u0986\u09ae\u09bf",
                        category=OpenRouterIssueCategory.GRAMMAR_ERROR,
                        confidence=0.7,
                    ),
                )
            ]
        }
    )
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    response = pipeline.analyze(sentence, mode=AnalyzeMode.STANDARD)

    assert all(not suggestion.rule_id.startswith("LLM_") for suggestion in response.suggestions)


def test_pipeline_keeps_valid_openrouter_grammar_suggestions_in_strict_mode(tmp_path: Path) -> None:
    sentence = "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"
    openrouter_client = RecordingOpenRouterClient(
        {
            sentence: [
                OpenRouterIssue(
                    **_issue_kwargs(
                        start=0,
                        end=7,
                        original="\u0986\u09ae\u09bf \u0986\u09ae\u09bf",
                        replacement="\u0986\u09ae\u09bf",
                        category=OpenRouterIssueCategory.GRAMMAR_ERROR,
                        confidence=0.88,
                    ),
                )
            ]
        }
    )
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    response = pipeline.analyze(sentence, mode=AnalyzeMode.STRICT)

    assert any(suggestion.source == SuggestionSource.HYBRID for suggestion in response.suggestions)


def test_pipeline_standard_mode_no_longer_overfilters_valid_openrouter_grammar_suggestions(tmp_path: Path) -> None:
    sentence = "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"
    openrouter_client = RecordingOpenRouterClient(
        {
            sentence: [
                OpenRouterIssue(
                    **_issue_kwargs(
                        start=0,
                        end=7,
                        original="\u0986\u09ae\u09bf \u0986\u09ae\u09bf",
                        replacement="\u0986\u09ae\u09bf",
                        category=OpenRouterIssueCategory.GRAMMAR_ERROR,
                        confidence=0.92,
                    ),
                )
            ]
        }
    )
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    response = pipeline.analyze(sentence, mode=AnalyzeMode.STANDARD)

    assert any(suggestion.source == SuggestionSource.HYBRID for suggestion in response.suggestions)


def test_pipeline_preserves_repeated_span_metadata_for_contextual_suggestions(tmp_path: Path) -> None:
    sentence = "\u0986\u099c\u0993 \u0986\u099c\u0993 \u09ad\u09be\u09b2\u09cb\u0964"
    openrouter_client = RecordingOpenRouterClient(
        {
            sentence: [
                OpenRouterIssue(
                    **_issue_kwargs(
                        start=4,
                        end=7,
                        original="\u0986\u099c\u0993",
                        replacement="\u0986\u099c",
                        category=OpenRouterIssueCategory.GRAMMAR_ERROR,
                        confidence=0.95,
                        occurrence_index=1,
                        anchor_before="\u0986\u099c\u0993 ",
                        anchor_after=" \u09ad\u09be\u09b2\u09cb\u0964",
                        source_trace=["occurrence_index", "anchor_triplet"],
                    ),
                )
            ]
        }
    )
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    response = pipeline.analyze(sentence, mode=AnalyzeMode.STRICT)
    suggestion = next(suggestion for suggestion in response.suggestions if suggestion.rule_id.startswith("LLM_"))

    assert suggestion.span_start == 4
    assert suggestion.span_end == 7
    assert suggestion.occurrence_index == 1
    assert suggestion.anchor_before == "\u0986\u099c\u0993 "
    assert suggestion.anchor_after == " \u09ad\u09be\u09b2\u09cb\u0964"


def test_pipeline_does_not_auto_apply_llm_grammar_suggestions_into_corrected_text(tmp_path: Path) -> None:
    sentence = "\u0986\u099c\u0993 \u0986\u099c\u0993 \u09ad\u09be\u09b2\u09cb\u0964"
    openrouter_client = RecordingOpenRouterClient(
        {
            sentence: [
                OpenRouterIssue(
                    **_issue_kwargs(
                        start=4,
                        end=7,
                        original="\u0986\u099c\u0993",
                        replacement="\u0986\u099c",
                        category=OpenRouterIssueCategory.GRAMMAR_ERROR,
                        confidence=0.95,
                        occurrence_index=1,
                        anchor_before="\u0986\u099c\u0993 ",
                        anchor_after=" \u09ad\u09be\u09b2\u09cb\u0964",
                        source_trace=["occurrence_index", "anchor_triplet"],
                    ),
                )
            ]
        }
    )
    pipeline = _build_pipeline(tmp_path, openrouter_client=openrouter_client)

    response = pipeline.analyze(sentence, mode=AnalyzeMode.STRICT)

    assert response.corrected_text == "আজও ভালো।"
    assert response.corrected_text != "আজও আজ ভালো।"


def _build_pipeline(tmp_path: Path, *, openrouter_client: RecordingOpenRouterClient) -> AnalysisPipeline:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u09b8\u09cd\u0995\u09c1\u09b2\u09c7", "\u09b8\u09cd\u0995\u09c1\u09b2\u09c7", "fixture.csv", "1", "1", "1"),
            ("\u09af\u09be\u0987", "\u09af\u09be\u0987", "fixture.csv", "1", "1", "1"),
            ("\u09ac\u09be\u0982\u09b2\u09be", "\u09ac\u09be\u0982\u09b2\u09be", "fixture.csv", "1", "1", "1"),
            ("\u09b2\u09bf\u0996\u09bf", "\u09b2\u09bf\u0996\u09bf", "fixture.csv", "1", "1", "1"),
        ],
    )
    return AnalysisPipeline(
        normalizer=BanglaNormalizer(),
        spell_engine=SpellEngine(runtime_csv_path=runtime_csv_path),
        rule_engine=RuleEngine(),
        suggestion_manager=SuggestionManager(),
        detector_service=DetectorService(),
        openrouter_client=openrouter_client,
    )


def _write_clean_csv_fixture(
    base_dir: Path,
    *,
    rows: list[tuple[str, str, str, str, str, str]],
) -> Path:
    runtime_csv_path = base_dir / "words_clean.csv"
    lines = ["word,normalized_word,source,is_trusted,is_common,is_active"]
    lines.extend(",".join(row) for row in rows)
    runtime_csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_csv_path


def _issue_kwargs(
    *,
    start: int,
    end: int,
    original: str,
    replacement: str,
    category: OpenRouterIssueCategory,
    confidence: float,
    occurrence_index: int | None = None,
    anchor_before: str | None = None,
    anchor_after: str | None = None,
    source_trace: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "start": start,
        "end": end,
        "original": original,
        "replacement": replacement,
        "category": category,
        "confidence": confidence,
        "reason_bn": f"'{original}' \u098f\u09b0 \u09ac\u09a6\u09b2\u09c7 '{replacement}' \u09a6\u09b0\u0995\u09be\u09b0\u0964",
    }
    if occurrence_index is not None:
        payload["occurrence_index"] = occurrence_index
    if anchor_before is not None:
        payload["anchor_before"] = anchor_before
    if anchor_after is not None:
        payload["anchor_after"] = anchor_after
    payload["source_trace"] = list(source_trace or ["exact_unique_match"])
    return payload
