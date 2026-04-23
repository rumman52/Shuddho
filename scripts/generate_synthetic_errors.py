from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from shared.constants.bangla import (
    BANGLA_TO_LATIN_DIGITS,
    BANGLA_WORD_PATTERN,
    CASUAL_PRONOUNS,
    CASUAL_VERB_MAP,
    CODE_MIX_REPLACEMENTS,
    COMMON_POSTPOSITIONS,
    CURATED_VARIANT_CORRECTIONS,
    FIRST_PERSON_PRONOUNS,
    FIRST_PERSON_VERB_MAP,
    HONORIFIC_VERB_MAP,
    LATIN_TO_BANGLA_DIGITS,
    POLITE_PRONOUNS,
    SAFE_EXACT_TYPOS,
    THIRD_PERSON_PRONOUNS,
    THIRD_PERSON_VERB_MAP,
    TOKEN_PATTERN,
)

SPACE_BETWEEN_WORDS_RE = re.compile(r"(?P<left>[\u0980-\u09FF]) (?P<right>[\u0980-\u09FF])")
PUNCTUATION_RE = re.compile(r"[।!?]")
FUNCTION_WORDS = frozenset({"না", "ও", "এবং", "খুব", "একটি", "একটা", "তো", "হয়তো"})
EXTRA_WORD_INSERTION = "খুব"
SUFFIX_ERROR_SUFFIXES = ("গুলো", "দের", "ভাবে", "টি")
LOOKAHEAD_WORD_LIMIT = 4
COARSE_LABELS = frozenset({"ok", "spelling", "grammar", "punctuation", "spacing"})
FIRST_PERSON_CORRECT_TO_WRONG = {correct: wrong for wrong, correct in FIRST_PERSON_VERB_MAP.items()}
CASUAL_CORRECT_TO_WRONG = {correct: wrong for wrong, correct in CASUAL_VERB_MAP.items()}
HONORIFIC_CORRECT_TO_WRONG = {correct: wrong for wrong, correct in HONORIFIC_VERB_MAP.items()}
THIRD_PERSON_CORRECT_TO_WRONG = {correct: wrong for wrong, correct in THIRD_PERSON_VERB_MAP.items()}
CODE_MIX_REVERSE_MAP = {bangla_word: latin_word for latin_word, bangla_word in CODE_MIX_REPLACEMENTS.items()}


@dataclass(frozen=True)
class TokenSpan:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class SyntheticIssue:
    start: int
    end: int
    label: str
    subtype: str
    fine_label: str | None = None
    expected_text: str | None = None
    observed_text: str | None = None
    is_variant_only: bool = False

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "start": self.start,
            "end": self.end,
            "label": self.label,
            "subtype": self.subtype,
        }
        if self.fine_label is not None:
            payload["fine_label"] = self.fine_label
        if self.expected_text is not None:
            payload["expected_text"] = self.expected_text
        if self.observed_text is not None:
            payload["observed_text"] = self.observed_text
        if self.is_variant_only:
            payload["is_variant_only"] = True
        return payload


@dataclass(frozen=True)
class SyntheticRecord:
    source_text: str
    target_text: str
    issues: tuple[SyntheticIssue, ...]
    source_split: str = "synthetic"
    generation_method: str = "rule_mutation"

    def as_combined_record(self) -> dict[str, object]:
        return {
            "input_text": self.source_text,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "issues": [issue.as_payload() for issue in self.issues],
            "source_split": self.source_split,
            "generation_method": self.generation_method,
        }

    def as_corrector_record(self) -> dict[str, str]:
        return {
            "source_text": self.source_text,
            "target_text": self.target_text,
        }

    def as_detector_record(self) -> dict[str, object]:
        return {
            "input_text": self.source_text,
            "target_text": self.target_text,
            "issues": [issue.as_payload() for issue in self.issues],
            "source_split": self.source_split,
            "generation_method": self.generation_method,
        }


