from __future__ import annotations

from shared.schemas.python_models import SuggestionCategory


DETECTOR_LABELS = (
    "ok",
    "spelling",
    "punctuation",
    "spacing",
    "repeated_word",
    "verb_agreement",
    "pronoun_mismatch",
    "suffix_error",
    "postposition_error",
    "mixed_register",
    "orthography_variant",
    "code_mix",
    "word_order",
    "missing_word",
    "extra_word",
    "mixed_digit_style",
    "grammar",
)
DETECTOR_LABEL_TO_ID = {label: index for index, label in enumerate(DETECTOR_LABELS)}
DETECTOR_ID_TO_LABEL = {index: label for label, index in DETECTOR_LABEL_TO_ID.items()}
DETECTOR_PAD_LABEL_ID = -100
DETECTOR_PAD_TOKEN = "<pad>"
DETECTOR_UNK_TOKEN = "<unk>"

DETECTOR_LABEL_TO_CATEGORY = {
    "spelling": SuggestionCategory.SPELLING,
    "orthography_variant": SuggestionCategory.STYLE,
    "grammar": SuggestionCategory.GRAMMAR,
    "punctuation": SuggestionCategory.PUNCTUATION,
    "spacing": SuggestionCategory.STYLE,
    "repeated_word": SuggestionCategory.GRAMMAR,
    "verb_agreement": SuggestionCategory.GRAMMAR,
    "pronoun_mismatch": SuggestionCategory.GRAMMAR,
    "suffix_error": SuggestionCategory.GRAMMAR,
    "postposition_error": SuggestionCategory.GRAMMAR,
    "mixed_register": SuggestionCategory.STYLE,
    "code_mix": SuggestionCategory.STYLE,
    "word_order": SuggestionCategory.GRAMMAR,
    "missing_word": SuggestionCategory.GRAMMAR,
    "extra_word": SuggestionCategory.GRAMMAR,
    "mixed_digit_style": SuggestionCategory.STYLE,
}

DETECTOR_LABEL_ALIASES = {
    "variant_mapping": "orthography_variant",
    "mixed_address_register": "mixed_register",
    "formal_informal_mismatch": "mixed_register",
    "honorific_pronoun_verb_mismatch": "verb_agreement",
    "casual_pronoun_verb_mismatch": "verb_agreement",
    "first_person_verb_mismatch": "verb_agreement",
    "third_person_verb_mismatch": "verb_agreement",
    "fused_postposition": "postposition_error",
    "genitive_spacing": "postposition_error",
    "code_mixed_latin": "code_mix",
    "safe_exact_correction": "spelling",
}


def normalize_detector_label(label: str | int) -> str:
    if isinstance(label, int):
        return DETECTOR_ID_TO_LABEL.get(label, "ok")

    normalized = label.strip().lower()
    normalized = DETECTOR_LABEL_ALIASES.get(normalized, normalized)
    return normalized if normalized in DETECTOR_LABEL_TO_ID else "ok"


def resolve_detector_label(
    *,
    label: str | int | None = None,
    fine_label: str | None = None,
    subtype: str | None = None,
) -> str:
    for candidate in (fine_label, label, subtype):
        if candidate is None:
            continue
        normalized = normalize_detector_label(candidate)
        if normalized != "ok" or str(candidate).strip().lower() == "ok":
            return normalized
    return "ok"
