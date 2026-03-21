from __future__ import annotations

from shared.schemas.python_models import Suggestion

from .text import stable_id


def build_feedback_key(
    *,
    category: str,
    original_text: str,
    replacement_options: list[str] | tuple[str, ...],
) -> str:
    normalized_original = " ".join(original_text.split())
    normalized_replacements = tuple(" ".join(option.split()) for option in replacement_options)
    payload = f"{category}:{normalized_original}:{'||'.join(normalized_replacements)}"
    return stable_id("fbk", payload)


def ensure_feedback_key(suggestion: Suggestion) -> Suggestion:
    if suggestion.feedback_key:
        return suggestion
    return suggestion.model_copy(
        update={
            "feedback_key": build_feedback_key(
                category=suggestion.category.value,
                original_text=suggestion.original_text,
                replacement_options=suggestion.replacement_options,
            )
        }
    )