def create_variants(text: str) -> list[SyntheticRecord]:
    variants: list[SyntheticRecord] = []
    generators = (
        _true_spelling_variants,
        _orthography_variant_records,
        _repeated_word_records,
        _punctuation_spacing_records,
        _verb_agreement_records,
        _pronoun_mismatch_records,
        _suffix_error_records,
        _postposition_error_records,
        _missing_word_records,
        _extra_word_records,
        _formal_informal_mismatch_records,
        _word_order_records,
        _mixed_digit_style_records,
        _code_mix_records,
    )
    for generator in generators:
        variants.extend(generator(text))
    return _dedupe_records(variants)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic Bangla error records for Shuddho.")
    parser.add_argument("--input", required=True, help="Clean corpus text file.")
    parser.add_argument("--output", required=True, help="JSONL output path.")
    parser.add_argument(
        "--task",
        choices=("combined", "corrector", "detector"),
        default="combined",
        help="Which record shape to emit.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records: list[dict[str, object]] = []

    for line in input_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for record in create_variants(stripped):
            if args.task == "corrector":
                records.append(record.as_corrector_record())
            elif args.task == "detector":
                records.append(record.as_detector_record())
            else:
                records.append(record.as_combined_record())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + ("\n" if records else ""),
        encoding="utf-8",
    )


def _true_spelling_variants(text: str) -> list[SyntheticRecord]:
    variants: list[SyntheticRecord] = []
    for wrong_form, correct_form in sorted(SAFE_EXACT_TYPOS.items(), key=lambda item: (item[1], item[0])):
        token = _find_token(text, correct_form)
        if token is None:
            continue
        variants.append(
            _replace_token(
                text,
                token,
                wrong_form,
                label="spelling",
                subtype="true_spelling_error",
                fine_label="spelling",
                expected_text=correct_form,
                observed_text=wrong_form,
            )
        )
    return variants


def _orthography_variant_records(text: str) -> list[SyntheticRecord]:
    variants: list[SyntheticRecord] = []
    for variant_form, formal_form in sorted(CURATED_VARIANT_CORRECTIONS.items(), key=lambda item: (item[1], item[0])):
        token = _find_token(text, formal_form)
        if token is None:
            continue
        variants.append(
            _replace_token(
                text,
                token,
                variant_form,
                label="spelling",
                subtype="orthography_variant",
                fine_label="orthography_variant",
                expected_text=formal_form,
                observed_text=variant_form,
                is_variant_only=True,
            )
        )
    return variants


def _repeated_word_records(text: str) -> list[SyntheticRecord]:
    for token in _word_tokens(text):
        duplicated = f"{token.text} {token.text}"
        return [
            _replace_token(
                text,
                token,
                duplicated,
                label="grammar",
                subtype="repeated_word",
                fine_label="repeated_word",
                expected_text=token.text,
                observed_text=duplicated,
            )
        ]
    return []


def _punctuation_spacing_records(text: str) -> list[SyntheticRecord]:
    records: list[SyntheticRecord] = []
    punctuation_match = PUNCTUATION_RE.search(text)
    if punctuation_match is not None:
        punctuation_start = punctuation_match.start()
        punctuation_character = punctuation_match.group(0)

        if punctuation_start > 0 and not text[punctuation_start - 1].isspace():
            records.append(
                _replace_span(
                    text,
                    punctuation_start,
                    punctuation_start + 1,
                    f" {punctuation_character}",
                    label="spacing",
                    subtype="space_before_punctuation",
                    fine_label="spacing",
                    expected_text=punctuation_character,
                    observed_text=f" {punctuation_character}",
                )
            )

        records.append(
            _replace_span(
                text,
                punctuation_start,
                punctuation_start + 1,
                punctuation_character * 2,
                label="punctuation",
                subtype="duplicate_punctuation",
                fine_label="punctuation",
                expected_text=punctuation_character,
                observed_text=punctuation_character * 2,
            )
        )

        if punctuation_character == "।":
            records.append(
                _replace_span(
                    text,
                    punctuation_start,
                    punctuation_start + 1,
                    ".",
                    label="punctuation",
                    subtype="latin_full_stop",
                    fine_label="punctuation",
                    expected_text="।",
                    observed_text=".",
                )
            )

    spacing_match = SPACE_BETWEEN_WORDS_RE.search(text)
    if spacing_match is not None:
        insert_at = spacing_match.start("right")
        records.append(
            _insert_text(
                text,
                insert_at,
                " ",
                label="spacing",
                subtype="extra_whitespace",
                fine_label="spacing",
                expected_text="",
                observed_text=" ",
            )
        )

    return records


