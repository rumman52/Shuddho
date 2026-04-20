from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from ml.corrector.model import BanglaCorrectorSeq2Seq
from ml.corrector.tokenizer import CharacterTokenizer
from services.analysis.shuddho_analysis.span_resolution import (
    SentenceSpan,
    build_anchor_context,
    find_sentence_local_matches,
    split_sentences,
)
from shared.constants.bangla import BANGLA_LETTER_PATTERN, BANGLA_WORD_PATTERN, PUNCTUATION_CHARS
from shared.schemas.python_models import AnalyzeMode, Suggestion, SuggestionCategory, SuggestionSeverity, SuggestionSource
from shared.utils.text import stable_id


SPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(rf"^[{re.escape(PUNCTUATION_CHARS)}\s]+$")


@dataclass(frozen=True)
class CorrectorModelBundle:
    model: BanglaCorrectorSeq2Seq
    tokenizer: CharacterTokenizer
    metadata: dict[str, object]
    checkpoint_dir: Path
    device: object


@dataclass(frozen=True)
class CorrectorPrediction:
    source_text: str
    corrected_text: str
    confidence: float
    token_ids: tuple[int, ...]
    token_confidences: tuple[float, ...]


class LocalSeq2SeqCorrectorBackend:
    backend_name = "local_seq2seq_corrector"

    def __init__(
        self,
        bundle: CorrectorModelBundle,
        *,
        confidence_threshold: float,
    ) -> None:
        self.bundle = bundle
        self.model = bundle.model
        self.tokenizer = bundle.tokenizer
        self.metadata = bundle.metadata
        self.checkpoint_path = str(bundle.checkpoint_dir)
        self.confidence_threshold = confidence_threshold
        self.max_source_length = int(self.metadata.get("max_source_length", 192))
        self.max_target_length = int(self.metadata.get("max_target_length", 192))

    def suggest(
        self,
        text: str,
        mode: AnalyzeMode,
        *,
        personal_dictionary: list[str] | None = None,
    ) -> list[Suggestion]:
        del personal_dictionary
        suggestions: list[Suggestion] = []
        for sentence in split_sentences(text):
            if not _looks_like_bangla_sentence(sentence.text):
                continue
            prediction = self.correct_sentence(sentence.text)
            if prediction.corrected_text == sentence.text:
                continue
            if prediction.confidence < self.confidence_threshold:
                continue
            suggestions.extend(
                _project_prediction_to_suggestions(
                    sentence,
                    prediction,
                    mode=mode,
                )
            )
        return suggestions

    def correct_sentence(self, sentence: str) -> CorrectorPrediction:
        try:
            import torch
        except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
            raise RuntimeError("PyTorch is required for corrector inference") from error

        source_ids = self.tokenizer.encode(
            sentence,
            add_bos=True,
            add_eos=True,
            max_length=self.max_source_length,
        )
        source_tensor = torch.tensor([source_ids], dtype=torch.long, device=self.bundle.device)
        outputs = self.model.greedy_decode(
            source_tensor,
            bos_token_id=self.tokenizer.bos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            max_length=self.max_target_length,
        )
        token_ids = outputs["token_ids"][0].detach().cpu().tolist()
        token_confidences = outputs["token_confidences"][0].detach().cpu().tolist()
        corrected_text = self.tokenizer.decode(token_ids)
        if not corrected_text:
            corrected_text = sentence
        usable_confidences = [
            float(confidence)
            for token_id, confidence in zip(token_ids, token_confidences)
            if token_id != self.tokenizer.eos_token_id
        ]
        confidence = round(sum(usable_confidences) / max(len(usable_confidences), 1), 4)
        return CorrectorPrediction(
            source_text=sentence,
            corrected_text=corrected_text,
            confidence=confidence,
            token_ids=tuple(int(token_id) for token_id in token_ids),
            token_confidences=tuple(float(value) for value in token_confidences),
        )


