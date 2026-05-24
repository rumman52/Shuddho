from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SuggestionCategory(str, Enum):
    SPELLING = "spelling"
    GRAMMAR = "grammar"
    PUNCTUATION = "punctuation"
    SPACING = "spacing"
    REGISTER = "register"
    CLARITY = "clarity"
    STYLE = "style"
    REWRITE_ONLY = "rewrite_only"


class SuggestionSource(str, Enum):
    RULE = "rule"
    SPELL = "spell"
    MODEL = "model"
    HYBRID = "hybrid"


class SuggestionSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalyzeMode(str, Enum):
    STANDARD = "standard"
    STRICT = "strict"
    FORMAL = "formal"


class AnalysisProfile(str, Enum):
    FULL_LOCAL = "full_local"
    BACKEND_WITHOUT_DETECTOR = "backend_without_detector"
    BACKEND_WITHOUT_CORRECTOR = "backend_without_corrector"
    BACKEND_RULES_AND_SPELL_ONLY = "backend_rules_and_spell_only"
    FRONTEND_LOCAL_FALLBACK = "frontend_local_fallback"


class SuggestionKind(str, Enum):
    TRUE_SPELLING_ERROR = "true_spelling_error"
    ORTHOGRAPHY_VARIANT = "orthography_variant"
    STYLE_SUGGESTION = "style_suggestion"
    GRAMMAR_ERROR = "grammar_error"
    PUNCTUATION_ERROR = "punctuation_error"
    SPACING_ERROR = "spacing_error"
    NAMED_ENTITY_OR_USER_WORD = "named_entity_or_user_word"
    NO_SUGGESTION = "no_suggestion"


class SuggestionUiGroup(str, Enum):
    CORRECTNESS = "correctness"
    SPACING = "spacing"
    PUNCTUATION = "punctuation"
    REGISTER = "register"
    CLARITY = "clarity"


class PreferredLanguageVariant(str, Enum):
    BANGLA = "bangla"


class WritingGoal(str, Enum):
    GENERAL = "general"
    FORMAL = "formal"
    ACADEMIC = "academic"
    BUSINESS = "business"
    CASUAL = "casual"
    SOCIAL = "social"


class ToneGoal(str, Enum):
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    CONCISE = "concise"
    CONFIDENT = "confident"


class SuggestionDensity(str, Enum):
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"


class RewriteIntent(str, Enum):
    CLARITY = "clarity"
    FORMAL = "formal"
    CONCISE = "concise"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"


class ToneLabel(str, Enum):
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    CONFIDENT = "confident"
    RESPECTFUL = "respectful"
    URGENT = "urgent"
    UNCLEAR = "unclear"


