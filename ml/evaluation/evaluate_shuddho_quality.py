from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from services.analysis.shuddho_analysis.candidate_generator import CandidateGenerator
from services.analysis.shuddho_analysis.corrector_service import CorrectorService
from services.analysis.shuddho_analysis.detector import DetectorService
from services.analysis.shuddho_analysis.pipeline import AnalysisPipeline
from services.analysis.shuddho_analysis.preferences import UserPreferencesService
from services.analysis.shuddho_analysis.ranking import SuggestionRankingPipeline
from services.analysis.shuddho_analysis.suggestion_validation import looks_generic_explanation
from services.feedback.shuddho_feedback.store import FeedbackStore
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import AnalyzeMode, Suggestion


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_SIBLING_SUFFIX = "_formal"


@dataclass(frozen=True)
class GoldSuggestion:
    category: str
    subtype: str
    original_text: str
    replacement: str
    safe_auto_apply: bool


@dataclass(frozen=True)
class GoldExample:
    id: str
    input: str
    expected_corrected: str
    expected_suggestions: tuple[GoldSuggestion, ...]
    mode: AnalyzeMode


def build_pipeline() -> AnalysisPipeline:
    feedback_store = FeedbackStore()
    return AnalysisPipeline(
        normalizer=BanglaNormalizer(),
        spell_engine=SpellEngine(runtime_csv_path=REPO_ROOT / "data" / "runtime" / "lexicon" / "runtime_words.csv"),
        rule_engine=RuleEngine(),
        suggestion_manager=SuggestionManager(),
        detector_service=DetectorService.from_environment(),
        corrector_service=CorrectorService.from_environment(),
        candidate_generator=CandidateGenerator(),
        ranking_pipeline=SuggestionRankingPipeline(feedback_store=feedback_store),
    )


def load_gold_examples(gold_path: Path) -> list[GoldExample]:
    examples = _load_jsonl(gold_path, mode=AnalyzeMode.STANDARD)
    formal_path = gold_path.with_name(f"{gold_path.stem}{FORMAL_SIBLING_SUFFIX}{gold_path.suffix}")
    if formal_path.exists():
        examples.extend(_load_jsonl(formal_path, mode=AnalyzeMode.FORMAL))
    return examples