def _verb_agreement_records(text: str) -> list[SyntheticRecord]:
    tokens = _tokenize_with_offsets(text)
    for index, token in enumerate(tokens):
        if token.text in FIRST_PERSON_PRONOUNS:
            record = _replace_following_verb(
                text,
                tokens,
                index,
                FIRST_PERSON_CORRECT_TO_WRONG,
                subtype="verb_agreement",
                fine_label="verb_agreement",
            )
            if record is not None:
                return [record]
        if token.text in CASUAL_PRONOUNS:
            record = _replace_following_verb(
                text,
                tokens,
                index,
                CASUAL_CORRECT_TO_WRONG,
                subtype="verb_agreement",
                fine_label="verb_agreement",
            )
            if record is not None:
                return [record]
        if token.text in POLITE_PRONOUNS:
            record = _replace_following_verb(
                text,
                tokens,
                index,
                HONORIFIC_CORRECT_TO_WRONG,
                subtype="verb_agreement",
                fine_label="verb_agreement",
            )
            if record is not None:
                return [record]
        if token.text in THIRD_PERSON_PRONOUNS:
            record = _replace_following_verb(
                text,
                tokens,
                index,
                THIRD_PERSON_CORRECT_TO_WRONG,
                subtype="verb_agreement",
                fine_label="verb_agreement",
            )
            if record is not None:
                return [record]
    return []


def _pronoun_mismatch_records(text: str) -> list[SyntheticRecord]:
    for token in _word_tokens(text):
        replacement = _mismatched_pronoun(token.text)
        if replacement is None:
            continue
        return [
            _replace_token(
                text,
                token,
                replacement,
                label="grammar",
                subtype="pronoun_mismatch",
                fine_label="pronoun_mismatch",
                expected_text=token.text,
                observed_text=replacement,
            )
        ]
    return []


def _suffix_error_records(text: str) -> list[SyntheticRecord]:
    for token in _word_tokens(text):
        for suffix in SUFFIX_ERROR_SUFFIXES:
            if not token.text.endswith(suffix) or len(token.text) <= len(suffix) + 1:
                continue
            mutated = token.text[:-1]
            if mutated == token.text:
                continue
            return [
                _replace_token(
                    text,
                    token,
                    mutated,
                    label="grammar",
                    subtype="suffix_error",
                    fine_label="suffix_error",
                    expected_text=token.text,
                    observed_text=mutated,
                )
            ]
    return []


def _postposition_error_records(text: str) -> list[SyntheticRecord]:
    tokens = _tokenize_with_offsets(text)
    for index in range(len(tokens) - 1):
        left = tokens[index]
        right = tokens[index + 1]
        if right.text not in COMMON_POSTPOSITIONS:
            continue
        if text[left.end:right.start] != " ":
            continue
        fused = f"{left.text}{right.text}"
        return [
            _replace_span(
                text,
                left.start,
                right.end,
                fused,
                label="grammar",
                subtype="fused_postposition",
                fine_label="postposition_error",
                expected_text=text[left.start:right.end],
                observed_text=fused,
            )
        ]
    return []


def _missing_word_records(text: str) -> list[SyntheticRecord]:
    tokens = _tokenize_with_offsets(text)
    for index, token in enumerate(tokens):
        if token.text not in FUNCTION_WORDS and token.text not in COMMON_POSTPOSITIONS:
            continue
        source_text, issue_position = _remove_token_with_spacing(text, tokens, index)
        return [
            SyntheticRecord(
                source_text=source_text,
                target_text=text,
                issues=(
                    SyntheticIssue(
                        start=issue_position,
                        end=issue_position,
                        label="grammar",
                        subtype="missing_word",
                        fine_label="missing_word",
                        expected_text=token.text,
                        observed_text="",
                    ),
                ),
            )
        ]
    return []


