from __future__ import annotations

import logging
import re

from services.llm.shuddho_llm.openrouter_client import OpenRouterClient, OpenRouterHint
from services.llm.shuddho_llm.parsing import OpenRouterIssue, OpenRouterIssueCategory
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.constants.bangla import BANGLA_LETTER_PATTERN, BANGLA_WORD_PATTERN
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
from shared.utils.text import stable_id

from .candidate_generator import CandidateGenerator
from .detector import DetectorService
from .models import AnalysisArtifacts, DetectorFinding
from .ranking import SuggestionRankingPipeline
from .span_resolution import SentenceSpan, enrich_suggestions_with_text_context, split_sentences

logger = logging.getLogger(__name__)

MAX_OPENROUTER_SENTENCES_PER_REQUEST = 4
STRICT_MODE_OPENROUTER_SENTENCE_LIMIT = 6
MAX_OPENROUTER_SENTENCE_LENGTH = 280
MIN_OPENROUTER_BANGLA_LETTERS = 4


class AnalysisPipeline:
    def __init__(
        self,
        *,
        normalizer: BanglaNormalizer,
        spell_engine: SpellEngine,
        rule_engine: RuleEngine,
        suggestion_manager: SuggestionManager,
        detector_service: DetectorService | None = None,
        candidate_generator: CandidateGenerator | None = None,
        ranking_pipeline: SuggestionRankingPipeline | None = None,
        openrouter_client: OpenRouterClient | None = None,
    ) -> None:
        self.normalizer = normalizer
        self.spell_engine = spell_engine
        self.rule_engine = rule_engine
        self.suggestion_manager = suggestion_manager
        self.detector_service = detector_service or DetectorService()
        self.candidate_generator = candidate_generator or CandidateGenerator(spell_engine=spell_engine)
        if getattr(self.candidate_generator, "spell_engine", None) is None:
            self.candidate_generator.spell_engine = spell_engine
        self.ranking_pipeline = ranking_pipeline or SuggestionRankingPipeline()
        self.openrouter_client = openrouter_client or OpenRouterClient.disabled()

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
            used_openrouter=artifacts.used_openrouter,
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
            "Starting analysis mode=%s text_length=%s openrouter_configured=%s openrouter_available=%s",
            mode.value,
            len(text),
            self.openrouter_client.is_configured(),
            self.openrouter_client.is_available(),
        )
        sentence_spans = split_sentences(text)
        normalized = self.normalizer.normalize(text)
        rule_suggestions = self.rule_engine.analyze(text)
        spell_suggestions = self.spell_engine.analyze(normalized.text, personal_dictionary)
        detector_findings = self.detector_service.detect(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
            spell_suggestions=spell_suggestions,
        )
        model_suggestions, used_openrouter = self._openrouter_model_suggestions(
            text=text,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            personal_dictionary=personal_dictionary,
            mode=mode,
        )
        candidates = self.candidate_generator.generate(
            spell_suggestions=spell_suggestions,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            model_suggestions=model_suggestions,
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
            model_suggestions=candidates.model_suggestions,
        )
        ranked_suggestions = self.ranking_pipeline.rank(prepared_suggestions, text=text, mode=mode)
        merged_suggestions = _apply_request_mode(
            self.suggestion_manager.finalize_ranked(ranked_suggestions),
            mode=mode,
        )
        merged_suggestions = enrich_suggestions_with_text_context(text, merged_suggestions)
        detector_runtime = self.detector_service.runtime_status()
        openrouter_runtime = self.openrouter_client.runtime_status()
        analysis_profile = _derive_runtime_profile(detector_runtime.loaded, openrouter_runtime.available)
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
            used_detector=detector_runtime.loaded,
            used_openrouter=used_openrouter,
            runtime_warnings=_build_runtime_warnings(detector_runtime, openrouter_runtime),
            analysis_profile=analysis_profile,
        )

    def _openrouter_model_suggestions(
        self,
        *,
        text: str,
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        personal_dictionary: list[str] | None,
        mode: AnalyzeMode,
    ) -> tuple[list[Suggestion], bool]:
        if not self.openrouter_client.is_available():
            logger.info(
                "Skipping OpenRouter analysis mode=%s openrouter_configured=%s openrouter_available=%s",
                mode.value,
                self.openrouter_client.is_configured(),
                self.openrouter_client.is_available(),
            )
            return [], False

        model_suggestions: list[Suggestion] = []
        suspicious_sentences = self._select_suspicious_sentences(
            text=text,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            mode=mode,
        )
        logger.info(
            "OpenRouter routing mode=%s suspicious_sentences_selected=%s",
            mode.value,
            len(suspicious_sentences),
        )
        if not suspicious_sentences:
            return [], False

        sentences_sent = 0
        issues_returned = 0
        issues_filtered_out = 0
        for sentence in suspicious_sentences:
            sentences_sent += 1
            sentence_hints = self._build_sentence_hints(
                sentence=sentence,
                rule_suggestions=rule_suggestions,
                detector_findings=detector_findings,
            )
            issues = self.openrouter_client.analyze_sentence(
                sentence.text,
                mode.value,
                local_hints=sentence_hints,
            )
            issues_returned += len(issues)
            for issue in issues:
                suggestion = self._validate_openrouter_issue(
                    issue,
                    sentence=sentence,
                    personal_dictionary=personal_dictionary,
                    mode=mode,
                )
                if suggestion is not None:
                    model_suggestions.append(suggestion)
                else:
                    issues_filtered_out += 1
        logger.info(
            "OpenRouter analysis summary mode=%s sentences_sent=%s issues_returned=%s issues_filtered_out=%s suggestions_kept=%s",
            mode.value,
            sentences_sent,
            issues_returned,
            issues_filtered_out,
            len(model_suggestions),
        )
        return model_suggestions, sentences_sent > 0

    def _select_suspicious_sentences(
        self,
        *,
        text: str,
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        mode: AnalyzeMode,
    ) -> list[SentenceSpan]:
        suspicious_sentences: list[SentenceSpan] = []
        eligible_sentences: list[SentenceSpan] = []
        analyze_all_eligible_sentences = mode in {AnalyzeMode.STRICT, AnalyzeMode.FORMAL}
        sentence_limit = (
            STRICT_MODE_OPENROUTER_SENTENCE_LIMIT
            if analyze_all_eligible_sentences
            else MAX_OPENROUTER_SENTENCES_PER_REQUEST
        )
        for sentence in split_sentences(text):
            if not _is_openrouter_eligible_sentence(sentence.text):
                continue
            eligible_sentences.append(sentence)

            overlapping_rules = [
                suggestion
                for suggestion in rule_suggestions
                if _overlaps_span(sentence.start, sentence.end, suggestion.span_start, suggestion.span_end)
                and _is_context_sensitive_rule(suggestion, mode=mode)
            ]
            overlapping_findings = [
                finding
                for finding in detector_findings
                if _overlaps_span(sentence.start, sentence.end, finding.span_start, finding.span_end)
                and finding.category in {SuggestionCategory.GRAMMAR, SuggestionCategory.STYLE, SuggestionCategory.PUNCTUATION}
            ]
            if not analyze_all_eligible_sentences and not overlapping_rules and not overlapping_findings:
                continue

            suspicious_sentences.append(sentence)
            if len(suspicious_sentences) >= sentence_limit:
                break
        if not analyze_all_eligible_sentences and not suspicious_sentences and eligible_sentences:
            suspicious_sentences.append(eligible_sentences[0])
        return suspicious_sentences

    def _build_sentence_hints(
        self,
        *,
        sentence: SentenceSpan,
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
    ) -> list[OpenRouterHint]:
        hints: list[OpenRouterHint] = []
        for suggestion in rule_suggestions:
            if not _overlaps_span(sentence.start, sentence.end, suggestion.span_start, suggestion.span_end):
                continue
            hints.append(
                OpenRouterHint(
                    start=max(0, suggestion.span_start - sentence.start),
                    end=max(0, suggestion.span_end - sentence.start),
                    category=suggestion.category.value,
                    subtype=suggestion.subtype,
                    text=suggestion.original_text,
                )
            )

        for finding in detector_findings:
            if not _overlaps_span(sentence.start, sentence.end, finding.span_start, finding.span_end):
                continue
            hints.append(
                OpenRouterHint(
                    start=max(0, finding.span_start - sentence.start),
                    end=max(0, finding.span_end - sentence.start),
                    category=finding.category.value,
                    subtype=finding.subtype,
                    text=finding.original_text,
                )
            )
        return hints[:6]

    def _validate_openrouter_issue(
        self,
        issue: OpenRouterIssue,
        *,
        sentence: SentenceSpan,
        personal_dictionary: list[str] | None,
        mode: AnalyzeMode,
    ) -> Suggestion | None:
        if issue.confidence < _minimum_openrouter_confidence(issue.category, mode=mode):
            return None
        if not _passes_model_localization_checks(issue, sentence.text, mode=mode):
            return None

        if issue.category == OpenRouterIssueCategory.SPELLING_ERROR:
            if not BANGLA_WORD_PATTERN.fullmatch(issue.original) or not BANGLA_WORD_PATTERN.fullmatch(issue.replacement):
                return None
            if not self.spell_engine.is_safe_spelling_replacement(
                issue.original,
                issue.replacement,
                personal_dictionary=personal_dictionary,
            ):
                return None
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.SPELLING,
                subtype=issue.subtype or "spelling_error",
                severity=SuggestionSeverity.MEDIUM,
            )

        if issue.category == OpenRouterIssueCategory.ORTHOGRAPHY_VARIANT:
            if mode == AnalyzeMode.STANDARD:
                return None
            if not BANGLA_WORD_PATTERN.fullmatch(issue.original) or not BANGLA_WORD_PATTERN.fullmatch(issue.replacement):
                return None
            if not self.spell_engine.is_safe_orthography_variant(
                issue.original,
                issue.replacement,
                personal_dictionary=personal_dictionary,
            ):
                return None
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.STYLE,
                subtype=issue.subtype or "orthography_variant",
                severity=SuggestionSeverity.LOW,
                suggestion_kind=SuggestionKind.ORTHOGRAPHY_VARIANT,
                optional_mode_visibility=[AnalyzeMode.STRICT, AnalyzeMode.FORMAL],
                is_variant_only=True,
            )

        if _looks_user_word_like(issue.original, self.spell_engine, personal_dictionary):
            return None

        if issue.category == OpenRouterIssueCategory.GRAMMAR_ERROR:
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.GRAMMAR,
                subtype=issue.subtype or "llm_grammar_error",
                severity=SuggestionSeverity.MEDIUM,
            )

        if issue.category == OpenRouterIssueCategory.PUNCTUATION_ERROR:
            if not _is_precise_punctuation_edit(issue.original, issue.replacement):
                return None
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.PUNCTUATION,
                subtype=issue.subtype or "punctuation_error",
                severity=SuggestionSeverity.LOW,
            )

        if issue.category == OpenRouterIssueCategory.SPACING_ERROR:
            if not _is_precise_spacing_edit(issue.original, issue.replacement):
                return None
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.PUNCTUATION,
                subtype=issue.subtype or "spacing_error",
                severity=SuggestionSeverity.LOW,
            )

        if mode == AnalyzeMode.STANDARD:
            return None

        return self._build_llm_suggestion(
            issue,
            sentence=sentence,
            category=SuggestionCategory.STYLE,
            subtype=issue.subtype or "style_suggestion",
            severity=SuggestionSeverity.LOW,
            optional_mode_visibility=[AnalyzeMode.STRICT, AnalyzeMode.FORMAL],
        )

    def _build_llm_suggestion(
        self,
        issue: OpenRouterIssue,
        *,
        sentence: SentenceSpan,
        category: SuggestionCategory,
        subtype: str,
        severity: SuggestionSeverity,
        suggestion_kind: SuggestionKind | None = None,
        optional_mode_visibility: list[AnalyzeMode] | None = None,
        is_variant_only: bool = False,
    ) -> Suggestion:
        span_start = sentence.start + issue.start
        span_end = sentence.start + issue.end
        return Suggestion(
            id=stable_id(
                "llm",
                f"{category.value}:{subtype}:{span_start}:{span_end}:{issue.original}:{issue.replacement}",
            ),
            rule_id=_llm_rule_id(subtype),
            category=category,
            subtype=subtype,
            span_start=span_start,
            span_end=span_end,
            original_text=issue.original,
            replacement_options=[issue.replacement],
            confidence=round(issue.confidence, 2),
            explanation_bn=issue.reason_bn,
            explanation_en="Backend-validated OpenRouter suggestion.",
            source=SuggestionSource.MODEL,
            severity=severity,
            suggestion_kind=suggestion_kind,
            is_contextual=True,
            optional_mode_visibility=optional_mode_visibility or [],
            is_variant_only=is_variant_only,
            sentence_index=sentence.sentence_index,
            sentence_start=sentence.start,
            sentence_end=sentence.end,
            occurrence_index=issue.occurrence_index,
            anchor_before=issue.anchor_before,
            anchor_after=issue.anchor_after,
            source_trace=(issue.source_trace or []) + ([issue.reasoning_key] if issue.reasoning_key else []),
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

    hard_suggestions = [suggestion for suggestion in gated_suggestions if suggestion.category != SuggestionCategory.STYLE]
    style_suggestions = [suggestion for suggestion in gated_suggestions if suggestion.category == SuggestionCategory.STYLE]

    if mode == AnalyzeMode.FORMAL:
        style_suggestions = sorted(style_suggestions, key=_formal_style_sort_key)

    return [*hard_suggestions, *style_suggestions]


def build_corrected_text(text: str, suggestions: list[Suggestion]) -> str:
    safe_suggestions = sorted(
        (
            suggestion
            for suggestion in suggestions
            if _is_safe_auto_apply_suggestion(text, suggestion)
        ),
        key=lambda suggestion: (
            suggestion.span_start,
            -suggestion.confidence,
            suggestion.span_end,
            suggestion.rule_id,
        ),
    )
    if not safe_suggestions:
        return text

    parts: list[str] = []
    cursor = 0
    for suggestion in safe_suggestions:
        if suggestion.span_start < cursor:
            continue

        replacement = suggestion.replacement_options[0]
        parts.append(text[cursor:suggestion.span_start])
        parts.append(replacement)
        cursor = suggestion.span_end

    parts.append(text[cursor:])
    corrected_text = "".join(parts)
    return corrected_text if corrected_text else text


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
    base_thresholds = {
        AnalyzeMode.STANDARD: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.94,
            SuggestionKind.GRAMMAR_ERROR: 0.82,
            SuggestionKind.PUNCTUATION_ERROR: 0.84,
            SuggestionKind.SPACING_ERROR: 0.84,
            SuggestionKind.STYLE_SUGGESTION: 0.9,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.95,
        },
        AnalyzeMode.STRICT: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.92,
            SuggestionKind.GRAMMAR_ERROR: 0.78,
            SuggestionKind.PUNCTUATION_ERROR: 0.82,
            SuggestionKind.SPACING_ERROR: 0.82,
            SuggestionKind.STYLE_SUGGESTION: 0.82,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.82,
        },
        AnalyzeMode.FORMAL: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.92,
            SuggestionKind.GRAMMAR_ERROR: 0.78,
            SuggestionKind.PUNCTUATION_ERROR: 0.82,
            SuggestionKind.SPACING_ERROR: 0.82,
            SuggestionKind.STYLE_SUGGESTION: 0.78,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.8,
        },
    }

    threshold = base_thresholds[mode].get(suggestion.suggestion_kind, 0.95)
    if suggestion.source == SuggestionSource.HYBRID:
        threshold -= 0.02
    if _is_high_precision_style_suggestion(suggestion):
        threshold -= {
            AnalyzeMode.STANDARD: 0.06,
            AnalyzeMode.STRICT: 0.04,
            AnalyzeMode.FORMAL: 0.02,
        }[mode]
    if suggestion.rule_id.startswith("LLM_") and suggestion.suggestion_kind in {
        SuggestionKind.STYLE_SUGGESTION,
        SuggestionKind.ORTHOGRAPHY_VARIANT,
    }:
        threshold += 0.02 if mode == AnalyzeMode.STANDARD else 0.0
    if not suggestion.replacement_options:
        threshold += 0.08 if mode == AnalyzeMode.STANDARD else 0.03
    if suggestion.is_variant_only and mode == AnalyzeMode.STANDARD:
        threshold += 0.03
    if suggestion.severity == SuggestionSeverity.HIGH:
        threshold -= 0.03
    if suggestion.rule_id.startswith("LLM_") and _is_rewrite_like_suggestion(suggestion, sentence=suggestion.original_text):
        threshold += 0.18
    if suggestion.rule_id.startswith("LLM_") and _looks_generic_explanation(suggestion.explanation_bn, suggestion):
        threshold += 0.08
    if suggestion.rule_id.startswith("LLM_") and suggestion.source_trace and "anchor_nearest_safe" in suggestion.source_trace:
        threshold += 0.04
    return suggestion.confidence >= threshold


