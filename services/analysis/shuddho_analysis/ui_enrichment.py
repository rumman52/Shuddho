from __future__ import annotations

from collections.abc import Callable

from shared.schemas.python_models import RewriteIntent, Suggestion, SuggestionCategory, SuggestionKind, SuggestionUiGroup, ToneLabel


class SuggestionUiEnricher:
    def __init__(self, *, auto_apply_checker: Callable[[str, Suggestion], bool] | None = None) -> None:
        self.auto_apply_checker = auto_apply_checker

    def enrich(self, text: str, suggestions: list[Suggestion]) -> list[Suggestion]:
        return [self._enrich_one(text, suggestion) for suggestion in suggestions]

    def _enrich_one(self, text: str, suggestion: Suggestion) -> Suggestion:
        ui_group = _resolve_ui_group(suggestion)
        short_title = _resolve_short_title(suggestion)
        can_auto_apply = self.auto_apply_checker(text, suggestion) if self.auto_apply_checker is not None else False
        learnable = suggestion.suggestion_kind not in {
            SuggestionKind.NO_SUGGESTION,
            SuggestionKind.NAMED_ENTITY_OR_USER_WORD,
        }
        rewrite_intents = _resolve_rewrite_intents(suggestion, ui_group)
        tone_labels = _resolve_tone_labels(suggestion)

        return suggestion.model_copy(
            update={
                "short_title": short_title,
                "ui_group": ui_group,
                "can_auto_apply": can_auto_apply,
                "learnable": learnable,
                "suggestion_reason_short_bn": _short_reason(suggestion.explanation_bn, short_title),
                "suggestion_reason_short_en": _short_reason(suggestion.explanation_en, short_title),
                "action_hints": _resolve_action_hints(suggestion, can_auto_apply, learnable, rewrite_intents),
                "rewrite_intents": rewrite_intents,
                "tone_labels": tone_labels,
            }
        )


def _resolve_ui_group(suggestion: Suggestion) -> SuggestionUiGroup:
    if suggestion.suggestion_kind in {SuggestionKind.PUNCTUATION_ERROR, SuggestionKind.SPACING_ERROR}:
        return SuggestionUiGroup.PUNCTUATION
    if suggestion.subtype in {"repeated_word", "code_mixed_latin"}:
        return SuggestionUiGroup.CLARITY
    if any(marker in suggestion.subtype for marker in {"honorific", "formal", "casual", "polite"}):
        return SuggestionUiGroup.TONE
    if suggestion.category == SuggestionCategory.STYLE:
        return SuggestionUiGroup.STYLE
    return SuggestionUiGroup.CORRECTNESS


def _resolve_short_title(suggestion: Suggestion) -> str:
    subtype_titles = {
        "repeated_word": "Repeated word",
        "spelling_error": "Spelling fix",
        "duplicate_punctuation": "Duplicate punctuation",
        "space_before_punctuation": "Spacing before punctuation",
        "space_after_punctuation": "Spacing after punctuation",
        "extra_whitespace": "Extra spacing",
        "orthography_variant": "Variant wording",
        "number_unit_spacing": "Number style",
        "mixed_digit_style": "Digit style",
        "code_mixed_latin": "Mixed language wording",
        "fused_postposition": "Joined postposition",
    }
    if suggestion.subtype in subtype_titles:
        return subtype_titles[suggestion.subtype]
    if suggestion.suggestion_kind == SuggestionKind.GRAMMAR_ERROR:
        return "Grammar suggestion"
    if suggestion.suggestion_kind == SuggestionKind.PUNCTUATION_ERROR:
        return "Punctuation suggestion"
    if suggestion.suggestion_kind == SuggestionKind.STYLE_SUGGESTION:
        return "Style suggestion"
    return "Writing suggestion"


def _short_reason(explanation: str, fallback: str) -> str:
    normalized = " ".join(explanation.split())
    if not normalized:
        return fallback
    if len(normalized) <= 84:
        return normalized
    truncated = normalized[:81].rsplit(" ", 1)[0].strip()
    return f"{truncated}..."


def _resolve_action_hints(
    suggestion: Suggestion,
    can_auto_apply: bool,
    learnable: bool,
    rewrite_intents: list[RewriteIntent],
) -> list[str]:
    hints: list[str] = []
    if suggestion.replacement_options:
        hints.append("apply" if can_auto_apply else "review")
    if learnable:
        hints.append("dismiss")
        hints.append("ignore_forever")
    if _can_add_to_dictionary(suggestion):
        hints.append("add_to_dictionary")
    if rewrite_intents:
        hints.append("rewrite")
    return _dedupe_strings(hints)


def _resolve_rewrite_intents(suggestion: Suggestion, ui_group: SuggestionUiGroup) -> list[RewriteIntent]:
    intents: list[RewriteIntent] = []
    if ui_group in {SuggestionUiGroup.CORRECTNESS, SuggestionUiGroup.PUNCTUATION, SuggestionUiGroup.CLARITY}:
        intents.append(RewriteIntent.CLARITY)
    if ui_group in {SuggestionUiGroup.STYLE, SuggestionUiGroup.TONE}:
        intents.extend([RewriteIntent.CLARITY, RewriteIntent.CONCISE])
    if suggestion.subtype in {"orthography_variant", "honorific_pronoun_verb_mismatch"}:
        intents.extend([RewriteIntent.FORMAL, RewriteIntent.PROFESSIONAL])
    if "casual" in suggestion.subtype or "chatty" in suggestion.subtype:
        intents.extend([RewriteIntent.PROFESSIONAL, RewriteIntent.FORMAL])
    if ui_group == SuggestionUiGroup.TONE:
        intents.append(RewriteIntent.FRIENDLY)
    return _dedupe_enum_values(intents)


def _resolve_tone_labels(suggestion: Suggestion) -> list[ToneLabel]:
    labels: list[ToneLabel] = []
    if "honorific" in suggestion.subtype or "formal" in suggestion.subtype:
        labels.extend([ToneLabel.PROFESSIONAL, ToneLabel.RESPECTFUL])
    if "casual" in suggestion.subtype or "chatty" in suggestion.subtype:
        labels.extend([ToneLabel.CASUAL, ToneLabel.FRIENDLY])
    return _dedupe_enum_values(labels)


def _can_add_to_dictionary(suggestion: Suggestion) -> bool:
    normalized = suggestion.original_text.strip()
    if not normalized or "\n" in normalized or len(normalized) > 40:
        return False
    if suggestion.category == SuggestionCategory.PUNCTUATION:
        return False
    return len(normalized.split()) <= 3


def _dedupe_strings(values: list[str]) -> list[str]:
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        compact.append(normalized)
    return compact


def _dedupe_enum_values(values: list[RewriteIntent] | list[ToneLabel]) -> list:
    compact: list = []
    seen: set = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        compact.append(value)
    return compact
