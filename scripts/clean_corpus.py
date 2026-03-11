from __future__ import annotations

import argparse
from pathlib import Path

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a raw Bangla corpus into a cleaned text file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    normalizer = BanglaNormalizer()
    input_path = Path(args.input)
    output_path = Path(args.output)

    lines = input_path.read_text(encoding="utf-8").splitlines()
    cleaned = [normalizer.normalize(line).text for line in lines if line.strip()]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(cleaned), encoding="utf-8")


if __name__ == "__main__":
    main()

