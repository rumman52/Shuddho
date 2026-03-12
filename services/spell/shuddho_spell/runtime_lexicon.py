from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeLexicon:
    ordered_words: tuple[str, ...]
    correction_map: dict[str, str]
    source: str


def load_runtime_lexicon(seed_path: Path, database_path: Path | None = None) -> RuntimeLexicon:
    if database_path is not None and database_path.exists():
        try:
            sqlite_lexicon = _load_sqlite_lexicon(database_path)
        except (OSError, sqlite3.Error, ValueError):
            sqlite_lexicon = None
        else:
            if sqlite_lexicon.ordered_words:
                return sqlite_lexicon
    return _load_seed_lexicon(seed_path)


def _load_sqlite_lexicon(database_path: Path) -> RuntimeLexicon:
    query = """
        SELECT word, normalized_word
        FROM words_clean
        WHERE is_active = 1 AND is_trusted = 1
        ORDER BY is_common DESC, row_order ASC
    """
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(query).fetchall()

    if not rows:
        raise ValueError(f"{database_path} does not contain any active trusted lexicon rows.")

    ordered_words: list[str] = []
    seen_words: set[str] = set()
    raw_pairs: list[tuple[str, str]] = []

    for raw_word, normalized_word in rows:
        canonical_word = _clean_word(normalized_word or raw_word)
        if not canonical_word:
            continue
        if canonical_word not in seen_words:
            seen_words.add(canonical_word)
            ordered_words.append(canonical_word)

        raw_form = _clean_word(raw_word)
        if raw_form and raw_form != canonical_word:
            raw_pairs.append((raw_form, canonical_word))

    accepted_words = set(ordered_words)
    correction_map: dict[str, str] = {}
    for raw_form, canonical_word in raw_pairs:
        if raw_form in accepted_words or raw_form in correction_map:
            continue
        correction_map[raw_form] = canonical_word

    return RuntimeLexicon(
        ordered_words=tuple(ordered_words),
        correction_map=correction_map,
        source="sqlite",
    )


def _load_seed_lexicon(seed_path: Path) -> RuntimeLexicon:
    ordered_words: list[str] = []
    seen_words: set[str] = set()

    for line in seed_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        word = _clean_word(stripped.split("\t")[0])
        if not word or word in seen_words:
            continue
        seen_words.add(word)
        ordered_words.append(word)

    return RuntimeLexicon(
        ordered_words=tuple(ordered_words),
        correction_map={},
        source="seed",
    )


def _clean_word(value: str) -> str:
    return value.strip()
