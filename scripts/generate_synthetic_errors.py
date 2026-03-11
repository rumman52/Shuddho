from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.constants.bangla import SAFE_EXACT_TYPOS


def create_variants(text: str) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    words = text.split()

    if len(words) >= 2:
        duplicated = words[:]
        duplicated.insert(1, duplicated[1])
        variants.append({"source_text": " ".join(duplicated), "target_text": text})

    if "।" in text:
        variants.append({"source_text": text.replace("।", " ।"), "target_text": text})

    for typo, correction in SAFE_EXACT_TYPOS.items():
        if correction in text:
            variants.append({"source_text": text.replace(correction, typo), "target_text": text})

    return variants


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Bangla error pairs.")
    parser.add_argument("--input", required=True, help="Clean corpus text file.")
    parser.add_argument("--output", required=True, help="JSONL output path.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    records: list[dict[str, str]] = []

    for line in input_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.extend(create_variants(stripped))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8")


if __name__ == "__main__":
    main()