def _is_safe_auto_apply_suggestion(text: str, suggestion: Suggestion) -> bool:
    if suggestion.category == SuggestionCategory.STYLE:
        return False
    if suggestion.rule_id.startswith("DET_"):
        return False
    if suggestion.rule_id.startswith("LLM_"):
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

    if suggestion.suggestion_kind == SuggestionKind.TRUE_SPELLING_ERROR:
        return (
            BANGLA_WORD_PATTERN.fullmatch(original_text.strip()) is not None
            and BANGLA_WORD_PATTERN.fullmatch(replacement.strip()) is not None
        )
    if suggestion.suggestion_kind == SuggestionKind.PUNCTUATION_ERROR:
        return _is_precise_punctuation_edit(original_text, replacement)
    if suggestion.suggestion_kind == SuggestionKind.SPACING_ERROR:
        return _is_precise_spacing_edit(original_text, replacement)
    if suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR:
        return _is_precise_local_edit(original_text, replacement, text)
    return False


def _auto_apply_confidence_threshold(suggestion: Suggestion) -> float:
    thresholds = {
        SuggestionSource.RULE: 0.0,
        SuggestionSource.SPELL: 0.97,
        SuggestionSource.HYBRID: 0.97,
        SuggestionSource.MODEL: 0.98,
    }
    threshold = thresholds[suggestion.source]
    if suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR:
        if suggestion.source == SuggestionSource.MODEL:
            return 1.01
        if suggestion.source == SuggestionSource.HYBRID:
            threshold = max(threshold, 0.98)
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
def _is_openrouter_eligible_sentence(sentence: str) -> bool:
    stripped_sentence = sentence.strip()
    if not stripped_sentence or len(stripped_sentence) > MAX_OPENROUTER_SENTENCE_LENGTH:
        return False
    bangla_letter_count = sum(1 for character in stripped_sentence if BANGLA_LETTER_PATTERN.search(character))
    return bangla_letter_count >= MIN_OPENROUTER_BANGLA_LETTERS


