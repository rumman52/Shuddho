from __future__ import annotations

from shared.schemas.python_models import SuggestionCategory


DETECTOR_LABELS = ("ok", "spelling", "grammar", "punctuation", "spacing")
DETECTOR_LABEL_TO_ID = {label: index for index, label in enumerate(DETECTOR_LABELS)}
DETECTOR_ID_TO_LABEL = {index: label for label, index in DETECTOR_LABEL_TO_ID.items()}
DETECTOR_PAD_LABEL_ID = -100
DETECTOR_PAD_TOKEN = "<pad>"
DETECTOR_UNK_TOKEN = "<unk>"

DETECTOR_LABEL_TO_CATEGORY = {
    "spelling": SuggestionCategory.SPELLING,
    "grammar": SuggestionCategory.GRAMMAR,
    "punctuation": SuggestionCategory.PUNCTUATION,
    "spacing": SuggestionCategory.STYLE,
}


def normalize_detector_label(label: str | int) -> str:
    if isinstance(label, int):
        return DETECTOR_ID_TO_LABEL.get(label, "ok")

    normalized = label.strip().lower()
    return normalized if normalized in DETECTOR_LABEL_TO_ID else "ok"