def _extra_word_records(text: str) -> list[SyntheticRecord]:
    tokens = _word_tokens(text)
    if len(tokens) < 2:
        return []
    insertion_point = tokens[min(1, len(tokens) - 1)].start
    return [
        _insert_text(
            text,
            insertion_point,
            f"{EXTRA_WORD_INSERTION} ",
            label="grammar",
            subtype="extra_word",
            fine_label="extra_word",
            expected_text="",
            observed_text=EXTRA_WORD_INSERTION,
        )
    ]


def _formal_informal_mismatch_records(text: str) -> list[SyntheticRecord]:
    for token in _word_tokens(text):
        conflicting_pronoun = None
        if token.text in POLITE_PRONOUNS:
            conflicting_pronoun = "তুমি"
        elif token.text in CASUAL_PRONOUNS:
            conflicting_pronoun = "আপনি"
        if conflicting_pronoun is None:
            continue
        source_text = text[:token.end] + f" {conflicting_pronoun}" + text[token.end:]
        issue_start = token.end + 1
        issue_end = issue_start + len(conflicting_pronoun)
        return [
            SyntheticRecord(
                source_text=source_text,
                target_text=text,
                issues=(
                    SyntheticIssue(
                        start=issue_start,
                        end=issue_end,
                        label="grammar",
                        subtype="formal_informal_mismatch",
                        fine_label="formal_informal_mismatch",
                        expected_text="",
                        observed_text=conflicting_pronoun,
                    ),
                ),
            )
        ]
    return []


def _word_order_records(text: str) -> list[SyntheticRecord]:
    tokens = _word_tokens(text)
    if len(tokens) < 3:
        return []
    left = tokens[-2]
    right = tokens[-1]
    swapped_phrase = f"{right.text}{text[left.end:right.start]}{left.text}"
    return [
        _replace_span(
            text,
            left.start,
            right.end,
            swapped_phrase,
            label="grammar",
            subtype="word_order",
            fine_label="word_order",
            expected_text=text[left.start:right.end],
            observed_text=swapped_phrase,
        )
    ]


def _mixed_digit_style_records(text: str) -> list[SyntheticRecord]:
    for index, character in enumerate(text):
        if "0" <= character <= "9":
            replacement = character.translate(LATIN_TO_BANGLA_DIGITS)
        elif "০" <= character <= "৯":
            replacement = character.translate(BANGLA_TO_LATIN_DIGITS)
        else:
            continue
        return [
            _replace_span(
                text,
                index,
                index + 1,
                replacement,
                label="grammar",
                subtype="mixed_digit_style",
                fine_label="mixed_digit_style",
                expected_text=character,
                observed_text=replacement,
            )
        ]
    return []


def _code_mix_records(text: str) -> list[SyntheticRecord]:
    for bangla_word, latin_word in sorted(CODE_MIX_REVERSE_MAP.items()):
        token = _find_token(text, bangla_word)
        if token is None:
            continue
        return [
            _replace_token(
                text,
                token,
                latin_word,
                label="grammar",
                subtype="code_mix",
                fine_label="code_mix",
                expected_text=bangla_word,
                observed_text=latin_word,
            )
        ]
    return []


def _replace_following_verb(
    text: str,
    tokens: list[TokenSpan],
    pronoun_index: int,
    correct_to_wrong_map: dict[str, str],
    *,
    subtype: str,
    fine_label: str,
) -> SyntheticRecord | None:
    looked_ahead_words = 0
    for candidate in tokens[pronoun_index + 1 :]:
        if _is_word(candidate.text):
            looked_ahead_words += 1
        if looked_ahead_words > LOOKAHEAD_WORD_LIMIT:
            break
        replacement = correct_to_wrong_map.get(candidate.text)
        if replacement is None:
            continue
        return _replace_token(
            text,
            candidate,
            replacement,
            label="grammar",
            subtype=subtype,
            fine_label=fine_label,
            expected_text=candidate.text,
            observed_text=replacement,
        )
    return None


