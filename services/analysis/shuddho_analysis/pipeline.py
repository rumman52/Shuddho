from __future__ import annotations

import re
from dataclasses import dataclass

from services.llm.shuddho_llm.client import GeminiClient, GeminiHint
from services.llm.shuddho_llm.parsing import GeminiIssue, GeminiIssueCategory
from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager
from shared.constants.bangla import BANGLA_LETTER_PATTERN, BANGLA_WORD_PATTERN
from shared.schemas.python_models import (
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


SENTENCE_PATTERN = re.compile(r"[^.!?\u0964\n]+(?:[.!?\u0964]+|$)")
MAX_GEMINI_SENTENCES_PER_REQUEST = 3
MAX_GEMINI_SENTENCE_LENGTH = 280
MIN_GEMINI_BANGLA_LETTERS = 4


@dataclass(frozen=True)
class SentenceSpan:
    start: int
    end: int
    text: str


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
        gemini_client: GeminiClient | None = None,
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
        self.gemini_client = gemini_client or GeminiClient.disabled()

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
            suggestions=artifacts.merged_suggestions,
        )

    def analyze_artifacts(
        self,
        text: str,
        personal_dictionary: list[str] | None = None,
        *,
        mode: AnalyzeMode = AnalyzeMode.STANDARD,
    ) -> AnalysisArtifacts:
        normalized = self.normalizer.normalize(text)
        rule_suggestions = self.rule_engine.analyze(text)
        spell_suggestions = self.spell_engine.analyze(normalized.text, personal_dictionary)
        detector_findings = self.detector_service.detect(
            text=text,
            normalized=normalized,
            rule_suggestions=rule_suggestions,
            spell_suggestions=spell_suggestions,
        )
        model_suggestions = self._gemini_model_suggestions(
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
        )

    def _gemini_model_suggestions(
        self,
        *,
        text: str,
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        personal_dictionary: list[str] | None,
        mode: AnalyzeMode,
    ) -> list[Suggestion]:
        if not self.gemini_client.is_available():
            return []

        model_suggestions: list[Suggestion] = []
        suspicious_sentences = self._select_suspicious_sentences(
            text=text,
            rule_suggestions=rule_suggestions,
            detector_findings=detector_findings,
            mode=mode,
        )
        for sentence in suspicious_sentences:
            sentence_hints = self._build_sentence_hints(
                sentence=sentence,
                rule_suggestions=rule_suggestions,
                detector_findings=detector_findings,
            )
            issues = self.gemini_client.analyze_sentence(
                sentence.text,
                mode.value,
                local_hints=sentence_hints,
            )
            for issue in issues:
                suggestion = self._validate_gemini_issue(
                    issue,
                    sentence=sentence,
                    full_text=text,
                    personal_dictionary=personal_dictionary,
                    mode=mode,
                )
                if suggestion is not None:
                    model_suggestions.append(suggestion)
        return model_suggestions

    def _select_suspicious_sentences(
        self,
        *,
        text: str,
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        mode: AnalyzeMode,
    ) -> list[SentenceSpan]:
        suspicious_sentences: list[SentenceSpan] = []
        for sentence in _split_sentences(text):
            if not _is_gemini_eligible_sentence(sentence.text):
                continue

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
            if not overlapping_rules and not overlapping_findings:
                continue

            suspicious_sentences.append(sentence)
            if len(suspicious_sentences) >= MAX_GEMINI_SENTENCES_PER_REQUEST:
                break
        return suspicious_sentences

    def _build_sentence_hints(
        self,
        *,
        sentence: SentenceSpan,
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
    ) -> list[GeminiHint]:
        hints: list[GeminiHint] = []
        for suggestion in rule_suggestions:
            if not _overlaps_span(sentence.start, sentence.end, suggestion.span_start, suggestion.span_end):
                continue
            hints.append(
                GeminiHint(
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
                GeminiHint(
                    start=max(0, finding.span_start - sentence.start),
                    end=max(0, finding.span_end - sentence.start),
                    category=finding.category.value,
                    subtype=finding.subtype,
                    text=finding.original_text,
                )
            )
        return hints[:6]

    def _validate_gemini_issue(
        self,
        issue: GeminiIssue,
        *,
        sentence: SentenceSpan,
        full_text: str,
        personal_dictionary: list[str] | None,
        mode: AnalyzeMode,
    ) -> Suggestion | None:
        if issue.confidence < _minimum_gemini_confidence(issue.category, mode=mode):
            return None
        if not _is_precise_local_edit(issue.original, issue.replacement, sentence.text):
            return None

        if issue.category == GeminiIssueCategory.SPELLING_ERROR:
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
                subtype="spelling_error",
                severity=SuggestionSeverity.MEDIUM,
            )

        if issue.category == GeminiIssueCategory.ORTHOGRAPHY_VARIANT:
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
                subtype="orthography_variant",
                severity=SuggestionSeverity.LOW,
                suggestion_kind=SuggestionKind.ORTHOGRAPHY_VARIANT,
                optional_mode_visibility=[AnalyzeMode.STRICT, AnalyzeMode.FORMAL],
                is_variant_only=True,
            )

        if _looks_user_word_like(issue.original, self.spell_engine, personal_dictionary):
            return None

        if issue.category == GeminiIssueCategory.GRAMMAR_ERROR:
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.GRAMMAR,
                subtype="llm_grammar_error",
                severity=SuggestionSeverity.MEDIUM,
            )

        if issue.category == GeminiIssueCategory.PUNCTUATION_ERROR:
            if not _is_precise_punctuation_edit(issue.original, issue.replacement):
                return None
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.PUNCTUATION,
                subtype="punctuation_error",
                severity=SuggestionSeverity.LOW,
            )

        if issue.category == GeminiIssueCategory.SPACING_ERROR:
            if not _is_precise_spacing_edit(issue.original, issue.replacement):
                return None
            return self._build_llm_suggestion(
                issue,
                sentence=sentence,
                category=SuggestionCategory.PUNCTUATION,
                subtype="spacing_error",
                severity=SuggestionSeverity.LOW,
            )

        if mode == AnalyzeMode.STANDARD:
            return None

        return self._build_llm_suggestion(
            issue,
            sentence=sentence,
            category=SuggestionCategory.STYLE,
            subtype="style_suggestion",
            severity=SuggestionSeverity.LOW,
            optional_mode_visibility=[AnalyzeMode.STRICT, AnalyzeMode.FORMAL],
        )

    def _build_llm_suggestion(
        self,
        issue: GeminiIssue,
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
        replacement_options = [issue.replacement]
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
            replacement_options=replacement_options,
            confidence=round(issue.confidence, 2),
            explanation_bn=issue.reason_bn,
            explanation_en="Backend-validated Gemini suggestion.",
            source=SuggestionSource.MODEL,
            severity=severity,
            suggestion_kind=suggestion_kind,
            is_contextual=True,
            optional_mode_visibility=optional_mode_visibility or [],
            is_variant_only=is_variant_only,
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
            SuggestionKind.TRUE_SPELLING_ERROR: 0.96,
            SuggestionKind.GRAMMAR_ERROR: 0.9,
            SuggestionKind.PUNCTUATION_ERROR: 0.9,
            SuggestionKind.SPACING_ERROR: 0.9,
            SuggestionKind.STYLE_SUGGESTION: 0.9,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.99,
        },
        AnalyzeMode.STRICT: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.92,
            SuggestionKind.GRAMMAR_ERROR: 0.82,
            SuggestionKind.PUNCTUATION_ERROR: 0.84,
            SuggestionKind.SPACING_ERROR: 0.84,
            SuggestionKind.STYLE_SUGGESTION: 0.82,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.82,
        },
        AnalyzeMode.FORMAL: {
            SuggestionKind.TRUE_SPELLING_ERROR: 0.92,
            SuggestionKind.GRAMMAR_ERROR: 0.82,
            SuggestionKind.PUNCTUATION_ERROR: 0.84,
            SuggestionKind.SPACING_ERROR: 0.84,
            SuggestionKind.STYLE_SUGGESTION: 0.76,
            SuggestionKind.ORTHOGRAPHY_VARIANT: 0.8,
        },
    }

    threshold = base_thresholds[mode].get(suggestion.suggestion_kind, 0.95)
    if suggestion.source == SuggestionSource.MODEL:
        threshold += 0.04
    if suggestion.source == SuggestionSource.HYBRID:
        threshold -= 0.02
    if _is_high_precision_style_suggestion(suggestion):
        threshold -= {
            AnalyzeMode.STANDARD: 0.06,
            AnalyzeMode.STRICT: 0.04,
            AnalyzeMode.FORMAL: 0.02,
        }[mode]
    if suggestion.rule_id.startswith("LLM_") and suggestion.suggestion_kind in {
        SuggestionKind.GRAMMAR_ERROR,
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
    return suggestion.confidence >= threshold


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


def _split_sentences(text: str) -> list[SentenceSpan]:
    sentences: list[SentenceSpan] = []
    for match in SENTENCE_PATTERN.finditer(text):
        raw_start = match.start()
        raw_end = match.end()
        while raw_start < raw_end and text[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and text[raw_end - 1].isspace():
            raw_end -= 1
        if raw_end <= raw_start:
            continue
        sentences.append(SentenceSpan(start=raw_start, end=raw_end, text=text[raw_start:raw_end]))
    return sentences


def _is_gemini_eligible_sentence(sentence: str) -> bool:
    stripped_sentence = sentence.strip()
    if not stripped_sentence or len(stripped_sentence) > MAX_GEMINI_SENTENCE_LENGTH:
        return False
    bangla_letter_count = sum(1 for character in stripped_sentence if BANGLA_LETTER_PATTERN.search(character))
    return bangla_letter_count >= MIN_GEMINI_BANGLA_LETTERS


def _is_context_sensitive_rule(suggestion: Suggestion, *, mode: AnalyzeMode) -> bool:
    if suggestion.category == SuggestionCategory.GRAMMAR:
        return True
    if mode == AnalyzeMode.FORMAL and suggestion.category == SuggestionCategory.STYLE:
        return suggestion.confidence >= 0.7 and bool(suggestion.replacement_options)
    return False


def _minimum_gemini_confidence(category: GeminiIssueCategory, *, mode: AnalyzeMode) -> float:
    thresholds = {
        AnalyzeMode.STANDARD: {
            GeminiIssueCategory.GRAMMAR_ERROR: 0.92,
            GeminiIssueCategory.SPELLING_ERROR: 0.96,
            GeminiIssueCategory.PUNCTUATION_ERROR: 0.9,
            GeminiIssueCategory.SPACING_ERROR: 0.9,
            GeminiIssueCategory.ORTHOGRAPHY_VARIANT: 0.98,
            GeminiIssueCategory.STYLE_SUGGESTION: 0.9,
        },
        AnalyzeMode.STRICT: {
            GeminiIssueCategory.GRAMMAR_ERROR: 0.86,
            GeminiIssueCategory.SPELLING_ERROR: 0.94,
            GeminiIssueCategory.PUNCTUATION_ERROR: 0.86,
            GeminiIssueCategory.SPACING_ERROR: 0.86,
            GeminiIssueCategory.ORTHOGRAPHY_VARIANT: 0.86,
            GeminiIssueCategory.STYLE_SUGGESTION: 0.84,
        },
        AnalyzeMode.FORMAL: {
            GeminiIssueCategory.GRAMMAR_ERROR: 0.84,
            GeminiIssueCategory.SPELLING_ERROR: 0.94,
            GeminiIssueCategory.PUNCTUATION_ERROR: 0.84,
            GeminiIssueCategory.SPACING_ERROR: 0.84,
            GeminiIssueCategory.ORTHOGRAPHY_VARIANT: 0.84,
            GeminiIssueCategory.STYLE_SUGGESTION: 0.82,
        },
    }
    return thresholds[mode][category]


def _is_precise_local_edit(original: str, replacement: str, sentence: str) -> bool:
    normalized_original = original.strip()
    normalized_replacement = replacement.strip()
    if not normalized_original or not normalized_replacement:
        return False
    if normalized_original == normalized_replacement:
        return False
    if normalized_replacement == sentence.strip() and normalized_original != sentence.strip():
        return False
    if len(normalized_replacement) > max(len(normalized_original) * 3, 48):
        return False
    if len(normalized_replacement.split()) > max(len(normalized_original.split()) + 3, 6):
        return False
    return True


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


def _llm_rule_id(subtype: str) -> str:
    mapping = {
        "spelling_error": "LLM_SPELL_001",
        "orthography_variant": "LLM_VARIANT_001",
        "punctuation_error": "LLM_PUNCT_001",
        "spacing_error": "LLM_SPACE_001",
        "style_suggestion": "LLM_STYLE_001",
    }
    return mapping.get(subtype, "LLM_GRAMMAR_001")
