from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SPACE_EQUIVALENTS = {
    "\t": " ",
    "\u00A0": " ",
    "\u1680": " ",
    "\u2000": " ",
    "\u2001": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2004": " ",
    "\u2005": " ",
    "\u2006": " ",
    "\u2007": " ",
    "\u2008": " ",
    "\u2009": " ",
    "\u200A": " ",
    "\u202F": " ",
    "\u205F": " ",
    "\u3000": " "
}
INVISIBLE_CHARS = {"\u200B", "\u2060", "\uFEFF"}
PUNCTUATION_EQUIVALENTS = {
    "“": "\"",
    "”": "\"",
    "„": "\"",
    "‘": "'",
    "’": "'",
    "‚": ",",
    "，": ",",
    "؛": ";",
    "॥": "।",
    "…": "..."
}
PUNCTUATION_WITHOUT_LEADING_SPACE = {",", ".", ";", ":", "!", "?", "।"}


@dataclass(frozen=True)
class NormalizedText:
    original_text: str
    text: str
    index_map: list[int]

    def to_original_span(self, start: int, end: int) -> tuple[int, int]:
        if not self.original_text:
            return 0, 0
        if start >= len(self.index_map):
            return len(self.original_text), len(self.original_text)
        mapped_start = self.index_map[max(start, 0)]
        if end <= 0:
            return mapped_start, mapped_start
        if end - 1 >= len(self.index_map):
            return mapped_start, len(self.original_text)
        mapped_end = self.index_map[end - 1] + 1
        return mapped_start, mapped_end


class BanglaNormalizer:
    def normalize(self, text: str) -> NormalizedText:
        items = [(character, index) for index, character in enumerate(text)]
        items = self._normalize_newlines(items)
        items = self._cleanup_unicode(items)
        items = self._normalize_punctuation(items)
        items = self._collapse_spaces(items)
        normalized_text = "".join(character for character, _ in items).strip()
        index_map = [index for _, index in items][: len(normalized_text)]
        if normalized_text != "".join(character for character, _ in items):
            normalized_text, index_map = self._trim_edges(items)
        return NormalizedText(original_text=text, text=normalized_text, index_map=index_map)

    def _normalize_newlines(self, items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        normalized: list[tuple[str, int]] = []
        position = 0
        while position < len(items):
            character, index = items[position]
            if character == "\r":
                normalized.append(("\n", index))
                if position + 1 < len(items) and items[position + 1][0] == "\n":
                    position += 2
                    continue
            else:
                normalized.append((character, index))
            position += 1
        return normalized

    def _cleanup_unicode(self, items: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
        cleaned: list[tuple[str, int]] = []
        for character, index in items:
            if character in INVISIBLE_CHARS:
                continue
            cleaned.append((SPACE_EQUIVALENTS.get(character, character), index))
        return cleaned

    def _normalize_punctuation(self, items: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
        normalized: list[tuple[str, int]] = []
        for character, index in items:
            replacement = PUNCTUATION_EQUIVALENTS.get(character, character)
            for replacement_character in replacement:
                normalized.append((replacement_character, index))
        return normalized

    def _collapse_spaces(self, items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        normalized: list[tuple[str, int]] = []
        pending_space: tuple[str, int] | None = None
        for character, index in items:
            if character == " ":
                if pending_space is None:
                    pending_space = (" ", index)
                continue
            if character == "\n":
                pending_space = None
                if normalized and normalized[-1][0] != "\n":
                    normalized.append((character, index))
                continue
            if pending_space is not None:
                if character not in PUNCTUATION_WITHOUT_LEADING_SPACE and normalized and normalized[-1][0] != "\n":
                    normalized.append(pending_space)
                pending_space = None
            normalized.append((character, index))
        return normalized

    def _trim_edges(self, items: list[tuple[str, int]]) -> tuple[str, list[int]]:
        start = 0
        end = len(items)
        while start < end and items[start][0].isspace():
            start += 1
        while end > start and items[end - 1][0].isspace():
            end -= 1
        trimmed = items[start:end]
        return "".join(character for character, _ in trimmed), [index for _, index in trimmed]