def _replace_token(
    text: str,
    token: TokenSpan,
    replacement_text: str,
    *,
    label: str,
    subtype: str,
    fine_label: str | None = None,
    expected_text: str | None = None,
    observed_text: str | None = None,
    is_variant_only: bool = False,
) -> SyntheticRecord:
    return _replace_span(
        text,
        token.start,
        token.end,
        replacement_text,
        label=label,
        subtype=subtype,
        fine_label=fine_label,
        expected_text=expected_text,
        observed_text=observed_text,
        is_variant_only=is_variant_only,
    )


def _replace_span(
    text: str,
    start: int,
    end: int,
    replacement_text: str,
    *,
    label: str,
    subtype: str,
    fine_label: str | None = None,
    expected_text: str | None = None,
    observed_text: str | None = None,
    is_variant_only: bool = False,
) -> SyntheticRecord:
    coarse_label = label if label in COARSE_LABELS else "grammar"
    source_text = text[:start] + replacement_text + text[end:]
    return SyntheticRecord(
        source_text=source_text,
        target_text=text,
        issues=(
            SyntheticIssue(
                start=start,
                end=start + len(replacement_text),
                label=coarse_label,
                subtype=subtype,
                fine_label=fine_label,
                expected_text=expected_text,
                observed_text=observed_text or replacement_text,
                is_variant_only=is_variant_only,
            ),
        ),
    )


def _insert_text(
    text: str,
    position: int,
    inserted_text: str,
    *,
    label: str,
    subtype: str,
    fine_label: str | None = None,
    expected_text: str | None = None,
    observed_text: str | None = None,
) -> SyntheticRecord:
    coarse_label = label if label in COARSE_LABELS else "grammar"
    source_text = text[:position] + inserted_text + text[position:]
    issue_start = position
    issue_end = position + len(observed_text or inserted_text.strip())
    return SyntheticRecord(
        source_text=source_text,
        target_text=text,
        issues=(
            SyntheticIssue(
                start=issue_start,
                end=issue_end,
                label=coarse_label,
                subtype=subtype,
                fine_label=fine_label,
                expected_text=expected_text,
                observed_text=observed_text or inserted_text.strip(),
            ),
        ),
    )


def _remove_token_with_spacing(text: str, tokens: list[TokenSpan], token_index: int) -> tuple[str, int]:
    token = tokens[token_index]
    remove_start = token.start
    remove_end = token.end

    if token_index > 0 and text[remove_start - 1].isspace():
        remove_start -= 1
    elif remove_end < len(text) and text[remove_end].isspace():
        remove_end += 1

    return text[:remove_start] + text[remove_end:], remove_start


def _find_token(text: str, target_token: str) -> TokenSpan | None:
    for token in _word_tokens(text):
        if token.text == target_token:
            return token
    return None


def _word_tokens(text: str) -> list[TokenSpan]:
    return [token for token in _tokenize_with_offsets(text) if _is_word(token.text)]


def _tokenize_with_offsets(text: str) -> list[TokenSpan]:
    return [
        TokenSpan(
            text=match.group(0),
            start=match.start(),
            end=match.end(),
        )
        for match in TOKEN_PATTERN.finditer(text)
    ]


def _is_word(value: str) -> bool:
    return bool(BANGLA_WORD_PATTERN.fullmatch(value))


def _mismatched_pronoun(value: str) -> str | None:
    if value in FIRST_PERSON_PRONOUNS:
        return "তুমি"
    if value in CASUAL_PRONOUNS:
        return "আপনি"
    if value in POLITE_PRONOUNS or value in THIRD_PERSON_PRONOUNS:
        return "আমি"
    return None


def _dedupe_records(records: list[SyntheticRecord]) -> list[SyntheticRecord]:
    seen_keys: set[tuple[str, str, tuple[tuple[object, ...], ...]]] = set()
    deduped: list[SyntheticRecord] = []
    for record in records:
        issue_key = tuple(
            (
                issue.start,
                issue.end,
                issue.label,
                issue.subtype,
                issue.fine_label,
                issue.expected_text,
                issue.observed_text,
                issue.is_variant_only,
            )
            for issue in record.issues
        )
        key = (record.source_text, record.target_text, issue_key)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(record)
    return deduped


if __name__ == "__main__":
    main()
