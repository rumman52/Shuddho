from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SPECIAL_TOKENS = ("<pad>", "<bos>", "<eos>", "<unk>")


@dataclass(frozen=True)
class CorrectorExample:
    source_text: str
    target_text: str


def load_corrector_examples(path: str | Path) -> list[CorrectorExample]:
    records: list[CorrectorExample] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        source_text = str(payload.get("source_text", "")).strip()
        target_text = str(payload.get("target_text", "")).strip()
        if not source_text or not target_text:
            continue
        records.append(CorrectorExample(source_text=source_text, target_text=target_text))
    return records


def split_examples(
    examples: list[CorrectorExample],
    *,
    validation_ratio: float,
    seed: int,
) -> tuple[list[CorrectorExample], list[CorrectorExample]]:
    if not examples:
        return [], []
    if validation_ratio <= 0:
        return list(examples), []

    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    validation_count = max(1, int(len(shuffled) * validation_ratio))
    validation_examples = shuffled[:validation_count]
    train_examples = shuffled[validation_count:] or shuffled[:1]
    return train_examples, validation_examples


class CharacterTokenizer:
    def __init__(self, tokens: list[str]) -> None:
        ordered_tokens = [*SPECIAL_TOKENS]
        for token in tokens:
            if token in ordered_tokens:
                continue
            ordered_tokens.append(token)
        self.tokens = ordered_tokens
        self.token_to_id = {token: index for index, token in enumerate(self.tokens)}

    @classmethod
    def train(
        cls,
        texts: list[str],
        *,
        max_vocab_size: int | None = None,
        min_frequency: int = 1,
    ) -> "CharacterTokenizer":
        frequencies = Counter(character for text in texts for character in text)
        ordered_items = sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
        filtered_tokens = [
            token
            for token, frequency in ordered_items
            if frequency >= min_frequency and token not in SPECIAL_TOKENS
        ]
        if max_vocab_size is not None:
            available_size = max(max_vocab_size - len(SPECIAL_TOKENS), 0)
            filtered_tokens = filtered_tokens[:available_size]
        return cls(filtered_tokens)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "CharacterTokenizer":
        raw_tokens = payload.get("tokens", [])
        if not isinstance(raw_tokens, list):
            raise ValueError("Tokenizer payload is missing the 'tokens' list.")
        tokens = [str(token) for token in raw_tokens]
        return cls(tokens)

    @property
    def vocab_size(self) -> int:
        return len(self.tokens)

    @property
    def pad_token_id(self) -> int:
        return self.token_to_id["<pad>"]

    @property
    def bos_token_id(self) -> int:
        return self.token_to_id["<bos>"]

    @property
    def eos_token_id(self) -> int:
        return self.token_to_id["<eos>"]

    @property
    def unk_token_id(self) -> int:
        return self.token_to_id["<unk>"]

    def encode(
        self,
        text: str,
        *,
        add_bos: bool = False,
        add_eos: bool = True,
        max_length: int | None = None,
    ) -> list[int]:
        token_ids: list[int] = []
        if add_bos:
            token_ids.append(self.bos_token_id)
        token_ids.extend(self.token_to_id.get(character, self.unk_token_id) for character in text)
        if add_eos:
            token_ids.append(self.eos_token_id)
        if max_length is not None:
            token_ids = token_ids[:max_length]
            if add_eos and token_ids and token_ids[-1] != self.eos_token_id:
                token_ids[-1] = self.eos_token_id
        return token_ids

    def decode(
        self,
        token_ids: list[int] | tuple[int, ...],
        *,
        stop_at_eos: bool = True,
        skip_special_tokens: bool = True,
    ) -> str:
        characters: list[str] = []
        special_tokens = set(SPECIAL_TOKENS)
        for token_id in token_ids:
            token = self.tokens[token_id] if 0 <= token_id < len(self.tokens) else "<unk>"
            if stop_at_eos and token == "<eos>":
                break
            if skip_special_tokens and token in special_tokens:
                continue
            characters.append(token)
        return "".join(characters)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "character",
            "tokens": list(self.tokens),
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "CharacterTokenizer":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Tokenizer file must contain a JSON object.")
        return cls.from_dict(payload)