def _is_context_sensitive_rule(suggestion: Suggestion, *, mode: AnalyzeMode) -> bool:
    if suggestion.category == SuggestionCategory.GRAMMAR:
        return suggestion.confidence >= 0.62
    if suggestion.category == SuggestionCategory.PUNCTUATION:
        return suggestion.confidence >= 0.84 and bool(suggestion.replacement_options)
    if suggestion.suggestion_kind == SuggestionKind.SPACING_ERROR:
        return suggestion.confidence >= 0.84 and bool(suggestion.replacement_options)
    if suggestion.category == SuggestionCategory.STYLE:
        if suggestion.subtype in {"number_unit_spacing", "mixed_digit_style"}:
            return suggestion.confidence >= 0.7 and bool(suggestion.replacement_options)
        if mode == AnalyzeMode.FORMAL:
            return suggestion.confidence >= 0.7 and bool(suggestion.replacement_options)
    return False


def _minimum_openrouter_confidence(category: OpenRouterIssueCategory, *, mode: AnalyzeMode) -> float:
    thresholds = {
        AnalyzeMode.STANDARD: {
            OpenRouterIssueCategory.GRAMMAR_ERROR: 0.82,
            OpenRouterIssueCategory.SPELLING_ERROR: 0.94,
            OpenRouterIssueCategory.PUNCTUATION_ERROR: 0.84,
            OpenRouterIssueCategory.SPACING_ERROR: 0.84,
            OpenRouterIssueCategory.ORTHOGRAPHY_VARIANT: 0.95,
            OpenRouterIssueCategory.STYLE_SUGGESTION: 0.9,
        },
        AnalyzeMode.STRICT: {
            OpenRouterIssueCategory.GRAMMAR_ERROR: 0.78,
            OpenRouterIssueCategory.SPELLING_ERROR: 0.92,
            OpenRouterIssueCategory.PUNCTUATION_ERROR: 0.82,
            OpenRouterIssueCategory.SPACING_ERROR: 0.82,
            OpenRouterIssueCategory.ORTHOGRAPHY_VARIANT: 0.82,
            OpenRouterIssueCategory.STYLE_SUGGESTION: 0.82,
        },
        AnalyzeMode.FORMAL: {
            OpenRouterIssueCategory.GRAMMAR_ERROR: 0.78,
            OpenRouterIssueCategory.SPELLING_ERROR: 0.92,
            OpenRouterIssueCategory.PUNCTUATION_ERROR: 0.82,
            OpenRouterIssueCategory.SPACING_ERROR: 0.82,
            OpenRouterIssueCategory.ORTHOGRAPHY_VARIANT: 0.8,
            OpenRouterIssueCategory.STYLE_SUGGESTION: 0.78,
        },
    }
    return thresholds[mode][category]


