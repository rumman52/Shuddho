from __future__ import annotations

import logging

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.schemas.python_models import (
    AnalysisProfile,
    AnalyzeMode,
    AnalyzeResponse,
    Suggestion,
    SuggestionCategory,
    SuggestionKind,
    SuggestionSeverity,
    SuggestionSource,
)

from .candidate_generator import CandidateGenerator
from .conflict_resolution import build_best_corrected_text, resolve_same_span_conflicts
from .corrector_service import CorrectorService
from .detector import DetectorService
from .models import AnalysisArtifacts
from .ranking import SuggestionRankingPipeline
from .suggestion_validation import (
    looks_generic_explanation,
    minimum_confidence_for_suggestion,
    validate_suggestions,
)
from .span_resolution import enrich_suggestions_with_text_context, split_sentences
from .ui_enrichment import SuggestionUiEnricher

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(
        self,
        *,
        normalizer: BanglaNormalizer,
        spell_engine: SpellEngine,
        rule_engine: RuleEngine,
        suggestion_manager: SuggestionManager,
        detector_service: DetectorService | None = None,
        corrector_service: CorrectorService | None = None,
        candidate_generator: CandidateGenerator | None = None,
        ranking_pipeline: SuggestionRankingPipeline | None = None,
        ui_enricher: SuggestionUiEnricher | None = None,
    ) -> None:
        self.normalizer = normalizer
        self.spell_engine = spell_engine
        self.rule_engine = rule_engine
        self.suggestion_manager = suggestion_manager
        self.detector_service = detector_service or DetectorService()
        self.corrector_service = corrector_service or CorrectorService.from_environment()
        self.candidate_generator = candidate_generator or CandidateGenerator(spell_engine=spell_engine)
        if getattr(self.candidate_generator, "spell_engine", None) is None:
            self.candidate_generator.spell_engine = spell_engine
        self.ranking_pipeline = ranking_pipeline or SuggestionRankingPipeline()
        self.ui_enricher = ui_enricher or SuggestionUiEnricher(auto_apply_checker=is_safe_auto_apply_suggestion)

    def analyze(
        self,
        text: str,
        personal_dictionary: list[str] | None = None,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> AnalyzeResponse:
        artifacts = self.analyze_artifacts(text, personal_dictionary, mode=mode)
        return AnalyzeResponse(
            text=text,
            normalized_text=artifacts.normalized.text,
            corrected_text=build_corrected_text(text, artifacts.merged_suggestions),
            suggestions=artifacts.merged_suggestions,
            analysis_profile=artifacts.analysis_profile,
            runtime_source=artifacts.analysis_profile,
            runtime_warnings=artifacts.runtime_warnings,
            used_detector=artifacts.used_detector,
            used_corrector=artifacts.used_corrector,
            backend_warning=artifacts.backend_warning,
            lexicon_source=self.spell_engine.lexicon_source,
            lexicon_version=self.spell_engine.lexicon_version,
            sentence_count=len(artifacts.sentence_spans),
            request_mode_applied=mode,
        )

    def analyze_artifacts(
        self,
        text: str,
        personal_dictionary: list[str] | None = None,
        *,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> AnalysisArtifacts:
        logger.debug(
            "Starting local analysis mode=%s text_length=%s detector_loaded=%s corrector_loaded=%s",
            mode.value,
            len(text),
            self.detector_service.is_loaded(),
            self.corrector_service.is_loaded(),
        )
        sentence_spans = split_sentences(text)
        normalized = self.normalizer.normalize(text)
        rule_suggestions = self.rule_engine.analyze(text)
        detector_findings = self.detector_service.detect(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
        )
        spell_suggestions = self.spell_engine.analyze(normalized.text, personal_dictionary)
        corrector_suggestions = self.corrector_service.suggest(
            text,
            mode=mode,
            personal_dictionary=personal_dictionary,
        )
        candidates = self.candidate_generator.generate(
            spell_suggestions=spell_suggestions,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            corrector_suggestions=corrector_suggestions,
            text=text,
            personal_dictionary=personal_dictionary,
            mode=mode,
        )
        prepared_suggestions = self.suggestion_manager.prepare_candidates(
            original_text=text,
            normalized=normalized,
            spell_suggestions=candidates.spell_suggestions,
            rule_suggestions=candidates.rule_suggestions,
            detector_suggestions=candidates.detector_suggestions,
            corrector_suggestions=candidates.corrector_suggestions,
        )
        ranked_suggestions = self.ranking_pipeline.rank(prepared_suggestions, text=text, mode=mode)
        merged_suggestions = _apply_request_mode(
            self.suggestion_manager.finalize_ranked(ranked_suggestions),
            mode=mode,
        )
        merged_suggestions = resolve_same_span_conflicts(merged_suggestions)
        merged_suggestions = enrich_suggestions_with_text_context(text, merged_suggestions)
        merged_suggestions = validate_suggestions(text, merged_suggestions, mode=mode, logger=logger)
        merged_suggestions = self.ui_enricher.enrich(text, merged_suggestions)

        detector_runtime = self.detector_service.runtime_status()
        corrector_runtime = self.corrector_service.runtime_status()
        analysis_profile = _derive_runtime_profile(detector_runtime.loaded, corrector_runtime.loaded)
        backend_warning = _derive_backend_warning(detector_runtime, corrector_runtime)
        return AnalysisArtifacts(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            spell_suggestions=spell_suggestions,
            candidates=candidates,
            prepared_suggestions=prepared_suggestions,
            ranked_suggestions=ranked_suggestions,
            merged_suggestions=merged_suggestions,
            sentence_spans=sentence_spans,
            used_detector=_used_detector_in_visible_output(merged_suggestions),
            used_corrector=_used_corrector_in_visible_output(merged_suggestions),
            backend_warning=backend_warning,
            runtime_warnings=_build_runtime_warnings(detector_runtime, corrector_runtime),
            analysis_profile=analysis_profile,
        )


def _apply_request_mode(suggestions: list[Suggestion], *, mode: AnalyzeMode) -> list[Suggestion]:
    visible_suggestions = [
        suggestion
        for suggestion in suggestions
        if _mode_allows_visibility(suggestion, mode=mode)
    ]
    gated_suggestions = [
        suggestion
        for suggestion in visible_suggestions
        if _passes_precision_gate(suggestion, mode=mode)
    ]

    hard_suggestions = [
        suggestion
        for suggestion in gated_suggestions
        if suggestion.category not in {
            SuggestionCategory.REGISTER,
            SuggestionCategory.CLARITY,
            SuggestionCategory.REWRITE_ONLY,
        }
    ]
    style_suggestions = [
        suggestion
        for suggestion in gated_suggestions
        if suggestion.category in {
            SuggestionCategory.REGISTER,
            SuggestionCategory.CLARITY,
        }
    ]

    if mode == AnalyzeMode.FORMAL:
        style_suggestions = sorted(style_suggestions, key=_formal_style_sort_key)

    return [*hard_suggestions, *style_suggestions]


def build_corrected_text(text: str, suggestions: list[Suggestion]) -> str:
    return build_best_corrected_text(
        text,
        suggestions,
        is_safe_auto_apply_suggestion=_is_safe_auto_apply_suggestion,
    )


def is_safe_auto_apply_suggestion(text: str, suggestion: Suggestion) -> bool:
    return _is_safe_auto_apply_suggestion(text, suggestion)


def _mode_allows_visibility(suggestion: Suggestion, *, mode: AnalyzeMode) -> bool:
    if suggestion.suggestion_kind in {
        SuggestionKind.NO_SUGGESTION,
        SuggestionKind.NAMED_ENTITY_OR_USER_WORD,
    }:
        return False
    if not suggestion.optional_mode_visibility:
        return True
    return mode in set(suggestion.optional_mode_visibility)


def _passes_precision_gate(suggestion: Suggestion, *, mode: AnalyzeMode) -> bool:
    threshold = minimum_confidence_for_suggestion(suggestion, mode=mode)
    if suggestion.source == SuggestionSource.HYBRID:
        threshold = max(threshold - 0.02, 0.0)
    if _is_high_precision_style_suggestion(suggestion):
        threshold -= {
            AnalyzeMode.STANDARD: 0.06,
            AnalyzeMode.STRICT: 0.04,
            AnalyzeMode.FORMAL: 0.02,
        }[mode]
    if not suggestion.replacement_options:
        threshold += 0.08 if mode == AnalyzeMode.STANDARD else 0.03
    if suggestion.severity == SuggestionSeverity.HIGH:
        threshold -= 0.03
    if suggestion.source == SuggestionSource.MODEL and _is_rewrite_like_suggestion(suggestion):
        threshold += 0.18
    if suggestion.source == SuggestionSource.MODEL and looks_generic_explanation(suggestion.explanation_bn, suggestion):
        threshold += 0.08
    if suggestion.source == SuggestionSource.MODEL and suggestion.source_trace and "anchor_nearest_safe" in suggestion.source_trace:
        threshold += 0.04
    return suggestion.confidence >= threshold


def _is_safe_auto_apply_suggestion(text: str, suggestion: Suggestion) -> bool:
    if suggestion.category in {
        SuggestionCategory.REGISTER,
        SuggestionCategory.CLARITY,
        SuggestionCategory.REWRITE_ONLY,
    }:
        return False
    if suggestion.rule_id.startswith("DET_"):
        return False
    if suggestion.source == SuggestionSource.MODEL and suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR:
        return False
    if suggestion.suggestion_kind in {
        SuggestionKind.STYLE_SUGGESTION,
        SuggestionKind.ORTHOGRAPHY_VARIANT,
        SuggestionKind.NAMED_ENTITY_OR_USER_WORD,
        SuggestionKind.NO_SUGGESTION,
    }:
        return False
    if len(suggestion.replacement_options) != 1:
        return False
    if suggestion.span_start < 0 or suggestion.span_end > len(text) or suggestion.span_start >= suggestion.span_end:
        return False

    original_text = text[suggestion.span_start:suggestion.span_end]
    replacement = suggestion.replacement_options[0]
    if not replacement or original_text != suggestion.original_text or replacement == original_text:
        return False
    if "\n" in replacement:
        return False
    if suggestion.confidence < _auto_apply_confidence_threshold(suggestion):
        return False

    if suggestion.suggestion_kind == SuggestionKind.PUNCTUATION_ERROR:
        return _is_precise_punctuation_edit(original_text, replacement)
    if suggestion.suggestion_kind == SuggestionKind.SPACING_ERROR:
        return _is_precise_spacing_edit(original_text, replacement)
    if suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR:
        return _is_precise_local_edit(original_text, replacement, text)
    return True


def _auto_apply_confidence_threshold(suggestion: Suggestion) -> float:
    thresholds = {
        SuggestionSource.RULE: 0.0,
        SuggestionSource.SPELL: 0.97,
        SuggestionSource.HYBRID: 0.97,
        SuggestionSource.MODEL: 0.98,
    }
    threshold = thresholds[suggestion.source]
    if suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR and suggestion.source in {
        SuggestionSource.MODEL,
        SuggestionSource.HYBRID,
    }:
        threshold = max(threshold, 0.99)
    return threshold


def _formal_style_sort_key(suggestion: Suggestion) -> tuple[int, int, float, int]:
    return (
        0 if suggestion.replacement_options else 1,
        0 if suggestion.severity != SuggestionSeverity.LOW else 1,
        -suggestion.confidence,
        suggestion.span_start,
    )


def _is_high_precision_style_suggestion(suggestion: Suggestion) -> bool:
    return (
        suggestion.suggestion_kind == SuggestionKind.STYLE_SUGGESTION
        and suggestion.subtype in {"number_unit_spacing", "mixed_digit_style"}
        and bool(suggestion.replacement_options)
    )


def _is_precise_local_edit(
    original: str,
    replacement: str,
    text: str,
    *,
    mode: AnalyzeMode = AnalyzeMode.STANDARD,
) -> bool:
    normalized_original = original.strip()
    normalized_replacement = replacement.strip()
    if not normalized_original or not normalized_replacement:
        return False
    if normalized_original == normalized_replacement:
        return False
    if normalized_replacement == text.strip() and normalized_original != text.strip():
        return False
    if _is_rewrite_like_replacement(normalized_original, normalized_replacement, text, mode=mode):
        return False
    return True


def _is_rewrite_like_replacement(original: str, replacement: str, text: str, *, mode: AnalyzeMode) -> bool:
    if not original or not replacement:
        return True
    text_tokens = max(len(text.split()), 1)
    replacement_tokens = len(replacement.split())
    token_limit = 6 if mode == AnalyzeMode.STANDARD else 8
    char_limit = (
        max(int(len(original) * 2.2), len(original) + 6, 16)
        if mode == AnalyzeMode.STANDARD
        else max(int(len(original) * 2.5), len(original) + 8, 24)
    )
    if replacement_tokens > token_limit:
        return True
    if len(replacement) > char_limit:
        return True
    if len(replacement) >= max(len(text.strip()) * 0.4, len(original) + 12) and len(text.strip()) > len(original):
        return True
    if replacement_tokens >= max(text_tokens - 1, 1) and replacement != original:
        return True
    return False


def _looks_generic_explanation(explanation: str, suggestion: Suggestion) -> bool:
    normalized = " ".join(explanation.split()).strip()
    if not normalized:
        return True
    if len(normalized.split()) <= 3:
        return True
    if suggestion.original_text not in normalized and not any(
        replacement in normalized for replacement in suggestion.replacement_options
    ):
        return any(marker in normalized for marker in {"আরও স্বাভাবিক", "আরও ভালো", "clearer", "more natural"})
    return False


def _is_rewrite_like_suggestion(suggestion: Suggestion) -> bool:
    if not suggestion.replacement_options:
        return True
    return _is_rewrite_like_local_replacement(
        suggestion.original_text.strip(),
        suggestion.replacement_options[0].strip(),
        mode=AnalyzeMode.STANDARD,
    )


def _is_rewrite_like_local_replacement(original: str, replacement: str, *, mode: AnalyzeMode) -> bool:
    if not original or not replacement:
        return True
    replacement_tokens = len(replacement.split())
    token_limit = 6 if mode == AnalyzeMode.STANDARD else 8
    char_limit = (
        max(int(len(original) * 2.2), len(original) + 6, 16)
        if mode == AnalyzeMode.STANDARD
        else max(int(len(original) * 2.5), len(original) + 8, 24)
    )
    if replacement_tokens > token_limit:
        return True
    if len(replacement) > char_limit:
        return True
    return False


def _is_precise_punctuation_edit(original: str, replacement: str) -> bool:
    return len(original.strip()) <= 6 and len(replacement.strip()) <= 8


def _is_precise_spacing_edit(original: str, replacement: str) -> bool:
    if not replacement:
        return False
    return len(replacement) <= max(len(original) + 2, 8)


def _build_runtime_warnings(detector_runtime, corrector_runtime) -> list[str]:  # type: ignore[no-untyped-def]
    warnings: list[str] = []
    if detector_runtime.status != "ready":
        warnings.append(f"detector_{detector_runtime.status}")
    if corrector_runtime.status != "ready":
        warnings.append(f"corrector_{corrector_runtime.status}")
    return warnings


def _derive_backend_warning(detector_runtime, corrector_runtime) -> str | None:  # type: ignore[no-untyped-def]
    if corrector_runtime.status != "ready":
        return "Sentence-level corrector is not loaded. Shuddho is running rules + spelling only."
    if detector_runtime.status != "ready":
        return "Detector is not loaded. Shuddho is using rules, spelling, and exact span anchors only."
    return None


def _used_detector_in_visible_output(suggestions: list[Suggestion]) -> bool:
    for suggestion in suggestions:
        if suggestion.rule_id.startswith("DET_"):
            return True
        if suggestion.source in {SuggestionSource.MODEL, SuggestionSource.HYBRID} and any(
            trace.startswith("detector_") for trace in (suggestion.source_trace or [])
        ):
            return True
    return False


def _used_corrector_in_visible_output(suggestions: list[Suggestion]) -> bool:
    return any("corrector_seq2seq" in (suggestion.source_trace or []) for suggestion in suggestions)


def _derive_runtime_profile(detector_ready: bool, corrector_ready: bool) -> AnalysisProfile:
    if detector_ready and corrector_ready:
        return AnalysisProfile.FULL_LOCAL
    if detector_ready:
        return AnalysisProfile.BACKEND_WITHOUT_CORRECTOR
    if corrector_ready:
        return AnalysisProfile.BACKEND_WITHOUT_DETECTOR
    return AnalysisProfile.BACKEND_RULES_AND_SPELL_ONLY
