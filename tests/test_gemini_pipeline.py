from pathlib import Path

from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.analysis.shuddho_analysis.detector import DetectorService
from services.llm.shuddho_llm.client import GeminiHint
from services.llm.shuddho_llm.parsing import GeminiIssue, GeminiIssueCategory
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode


class RecordingGeminiClient:
    def __init__(self, issues_by_sentence: dict[str, list[GeminiIssue]] | None = None, *, available: bool = True) -> None:
        self.issues_by_sentence = issues_by_sentence or {}
        self.available = available
        self.calls: list[tuple[str, str, list[GeminiHint]]] = []
        self.model_name = "gemini-test"

    def is_available(self) -> bool:
        return self.available

    def analyze_sentence(self, sentence: str, mode: str, *, local_hints: list[GeminiHint] | None = None) -> list[GeminiIssue]:
        self.calls.append((sentence, mode, list(local_hints or [])))
        return list(self.issues_by_sentence.get(sentence, []))


def test_pipeline_routes_only_suspicious_sentences_to_gemini(tmp_path: Path) -> None:
    gemini_client = RecordingGeminiClient()
    pipeline = _build_pipeline(tmp_path, gemini_client=gemini_client)

    pipeline.analyze(
        "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964 \u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf\u0964",
        mode=AnalyzeMode.STANDARD,
    )

    assert [call[0] for call in gemini_client.calls] == ["\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"]


def test_pipeline_still_works_when_gemini_is_unavailable(tmp_path: Path) -> None:
    gemini_client = RecordingGeminiClient(available=False)
    pipeline = _build_pipeline(tmp_path, gemini_client=gemini_client)

    response = pipeline.analyze("\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964", mode=AnalyzeMode.STANDARD)

    assert any(suggestion.rule_id == "REP_001" for suggestion in response.suggestions)
    assert gemini_client.calls == []


def test_pipeline_hides_low_confidence_gemini_suggestions(tmp_path: Path) -> None:
    sentence = "\u0986\u09ae\u09bf \u0986\u09ae\u09bf \u09b8\u09cd\u0995\u09c1\u09b2\u09c7 \u09af\u09be\u0987\u0964"
    gemini_client = RecordingGeminiClient(
        {
            sentence: [
                GeminiIssue(
                    start=0,
                    end=7,
                    original="\u0986\u09ae\u09bf \u0986\u09ae\u09bf",
                    replacement="\u0986\u09ae\u09bf",
                    category=GeminiIssueCategory.GRAMMAR_ERROR,
                    confidence=0.7,
                    reason_bn="\u098f\u0996\u09be\u09a8\u09c7 \u0985\u09aa\u09cd\u09b0\u09df\u09cb\u099c\u09a8\u09c0\u09df \u09aa\u09c1\u09a8\u09b0\u09be\u09ac\u09c3\u09a4\u09cd\u09a4\u09bf \u0986\u099b\u09c7\u0964",
                )
            ]
        }
    )
    pipeline = _build_pipeline(tmp_path, gemini_client=gemini_client)

    response = pipeline.analyze(sentence, mode=AnalyzeMode.STANDARD)

    assert all(not suggestion.rule_id.startswith("LLM_") for suggestion in response.suggestions)


def _build_pipeline(tmp_path: Path, *, gemini_client: RecordingGeminiClient) -> AnalysisPipeline:
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
        gemini_client=gemini_client,
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
