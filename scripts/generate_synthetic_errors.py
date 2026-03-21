from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from shared.constants.bangla import CURATED_VARIANT_CORRECTIONS, SAFE_EXACT_TYPOS


@dataclass(frozen=True)
class SyntheticIssue:
    start: int
    end: int
    label: str
    subtype: str


@dataclass(frozen=True)
class SyntheticRecord:
    source_text: str
    target_text: str
    issues: tuple[SyntheticIssue, ...]

    def as_combined_record(self) -> dict[str, object]:
        return {
            "input_text": self.source_text,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "issues": [asdict(issue) for issue in self.issues],
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
            "issues": [asdict(issue) for issue in self.issues],
        }


def create_variants(text: str) -> list[SyntheticRecord]:
    variants: list[SyntheticRecord] = []
    words = text.split()

    if len(words) >= 2:
        duplicated_words = [words[0], words[0], *words[1:]]
        source_text = " ".join(duplicated_words)
        variants.append(
            SyntheticRecord(
                source_text=source_text,
                target_text=text,
                issues=(
                    SyntheticIssue(
                        start=0,
                        end=len(f"{words[0]} {words[0]}"),
                        label="grammar",
                        subtype="repeated_word",
                    ),
                ),
            )
        )

    punctuation_index = text.find("।")
    if punctuation_index >= 0:
        spaced_text = f"{text[:punctuation_index]} ।{text[punctuation_index + 1:]}"
        variants.append(
            SyntheticRecord(
                source_text=spaced_text,
                target_text=text,
                issues=(
                    SyntheticIssue(
                        start=punctuation_index,
                        end=punctuation_index + 2,
                        label="spacing",
                        subtype="space_before_punctuation",
                    ),
                ),
            )
        )

        duplicated_punctuation = f"{text[:punctuation_index]}।।{text[punctuation_index + 1:]}"
        variants.append(
            SyntheticRecord(
                source_text=duplicated_punctuation,
                target_text=text,
                issues=(
                    SyntheticIssue(
                        start=punctuation_index,
                        end=punctuation_index + 2,
                        label="punctuation",
                        subtype="duplicate_punctuation",
                    ),
                ),
            )
        )

    variants.extend(_spelling_variants(text, SAFE_EXACT_TYPOS, subtype="safe_exact_typo"))
    variants.extend(_spelling_variants(text, CURATED_VARIANT_CORRECTIONS, subtype="variant_mapping"))
    return _dedupe_records(variants)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Bangla error records for Shuddho.")
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
    output_path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8")


def _spelling_variants(
    text: str,
    mapping: dict[str, str],
    *,
    subtype: str,
) -> list[SyntheticRecord]:
    variants: list[SyntheticRecord] = []
    for wrong_form, correct_form in mapping.items():
        source_term = correct_form
        replacement_term = wrong_form
        match_index = text.find(source_term)
        if match_index < 0:
            continue

        source_text = text.replace(source_term, replacement_term, 1)
        variants.append(
            SyntheticRecord(
                source_text=source_text,
                target_text=text,
                issues=(
                    SyntheticIssue(
                        start=match_index,
                        end=match_index + len(replacement_term),
                        label="spelling",
                        subtype=subtype,
                    ),
                ),
            )
        )
    return variants


def _dedupe_records(records: list[SyntheticRecord]) -> list[SyntheticRecord]:
    seen_keys: set[tuple[str, str, tuple[tuple[int, int, str, str], ...]]] = set()
    deduped: list[SyntheticRecord] = []
    for record in records:
        key = (
            record.source_text,
            record.target_text,
            tuple((issue.start, issue.end, issue.label, issue.subtype) for issue in record.issues),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(record)
    return deduped


if __name__ == "__main__":
    main()