class SuggestionAlternative(BaseModel):
    id: str
    rule_id: str
    category: SuggestionCategory
    subtype: str
    original_text: str
    replacement_options: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    explanation_bn: str
    explanation_en: str
    source: SuggestionSource
    severity: SuggestionSeverity
    feedback_key: str | None = None
    suggestion_kind: SuggestionKind | None = None
    suppression_key: str | None = None
    is_variant_only: bool = False
    source_trace: list[str] | None = None

    @field_validator("replacement_options")
    @classmethod
    def normalize_replacement_options(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value, preserve_single_space=True)

    @field_validator("source_trace")
    @classmethod
    def normalize_source_trace(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = _normalize_unique_strings(value)
        return normalized or None

    @model_validator(mode="after")
    def populate_precision_metadata(self) -> "SuggestionAlternative":
        suggestion_kind = self.suggestion_kind or _infer_suggestion_kind(
            category=self.category,
            subtype=self.subtype,
            is_variant_only=self.is_variant_only,
        )
        self.suggestion_kind = suggestion_kind
        self.is_variant_only = self.is_variant_only or suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT

        if self.feedback_key is None:
            self.feedback_key = _build_feedback_key(
                category=self.category.value,
                original_text=self.original_text,
                replacement_options=self.replacement_options,
            )

        if self.suppression_key is None:
            self.suppression_key = _build_suppression_key(
                rule_id=self.rule_id,
                subtype=self.subtype,
                original_text=self.original_text,
                replacement_options=self.replacement_options,
            )

        return self


class Suggestion(BaseModel):
    id: str
    rule_id: str
    category: SuggestionCategory
    subtype: str
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=0)
    original_text: str
    replacement_options: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    explanation_bn: str
    explanation_en: str
    source: SuggestionSource
    severity: SuggestionSeverity
    feedback_key: str | None = None
    suggestion_kind: SuggestionKind | None = None
    is_contextual: bool | None = None
    optional_mode_visibility: list[AnalyzeMode] = Field(default_factory=list)
    suppression_key: str | None = None
    is_variant_only: bool = False
    sentence_index: int | None = None
    sentence_start: int | None = Field(default=None, ge=0)
    sentence_end: int | None = Field(default=None, ge=0)
    occurrence_index: int | None = Field(default=None, ge=0)
    anchor_before: str | None = None
    anchor_after: str | None = None
    source_trace: list[str] | None = None
    conflict_group_id: str | None = None
    is_primary: bool = True
    primary_reason: str | None = None
    alternatives: list[SuggestionAlternative] = Field(default_factory=list)
    short_title: str | None = None
    ui_group: SuggestionUiGroup | None = None
    can_auto_apply: bool | None = None
    learnable: bool | None = None
    ranking_score: float | None = None
    suggestion_reason_short_bn: str | None = None
    suggestion_reason_short_en: str | None = None
    action_hints: list[str] = Field(default_factory=list)
    rewrite_intents: list[RewriteIntent] = Field(default_factory=list)
    tone_labels: list[ToneLabel] = Field(default_factory=list)

    @field_validator("replacement_options")
    @classmethod
    def normalize_replacement_options(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value, preserve_single_space=True)

    @field_validator("optional_mode_visibility")
    @classmethod
    def normalize_optional_mode_visibility(cls, value: list[AnalyzeMode]) -> list[AnalyzeMode]:
        return _normalize_unique_enums(value)

    @field_validator("source_trace")
    @classmethod
    def normalize_source_trace(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = _normalize_unique_strings(value)
        return normalized or None

    @field_validator("action_hints")
    @classmethod
    def normalize_action_hints(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)

    @field_validator("rewrite_intents")
    @classmethod
    def normalize_rewrite_intents(cls, value: list[RewriteIntent]) -> list[RewriteIntent]:
        return _normalize_unique_enums(value)

    @field_validator("tone_labels")
    @classmethod
    def normalize_tone_labels(cls, value: list[ToneLabel]) -> list[ToneLabel]:
        return _normalize_unique_enums(value)

    @model_validator(mode="after")
    def populate_precision_metadata(self) -> "Suggestion":
        suggestion_kind = self.suggestion_kind or _infer_suggestion_kind(
            category=self.category,
            subtype=self.subtype,
            is_variant_only=self.is_variant_only,
        )
        self.suggestion_kind = suggestion_kind
        self.is_variant_only = self.is_variant_only or suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT

        if self.is_contextual is None:
            self.is_contextual = _infer_is_contextual(self)

        if not self.optional_mode_visibility:
            self.optional_mode_visibility = _default_optional_mode_visibility(suggestion_kind)

        if self.feedback_key is None:
            self.feedback_key = _build_feedback_key(
                category=self.category.value,
                original_text=self.original_text,
                replacement_options=self.replacement_options,
            )

        if self.suppression_key is None:
            self.suppression_key = _build_suppression_key(
                rule_id=self.rule_id,
                subtype=self.subtype,
                original_text=self.original_text,
                replacement_options=self.replacement_options,
            )

        return self


class AnalyzeRequest(BaseModel):
    text: str
    personal_dictionary: list[str] = Field(default_factory=list)
    mode: AnalyzeMode = AnalyzeMode.STANDARD
    user_id: str | None = None

    @field_validator("personal_dictionary")
    @classmethod
    def normalize_personal_dictionary(cls, value: list[str]) -> list[str]:
        return _normalize_unique_entries(value)


class AnalyzeResponse(BaseModel):
    text: str
    normalized_text: str
    corrected_text: str
    suggestions: list[Suggestion]
    analysis_profile: AnalysisProfile = AnalysisProfile.BACKEND_RULES_AND_SPELL_ONLY
    runtime_source: AnalysisProfile = AnalysisProfile.BACKEND_RULES_AND_SPELL_ONLY
    runtime_warnings: list[str] = Field(default_factory=list)
    used_detector: bool = False
    used_corrector: bool = False
    backend_warning: str | None = None
    lexicon_source: str = "unknown"
    lexicon_version: str | None = None
    backend_version: str | None = None
    sentence_count: int = Field(default=0, ge=0)
    request_mode_applied: AnalyzeMode = AnalyzeMode.STANDARD


class UserPreferences(BaseModel):
    user_id: str
    preferred_language_variant: PreferredLanguageVariant = PreferredLanguageVariant.BANGLA
    writing_goal: WritingGoal = WritingGoal.GENERAL
    tone_goal: ToneGoal = ToneGoal.NEUTRAL
    suggestion_density: SuggestionDensity = SuggestionDensity.BALANCED
    auto_show_tone: bool = True
    enable_rewrites: bool = True
    personal_dictionary: list[str] = Field(default_factory=list)
    suppressed_rule_keys: list[str] = Field(default_factory=list)
    disabled_sites: list[str] = Field(default_factory=list)

    @field_validator("personal_dictionary")
    @classmethod
    def normalize_personal_dictionary(cls, value: list[str]) -> list[str]:
        return _normalize_unique_entries(value)

    @field_validator("suppressed_rule_keys", "disabled_sites")
    @classmethod
    def normalize_string_lists(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class RewriteRequest(BaseModel):
    text: str
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    intent: RewriteIntent
    user_id: str | None = None
    writing_goal: WritingGoal | None = None
    tone_goal: ToneGoal | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "RewriteRequest":
        if self.selection_start is None and self.selection_end is None:
            return self
        if self.selection_start is None or self.selection_end is None:
            raise ValueError("selection_start and selection_end must be provided together")
        if self.selection_end < self.selection_start:
            raise ValueError("selection_end must be greater than or equal to selection_start")
        return self


class RewriteOption(BaseModel):
    id: str
    label: str
    rewritten_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation_bn: str
    explanation_en: str
    source: str


class RewriteResponse(BaseModel):
    original_text: str
    target_text: str
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    intent: RewriteIntent
    options: list[RewriteOption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ToneAnalysisRequest(BaseModel):
    text: str
    user_id: str | None = None


class ToneAnalysisResponse(BaseModel):
    detected_tones: list[ToneLabel] = Field(default_factory=list)
    primary_tone: ToneLabel | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    explanation_bn: str
    explanation_en: str
    suggestions: list[str] = Field(default_factory=list)

    @field_validator("detected_tones")
    @classmethod
    def normalize_detected_tones(cls, value: list[ToneLabel]) -> list[ToneLabel]:
        return _normalize_unique_enums(value)

    @field_validator("suggestions")
    @classmethod
    def normalize_suggestions(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class FeedbackAction(str, Enum):
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    SUPPRESSED = "suppressed"
    IGNORE_FOREVER = "ignore_forever"
    ADD_TO_PERSONAL_DICTIONARY = "add_to_personal_dictionary"
    NOT_WRONG = "not_wrong"
    REWRITE_ACCEPTED = "rewrite_accepted"
    REWRITE_DISMISSED = "rewrite_dismissed"
    TONE_HELPFUL = "tone_helpful"
    TONE_NOT_HELPFUL = "tone_not_helpful"


class FeedbackRequest(BaseModel):
    suggestion_id: str
    action: FeedbackAction
    text: str
    replacement: str | None = None
    feedback_key: str | None = None
    rule_id: str | None = None
    subtype: str | None = None
    source: SuggestionSource | None = None
    original_text: str | None = None
    suppression_key: str | None = None
    user_dictionary_entry: str | None = None
    user_id: str | None = None


class FeedbackRecord(BaseModel):
    id: int | None = None
    suggestion_id: str
    action: FeedbackAction
    text: str
    replacement: str | None = None
    feedback_key: str | None = None
    rule_id: str | None = None
    subtype: str | None = None
    source: SuggestionSource | None = None
    original_text: str | None = None
    suppression_key: str | None = None
    user_dictionary_entry: str | None = None
    user_id: str | None = None
    created_at: datetime


class DetectorHealth(BaseModel):
    enabled: bool
    loaded: bool
    status: str
    reason: str | None = None
    checkpoint: str | None = None
    checkpoint_exists: bool = False
    backend_name: str = "disabled"
    threshold: float = Field(ge=0.0, le=1.0)


class CorrectorHealth(BaseModel):
    enabled: bool
    loaded: bool
    status: str
    reason: str | None = None
    checkpoint: str | None = None
    checkpoint_exists: bool = False
    backend_name: str = "disabled"
    threshold: float = Field(ge=0.0, le=1.0)


class LexiconHealth(BaseModel):
    runtime_source_of_truth: str
    runtime_source: str
    runtime_path: str | None = None
    runtime_exists: bool = False
    version: str | None = None
    checksum: str | None = None
    accepted_word_count: int = Field(default=0, ge=0)
    candidate_word_count: int = Field(default=0, ge=0)
    correction_map_count: int = Field(default=0, ge=0)
    import_database_path: str | None = None
    import_database_exists: bool = False
    loaded_at: datetime | None = None
    reload_supported: bool = False
    restart_required: bool = True


class HealthResponse(BaseModel):
    status: str
    backend_reachable: bool = True
    detector_loaded: bool
    detector_checkpoint: str | None = None
    corrector_loaded: bool
    corrector_checkpoint: str | None = None
    allowed_origins: list[str]
    detector: DetectorHealth
    corrector: CorrectorHealth
    analysis_profile: AnalysisProfile
    degraded_reasons: list[str] = Field(default_factory=list)
    mode_capabilities: dict[str, list[str]] = Field(default_factory=dict)


class HealthDeepResponse(HealthResponse):
    backend_warning: str | None = None
    backend_version: str | None = None
    env_file_path: str | None = None
    env_file_loaded: bool = False
    last_startup_timestamp: datetime
    llm: dict[str, Any] = Field(default_factory=dict)
    lexicon: LexiconHealth


def _infer_suggestion_kind(
    *,
    category: SuggestionCategory,
    subtype: str,
    is_variant_only: bool,
) -> SuggestionKind:
    if is_variant_only or subtype == SuggestionKind.ORTHOGRAPHY_VARIANT.value:
        return SuggestionKind.ORTHOGRAPHY_VARIANT
    if subtype == SuggestionKind.NAMED_ENTITY_OR_USER_WORD.value:
        return SuggestionKind.NAMED_ENTITY_OR_USER_WORD
    if subtype in {
        "spacing_error",
        "extra_whitespace",
        "space_before_punctuation",
        "space_after_punctuation",
        "genitive_spacing",
        "fused_postposition",
        "number_unit_spacing",
    }:
        return SuggestionKind.SPACING_ERROR
    if category == SuggestionCategory.SPELLING:
        return SuggestionKind.TRUE_SPELLING_ERROR
    if category == SuggestionCategory.GRAMMAR:
        return SuggestionKind.GRAMMAR_ERROR
    if category == SuggestionCategory.PUNCTUATION:
        return SuggestionKind.PUNCTUATION_ERROR
    if category == SuggestionCategory.SPACING:
        return SuggestionKind.SPACING_ERROR
    if category in {
        SuggestionCategory.REGISTER,
        SuggestionCategory.CLARITY,
        SuggestionCategory.STYLE,
    }:
        return SuggestionKind.STYLE_SUGGESTION
    return SuggestionKind.NO_SUGGESTION


def _infer_is_contextual(suggestion: Suggestion) -> bool:
    if suggestion.source in {SuggestionSource.MODEL, SuggestionSource.HYBRID}:
        return True
    return suggestion.suggestion_kind in {
        SuggestionKind.GRAMMAR_ERROR,
        SuggestionKind.PUNCTUATION_ERROR,
        SuggestionKind.SPACING_ERROR,
        SuggestionKind.STYLE_SUGGESTION,
    }


def _default_optional_mode_visibility(suggestion_kind: SuggestionKind) -> list[AnalyzeMode]:
    if suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT:
        return [AnalyzeMode.STRICT, AnalyzeMode.FORMAL]
    if suggestion_kind == SuggestionKind.STYLE_SUGGESTION:
        return [AnalyzeMode.STANDARD, AnalyzeMode.STRICT, AnalyzeMode.FORMAL]
    return []


def _build_feedback_key(
    *,
    category: str,
    original_text: str,
    replacement_options: list[str],
) -> str:
    normalized_original = " ".join(original_text.split())
    normalized_replacements = "||".join(" ".join(option.split()) for option in replacement_options)
    return _stable_digest("fbk", f"{category}:{normalized_original}:{normalized_replacements}")


def _build_suppression_key(
    *,
    rule_id: str,
    subtype: str,
    original_text: str,
    replacement_options: list[str],
) -> str:
    normalized_original = " ".join(original_text.split())
    normalized_replacements = "||".join(" ".join(option.split()) for option in replacement_options)
    return _stable_digest("sup", f"{rule_id}:{subtype}:{normalized_original}:{normalized_replacements}")


def _stable_digest(prefix: str, payload: str) -> str:
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _normalize_replacement_option(option: str) -> str:
    if option == "":
        return ""
    compact = re.sub(r"\s+", " ", option.strip())
    if compact:
        return compact
    if option.isspace():
        return " "
    return ""


def _normalize_unique_strings(values: list[str], *, preserve_single_space: bool = False) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = _normalize_replacement_option(value) if preserve_single_space else " ".join(value.split())
        if not compact or compact in seen:
            continue
        seen.add(compact)
        normalized.append(compact)
    return normalized


def _normalize_unique_entries(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = " ".join(value.split())
        if not compact or compact in seen:
            continue
        seen.add(compact)
        normalized.append(compact)
    return normalized


def _normalize_unique_enums(values: list[Enum]) -> list[Enum]:
    normalized: list[Enum] = []
    seen: set[Enum] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized

# Canonical Shuddho API contract used by the TypeScript gateway and future clients.
class TextSpan(BaseModel):
    startIndex: int = Field(ge=0)
    endIndex: int = Field(ge=0)
    utf16StartIndex: int | None = Field(default=None, ge=0)
    utf16EndIndex: int | None = Field(default=None, ge=0)
    codePointStartIndex: int | None = Field(default=None, ge=0)
    codePointEndIndex: int | None = Field(default=None, ge=0)
    graphemeStartIndex: int | None = Field(default=None, ge=0)
    graphemeEndIndex: int | None = Field(default=None, ge=0)


class CanonicalSuggestion(BaseModel):
    id: str
    suppressionKey: str
    ruleId: str
    type: str
    severity: str
    originalText: str
    suggestedText: str
    replacementOptions: list[str] = Field(default_factory=list)
    explanationBn: str
    explanationEn: str | None = None
    span: TextSpan
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    provider: str
    metadata: dict[str, Any] | None = None


class CanonicalCheckRequest(BaseModel):
    text: str
    documentId: str | None = None
    revision: int | None = Field(default=None, ge=0)
    language: str = 'bn'
    dialect: str | None = 'standard'
    userId: str | None = None
    options: dict[str, bool] | None = None


class CanonicalCheckResponse(BaseModel):
    requestId: str
    documentId: str | None = None
    revision: int | None = Field(default=None, ge=0)
    language: str = 'bn'
    normalizedText: str | None = None
    correctedText: str | None = None
    documentAssessment: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[CanonicalSuggestion] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    llm_requested: bool = False
    llm_attempted: bool = False
    llm_used: bool = False
    llm_status: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_response_mode: str | None = None
    local_suggestion_count: int = Field(default=0, ge=0)
    ai_suggestion_count: int = Field(default=0, ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
