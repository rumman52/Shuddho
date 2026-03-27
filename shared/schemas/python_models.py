from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class SuggestionCategory(str, Enum):
    SPELLING = "spelling"
    GRAMMAR = "grammar"
    PUNCTUATION = "punctuation"
    STYLE = "style"


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


class SuggestionKind(str, Enum):
    TRUE_SPELLING_ERROR = "true_spelling_error"
    ORTHOGRAPHY_VARIANT = "orthography_variant"
    STYLE_SUGGESTION = "style_suggestion"
    GRAMMAR_ERROR = "grammar_error"
    PUNCTUATION_ERROR = "punctuation_error"
    SPACING_ERROR = "spacing_error"
    NAMED_ENTITY_OR_USER_WORD = "named_entity_or_user_word"
    NO_SUGGESTION = "no_suggestion"


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

    @field_validator("replacement_options")
    @classmethod
    def normalize_replacement_options(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for option in value:
            compact = _normalize_replacement_option(option)
            if not compact or compact in seen:
                continue
            seen.add(compact)
            normalized.append(compact)
        return normalized

    @field_validator("optional_mode_visibility")
    @classmethod
    def normalize_optional_mode_visibility(cls, value: list[AnalyzeMode]) -> list[AnalyzeMode]:
        normalized: list[AnalyzeMode] = []
        seen: set[AnalyzeMode] = set()
        for mode in value:
            if mode in seen:
                continue
            seen.add(mode)
            normalized.append(mode)
        return normalized

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
        normalized: list[str] = []
        seen: set[str] = set()
        for entry in value:
            compact = " ".join(entry.split())
            if not compact or compact in seen:
                continue
            seen.add(compact)
            normalized.append(compact)
        return normalized


class AnalyzeResponse(BaseModel):
    text: str
    normalized_text: str
    suggestions: list[Suggestion]


class FeedbackAction(str, Enum):
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    SUPPRESSED = "suppressed"
    IGNORE_FOREVER = "ignore_forever"
    ADD_TO_PERSONAL_DICTIONARY = "add_to_personal_dictionary"
    NOT_WRONG = "not_wrong"


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


class HealthResponse(BaseModel):
    status: str
    detector_loaded: bool
    detector_checkpoint: str | None = None
    allowed_origins: list[str]
    openrouter_configured: bool = False
    openrouter_available: bool = False
    openrouter_model: str | None = None


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
    }:
        return SuggestionKind.SPACING_ERROR
    if category == SuggestionCategory.SPELLING:
        return SuggestionKind.TRUE_SPELLING_ERROR
    if category == SuggestionCategory.GRAMMAR:
        return SuggestionKind.GRAMMAR_ERROR
    if category == SuggestionCategory.PUNCTUATION:
        return SuggestionKind.PUNCTUATION_ERROR
    if category == SuggestionCategory.STYLE:
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
