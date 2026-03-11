from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a custom SentencePiece tokenizer for Shuddho.")
    parser.add_argument("--input", required=True, help="Path to cleaned corpus text file.")
    parser.add_argument("--model-prefix", required=True, help="Output model prefix.")
    parser.add_argument("--vocab-size", type=int, default=4000, help="Tokenizer vocabulary size.")
    parser.add_argument("--character-coverage", type=float, default=0.9995)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        import sentencepiece as spm
    except ImportError as error:  # pragma: no cover - depends on optional install
        raise RuntimeError("sentencepiece is not installed") from error

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    spm.SentencePieceTrainer.Train(
        input=str(input_path),
        model_prefix=args.model_prefix,
        vocab_size=args.vocab_size,
        model_type="unigram",
        character_coverage=args.character_coverage,
        normalization_rule_name="identity"
    )


if __name__ == "__main__":
    main()