def _passes_model_localization_checks(issue: OpenRouterIssue, sentence: str, *, mode: AnalyzeMode) -> bool:
    if issue.source_trace and "anchor_nearest_safe" in issue.source_trace and issue.confidence < 0.94:
        return False
    if not issue.source_trace:
        return False
    if issue.occurrence_index is None and not issue.anchor_before and not issue.anchor_after and "exact_unique_match" not in issue.source_trace:
        return False
    if _looks_generic_explanation(issue.reason_bn, issue):
        return False
    if not _is_precise_local_edit(issue.original, issue.replacement, sentence, mode=mode):
        return False
    return True


def _is_precise_local_edit(original: str, replacement: str, sentence: str, *, mode: AnalyzeMode = AnalyzeMode.STANDARD) -> bool:
    normalized_original = original.strip()
    normalized_replacement = replacement.strip()
    if not normalized_original or not normalized_replacement:
        return False
    if normalized_original == normalized_replacement:
        return False
    if normalized_replacement == sentence.strip() and normalized_original != sentence.strip():
        return False
    if _is_rewrite_like_replacement(normalized_original, normalized_replacement, sentence, mode=mode):
        return False
    return True


def _is_rewrite_like_replacement(original: str, replacement: str, sentence: str, *, mode: AnalyzeMode) -> bool:
    if not original or not replacement:
        return True
    sentence_tokens = max(len(sentence.split()), 1)
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
    if len(replacement) >= max(len(sentence.strip()) * 0.4, len(original) + 12) and len(sentence.strip()) > len(original):
        return True
    if replacement_tokens >= max(sentence_tokens - 1, 1) and replacement != original:
        return True
    return False


