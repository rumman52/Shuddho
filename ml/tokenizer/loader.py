from __future__ import annotations

from pathlib import Path


class TokenizerLoader:
    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)

    def load(self):  # type: ignore[no-untyped-def]
        try:
            import sentencepiece as spm
        except ImportError as error:  # pragma: no cover - depends on optional install
            raise RuntimeError("sentencepiece is required to load tokenizer models") from error

        if not self.model_path.exists():
            raise FileNotFoundError(f"Tokenizer model not found: {self.model_path}")

        return spm.SentencePieceProcessor(model_file=str(self.model_path))