def load_corrector_bundle(
    checkpoint_dir: str | Path,
    *,
    checkpoint_name: str = "best_model.pt",
    device: str = "auto",
) -> CorrectorModelBundle:
    try:
        import torch
    except (ImportError, OSError) as error:  # pragma: no cover - depends on local torch runtime
        raise RuntimeError("PyTorch is required for corrector inference") from error

    checkpoint_dir = Path(checkpoint_dir)
    metadata_path = checkpoint_dir / "metadata.json"
    checkpoint_path = checkpoint_dir / checkpoint_name
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(checkpoint_path)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    tokenizer = CharacterTokenizer.from_dict(dict(metadata["tokenizer"]))
    model_config = dict(metadata["model"])
    runtime_device = _resolve_device(device, torch)
    checkpoint = torch.load(checkpoint_path, map_location=runtime_device)
    model = BanglaCorrectorSeq2Seq(
        vocab_size=tokenizer.vocab_size,
        embedding_size=int(model_config.get("embedding_size", 128)),
        hidden_size=int(model_config.get("hidden_size", 192)),
        dropout=float(model_config.get("dropout", 0.15)),
        pad_token_id=tokenizer.pad_token_id,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(runtime_device)
    model.eval()
    return CorrectorModelBundle(
        model=model,
        tokenizer=tokenizer,
        metadata=metadata,
        checkpoint_dir=checkpoint_dir,
        device=runtime_device,
    )


def load_corrector_backend(
    checkpoint_dir: str | Path,
    *,
    confidence_threshold: float,
) -> LocalSeq2SeqCorrectorBackend:
    return LocalSeq2SeqCorrectorBackend(
        load_corrector_bundle(checkpoint_dir),
        confidence_threshold=confidence_threshold,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local inference with a trained Shuddho corrector.")
    parser.add_argument("--checkpoint-dir", required=True, help="Directory containing the trained corrector checkpoint.")
    parser.add_argument("--text", required=True, help="Bangla sentence or paragraph to correct.")
    parser.add_argument("--mode", default="standard", choices=["standard", "strict", "formal"])
    args = parser.parse_args()

    backend = load_corrector_backend(args.checkpoint_dir, confidence_threshold=0.0)
    suggestions = backend.suggest(args.text, AnalyzeMode(args.mode))
    prediction = [backend.correct_sentence(sentence.text) for sentence in split_sentences(args.text)]
    payload = {
        "predictions": [
            {
                "source_text": item.source_text,
                "corrected_text": item.corrected_text,
                "confidence": item.confidence,
            }
            for item in prediction
        ],
        "suggestions": [suggestion.model_dump() for suggestion in suggestions],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _project_prediction_to_suggestions(
    sentence: SentenceSpan,
    prediction: CorrectorPrediction,
    *,
    mode: AnalyzeMode,
) -> list[Suggestion]:
    matcher = SequenceMatcher(a=prediction.source_text, b=prediction.corrected_text)
    suggestions: list[Suggestion] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        original_start, original_end, corrected_start, corrected_end = _expand_edit_if_needed(
            prediction.source_text,
            prediction.corrected_text,
            i1,
            i2,
            j1,
            j2,
        )
        original_text = prediction.source_text[original_start:original_end]
        replacement = prediction.corrected_text[corrected_start:corrected_end]
        if not replacement or original_text == replacement:
            continue
        if _looks_like_rewrite(original_text, replacement, mode=mode):
            continue

        category, subtype, severity = _classify_edit(original_text, replacement)
        confidence = _estimate_edit_confidence(prediction.confidence, original_text, replacement, mode=mode)
        if confidence < _minimum_edit_confidence(mode):
            continue

        anchor_before, anchor_after = build_anchor_context(sentence.text, original_start, original_end)
        occurrence_index = _resolve_occurrence_index(sentence.text, original_text, original_start, original_end)
        suggestions.append(
            Suggestion(
                id=stable_id(
                    "corrector",
                    f"{sentence.start + original_start}:{sentence.start + original_end}:{original_text}:{replacement}",
                ),
                rule_id=_corrector_rule_id(category),
                category=category,
                subtype=subtype,
                span_start=sentence.start + original_start,
                span_end=sentence.start + original_end,
                original_text=original_text,
                replacement_options=[replacement],
                confidence=confidence,
                explanation_bn=_explanation_bn(original_text, replacement, category),
                explanation_en=_explanation_en(original_text, replacement, category),
                source=SuggestionSource.MODEL,
                severity=severity,
                is_contextual=True,
                sentence_index=sentence.sentence_index,
                sentence_start=sentence.start,
                sentence_end=sentence.end,
                occurrence_index=occurrence_index,
                anchor_before=anchor_before,
                anchor_after=anchor_after,
                source_trace=["corrector_seq2seq", "exact_unique_match"],
            )
        )

    return suggestions


def _expand_edit_if_needed(
    source_text: str,
    corrected_text: str,
    i1: int,
    i2: int,
    j1: int,
    j2: int,
) -> tuple[int, int, int, int]:
    if i1 != i2 and j1 != j2:
        return i1, i2, j1, j2

    if i1 == i2:
        if i2 < len(source_text):
            expanded_end = _find_right_unit_boundary(source_text, i2)
            if expanded_end > i2:
                return i1, expanded_end, j1, min(len(corrected_text), j2 + (expanded_end - i2))
        if i1 > 0:
            expanded_start = _find_left_unit_boundary(source_text, i1)
            return expanded_start, i2, expanded_start, j2
        expanded_end = _find_right_unit_boundary(source_text, i2)
        return i1, expanded_end, j1, min(len(corrected_text), j2 + (expanded_end - i2))

    if j1 == j2:
        if i2 < len(source_text):
            expanded_end = _find_right_unit_boundary(source_text, i2)
            if expanded_end > i2:
                return i1, expanded_end, j1, min(len(corrected_text), j2 + (expanded_end - i2))
        if i1 > 0:
            expanded_start = _find_left_unit_boundary(source_text, i1)
            shift = i1 - expanded_start
            return expanded_start, i2, max(0, j1 - shift), j2
        expanded_end = _find_right_unit_boundary(source_text, i2)
        return i1, expanded_end, j1, min(len(corrected_text), j2 + (expanded_end - i2))

    return i1, i2, j1, j2


def _find_left_unit_boundary(text: str, index: int) -> int:
    if index <= 0:
        return 0
    cursor = index
    while cursor > 0 and text[cursor - 1].isspace():
        cursor -= 1
    while cursor > 0 and not text[cursor - 1].isspace():
        cursor -= 1
    return cursor


def _find_right_unit_boundary(text: str, index: int) -> int:
    cursor = index
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    while cursor < len(text) and not text[cursor].isspace():
        cursor += 1
    return cursor




def _classify_edit(
    original_text: str,
    replacement: str,
) -> tuple[SuggestionCategory, str, SuggestionSeverity]:
    compact_original = SPACE_RE.sub("", original_text)
    compact_replacement = SPACE_RE.sub("", replacement)
    stripped_original = original_text.strip()
    stripped_replacement = replacement.strip()

    if compact_original == compact_replacement and original_text != replacement:
        return SuggestionCategory.PUNCTUATION, "spacing_error", SuggestionSeverity.LOW
    if PUNCTUATION_RE.fullmatch(original_text) or PUNCTUATION_RE.fullmatch(replacement):
        return SuggestionCategory.PUNCTUATION, "corrector_punctuation", SuggestionSeverity.LOW
    if _differs_only_by_attached_punctuation(stripped_original, stripped_replacement):
        return SuggestionCategory.PUNCTUATION, "corrector_punctuation", SuggestionSeverity.LOW
    if (
        BANGLA_WORD_PATTERN.fullmatch(stripped_original)
        and BANGLA_WORD_PATTERN.fullmatch(stripped_replacement)
        and _levenshtein_distance(stripped_original, stripped_replacement) <= 2
    ):
        return SuggestionCategory.SPELLING, "corrector_spelling", SuggestionSeverity.MEDIUM
    return SuggestionCategory.GRAMMAR, "corrector_sentence_fix", SuggestionSeverity.MEDIUM


def _differs_only_by_attached_punctuation(original_text: str, replacement: str) -> bool:
    if not original_text or not replacement:
        return False
    if original_text == replacement:
        return False
    if replacement.startswith(original_text):
        suffix = replacement[len(original_text) :]
        return bool(suffix and PUNCTUATION_RE.fullmatch(suffix))
    if original_text.startswith(replacement):
        suffix = original_text[len(replacement) :]
        return bool(suffix and PUNCTUATION_RE.fullmatch(suffix))
    return False


def _estimate_edit_confidence(
    base_confidence: float,
    original_text: str,
    replacement: str,
    *,
    mode: AnalyzeMode,
) -> float:
    penalty = 0.0
    penalty += max(len(replacement.split()) - 1, 0) * 0.02
    penalty += max(len(replacement) - len(original_text), 0) * 0.003
    if mode == AnalyzeMode.STANDARD:
        penalty += 0.02
    return round(max(0.55, min(base_confidence - penalty, 0.99)), 2)


def _minimum_edit_confidence(mode: AnalyzeMode) -> float:
    if mode == AnalyzeMode.STANDARD:
        return 0.8
    if mode == AnalyzeMode.STRICT:
        return 0.75
    return 0.72


def _looks_like_rewrite(original_text: str, replacement: str, *, mode: AnalyzeMode) -> bool:
    if not original_text or not replacement:
        return True
    token_limit = 6 if mode == AnalyzeMode.STANDARD else 8
    char_limit = max(len(original_text) * 3, len(original_text) + 10, 24)
    if len(replacement.split()) > token_limit:
        return True
    if len(replacement) > char_limit:
        return True
    return False


def _resolve_occurrence_index(sentence_text: str, original_text: str, start: int, end: int) -> int | None:
    matches = find_sentence_local_matches(sentence_text, original_text)
    for match in matches:
        if match.start == start and match.end == end:
            return match.occurrence_index
    return None


def _looks_like_bangla_sentence(text: str) -> bool:
    bangla_letters = sum(1 for character in text if BANGLA_LETTER_PATTERN.search(character))
    return bangla_letters >= 3


def _corrector_rule_id(category: SuggestionCategory) -> str:
    return {
        SuggestionCategory.SPELLING: "COR_SPELL_001",
        SuggestionCategory.GRAMMAR: "COR_GRAM_001",
        SuggestionCategory.PUNCTUATION: "COR_PUNC_001",
        SuggestionCategory.STYLE: "COR_STYLE_001",
    }[category]


def _explanation_bn(original_text: str, replacement: str, category: SuggestionCategory) -> str:
    if category == SuggestionCategory.SPELLING:
        return f"স্থানীয় corrector এখানে '{original_text}' এর বদলে '{replacement}' প্রস্তাব করছে।"
    if category == SuggestionCategory.PUNCTUATION:
        return f"স্থানীয় corrector এখানে '{replacement}' ব্যবহার করতে বলছে।"
    return f"স্থানীয় corrector এখানে '{replacement}' রূপটি বেশি স্বাভাবিক মনে করছে।"


def _explanation_en(original_text: str, replacement: str, category: SuggestionCategory) -> str:
    if category == SuggestionCategory.SPELLING:
        return f"The local corrector suggests '{replacement}' instead of '{original_text}' here."
    if category == SuggestionCategory.PUNCTUATION:
        return f"The local corrector suggests using '{replacement}' here."
    return f"The local corrector suggests '{replacement}' as the more natural local fix here."


def _levenshtein_distance(source: str, target: str) -> int:
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)

    previous = list(range(len(target) + 1))
    for row_index, source_character in enumerate(source, start=1):
        current = [row_index]
        for column_index, target_character in enumerate(target, start=1):
            insert_cost = current[column_index - 1] + 1
            delete_cost = previous[column_index] + 1
            replace_cost = previous[column_index - 1] + (0 if source_character == target_character else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _resolve_device(device_name: str, torch_module):
    if device_name == "cpu":
        return torch_module.device("cpu")
    if device_name == "cuda":
        return torch_module.device("cuda")
    return torch_module.device("cuda" if torch_module.cuda.is_available() else "cpu")


if __name__ == "__main__":
    main()