def _looks_generic_explanation(explanation: str, issue_or_suggestion: OpenRouterIssue | Suggestion) -> bool:
    normalized = " ".join(explanation.split()).strip()
    if not normalized:
        return True
    original = issue_or_suggestion.original if isinstance(issue_or_suggestion, OpenRouterIssue) else issue_or_suggestion.original_text
    replacement = (
        issue_or_suggestion.replacement
        if isinstance(issue_or_suggestion, OpenRouterIssue)
        else (issue_or_suggestion.replacement_options[0] if issue_or_suggestion.replacement_options else "")
    )
    generic_markers = {
        "আরও স্বাভাবিক",
        "আরও উপযুক্ত",
        "আরও ভালো",
        "স্পষ্টতর",
        "clearer",
        "more natural",
        "better here",
    }
    if len(normalized.split()) <= 3:
        return True
    if not any(token in normalized for token in {original, replacement} if token):
        return any(marker in normalized for marker in generic_markers)
    return False


def _is_rewrite_like_suggestion(suggestion: Suggestion, *, sentence: str) -> bool:
    if not suggestion.replacement_options:
        return True
    comparison_sentence = sentence.strip()
    if comparison_sentence == suggestion.original_text.strip() and (suggestion.anchor_before or suggestion.anchor_after):
        comparison_sentence = f"{suggestion.anchor_before or ''}{suggestion.original_text}{suggestion.anchor_after or ''}".strip()
    if not comparison_sentence or comparison_sentence == suggestion.original_text.strip():
        return _is_rewrite_like_local_replacement(
            suggestion.original_text.strip(),
            suggestion.replacement_options[0].strip(),
            mode=AnalyzeMode.STANDARD,
        )
    return _is_rewrite_like_replacement(
        suggestion.original_text.strip(),
        suggestion.replacement_options[0].strip(),
        comparison_sentence,
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


def _looks_user_word_like(original: str, spell_engine: SpellEngine, personal_dictionary: list[str] | None) -> bool:
    if " " in original.strip():
        return False
    if not BANGLA_WORD_PATTERN.fullmatch(original):
        return spell_engine.looks_code_mixed_token(original)
    return spell_engine.is_probable_named_entity_or_user_word(
        original,
        personal_dictionary=personal_dictionary,
    )


def _overlaps_span(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return left_start < right_end and right_start < left_end


def _build_runtime_warnings(detector_runtime, openrouter_runtime) -> list[str]:  # type: ignore[no-untyped-def]
    warnings: list[str] = []
    if detector_runtime.status != "ready":
        warnings.append(f"detector_{detector_runtime.status}")
    if openrouter_runtime.status != "ready":
        warnings.append(f"openrouter_{openrouter_runtime.status}")
    return warnings


def _derive_runtime_profile(detector_ready: bool, openrouter_ready: bool) -> AnalysisProfile:
    if detector_ready and openrouter_ready:
        return AnalysisProfile.FULL_BACKEND
    if detector_ready:
        return AnalysisProfile.BACKEND_WITHOUT_OPENROUTER
    if openrouter_ready:
        return AnalysisProfile.BACKEND_WITHOUT_DETECTOR
    return AnalysisProfile.BACKEND_RULES_AND_SPELL_ONLY


def _llm_rule_id(subtype: str) -> str:
    mapping = {
        "spelling_error": "LLM_SPELL_001",
        "orthography_variant": "LLM_VARIANT_001",
        "punctuation_error": "LLM_PUNCT_001",
        "spacing_error": "LLM_SPACE_001",
        "style_suggestion": "LLM_STYLE_001",
    }
    return mapping.get(subtype, "LLM_GRAMMAR_001")