def _load_jsonl(path: Path, *, mode: AnalyzeMode) -> list[GoldExample]:
    examples: list[GoldExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        expected_suggestions = tuple(
            GoldSuggestion(
                category=item["category"],
                subtype=item["subtype"],
                original_text=item["original_text"],
                replacement=item["replacement"],
                safe_auto_apply=bool(item["safe_auto_apply"]),
            )
            for item in payload.get("expected_suggestions", [])
        )
        examples.append(
            GoldExample(
                id=payload["id"],
                input=payload["input"],
                expected_corrected=payload["expected_corrected"],
                expected_suggestions=expected_suggestions,
                mode=mode,
            )
        )
    return examples


def evaluate(gold_path: Path) -> dict[str, float | int]:
    pipeline = build_pipeline()
    examples = load_gold_examples(gold_path)

    total_expected = 0
    matched_predictions = 0
    matched_expected = 0
    matched_spans = 0
    matched_replacements = 0
    predicted_total = 0
    exact_corrected_matches = 0
    false_positive_count = 0
    generic_suggestion_count = 0
    deterministic_expected = 0
    deterministic_replacement_matches = 0
    whole_sentence_rewrite_count = 0

    for example in examples:
        response = pipeline.analyze(example.input, mode=example.mode)
        predicted = response.suggestions
        predicted_total += len(predicted)
        total_expected += len(example.expected_suggestions)

        if response.corrected_text == example.expected_corrected:
            exact_corrected_matches += 1

        if not example.expected_suggestions:
            false_positive_count += len(predicted)

        generic_suggestion_count += sum(
            1 for suggestion in predicted if looks_generic_explanation(suggestion.explanation_bn or suggestion.explanation_en, suggestion)
        )
        whole_sentence_rewrite_count += sum(1 for suggestion in predicted if _looks_like_whole_sentence_rewrite(example.input, suggestion))

        matched_predicted_indices: set[int] = set()
        for expected in example.expected_suggestions:
            expected_span = _unique_span(example.input, expected.original_text)
            if expected.safe_auto_apply:
                deterministic_expected += 1

            span_match = _find_matching_prediction(
                predicted,
                expected,
                expected_span=expected_span,
                require_replacement=False,
                require_category=False,
            )
            if span_match is not None:
                matched_spans += 1

            replacement_match = _find_matching_prediction(
                predicted,
                expected,
                expected_span=expected_span,
                require_replacement=True,
                require_category=False,
            )
            if replacement_match is not None:
                matched_replacements += 1
                if expected.safe_auto_apply:
                    deterministic_replacement_matches += 1

            exact_match = _find_matching_prediction(
                predicted,
                expected,
                expected_span=expected_span,
                require_replacement=True,
                require_category=True,
            )
            if exact_match is not None:
                matched_expected += 1
                matched_predicted_indices.add(exact_match)

        matched_predictions += len(matched_predicted_indices)

    precision = matched_predictions / predicted_total if predicted_total else 1.0
    recall = matched_expected / total_expected if total_expected else 1.0
    exact_corrected_text_match = exact_corrected_matches / max(len(examples), 1)
    span_match_accuracy = matched_spans / total_expected if total_expected else 1.0
    replacement_accuracy = matched_replacements / total_expected if total_expected else 1.0
    deterministic_replacement_accuracy = (
        deterministic_replacement_matches / deterministic_expected if deterministic_expected else 1.0
    )

    metrics: dict[str, float | int] = {
        "example_count": len(examples),
        "predicted_suggestion_count": predicted_total,
        "expected_suggestion_count": total_expected,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "exact_corrected_text_match": round(exact_corrected_text_match, 4),
        "span_match_accuracy": round(span_match_accuracy, 4),
        "replacement_accuracy": round(replacement_accuracy, 4),
        "deterministic_replacement_accuracy": round(deterministic_replacement_accuracy, 4),
        "false_positive_count": false_positive_count,
        "generic_suggestion_count": generic_suggestion_count,
        "whole_sentence_rewrite_count": whole_sentence_rewrite_count,
    }
    return metrics


def _find_matching_prediction(
    predicted: list[Suggestion],
    expected: GoldSuggestion,
    *,
    expected_span: tuple[int, int] | None,
    require_replacement: bool,
    require_category: bool,
) -> int | None:
    for index, suggestion in enumerate(predicted):
        if expected_span is not None and (suggestion.span_start, suggestion.span_end) != expected_span:
            continue
        if suggestion.original_text != expected.original_text:
            continue
        if suggestion.subtype != expected.subtype:
            continue
        if require_category and suggestion.category.value != expected.category:
            continue
        if require_replacement and expected.replacement not in suggestion.replacement_options:
            continue
        return index
    return None


def _unique_span(text: str, original_text: str) -> tuple[int, int] | None:
    matches: list[int] = []
    cursor = 0
    while True:
        index = text.find(original_text, cursor)
        if index < 0:
            break
        matches.append(index)
        cursor = index + 1
    if len(matches) != 1:
        return None
    start = matches[0]
    return start, start + len(original_text)


def _looks_like_whole_sentence_rewrite(text: str, suggestion: Suggestion) -> bool:
    stripped_text = text.strip()
    if not stripped_text or not suggestion.replacement_options:
        return False
    replacement = suggestion.replacement_options[0].strip()
    span_length = suggestion.span_end - suggestion.span_start
    if suggestion.span_start == 0 and suggestion.span_end == len(text):
        return True
    if span_length >= max(int(len(text) * 0.6), 12):
        return True
    if len(replacement.split()) >= max(len(stripped_text.split()) - 1, 4):
        return True
    return False


def _print_report(metrics: dict[str, float | int]) -> None:
    for key, value in metrics.items():
        print(f"{key}: {value}")


def _enforce_thresholds(metrics: dict[str, float | int]) -> None:
    failures: list[str] = []
    if int(metrics["false_positive_count"]) != 0:
        failures.append("false positives on clean sentences must be 0")
    if int(metrics["generic_suggestion_count"]) != 0:
        failures.append("generic suggestion count must be 0")
    if float(metrics["deterministic_replacement_accuracy"]) < 0.8:
        failures.append("deterministic replacement accuracy must be at least 80%")
    if int(metrics["whole_sentence_rewrite_count"]) != 0:
        failures.append("whole-sentence rewrite suggestions are not allowed in /analyze")
    if failures:
        raise SystemExit("Evaluation thresholds failed:\n- " + "\n- ".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Shuddho suggestion quality against the human gold set.")
    parser.add_argument("--gold", required=True, help="Path to the main gold JSONL file.")
    args = parser.parse_args()

    gold_path = Path(args.gold)
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path

    metrics = evaluate(gold_path)
    _print_report(metrics)
    _enforce_thresholds(metrics)


if __name__ == "__main__":
    main()
