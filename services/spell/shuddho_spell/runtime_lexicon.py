from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeLexicon:
    accepted_words: tuple[str, ...]
    candidate_words: tuple[str, ...]
    correction_map: dict[str, str]
    source: str


def load_runtime_lexicon(
    seed_path: Path,
    database_path: Path | None = None,
    *,
    use_sqlite_lexicon: bool = False,
    use_sqlite_correction_map: bool = True,
) -> RuntimeLexicon:
    seed_words = _load_seed_words(seed_path)
    correction_map: dict[str, str] = {}
    accepted_words = list(seed_words)
    source = "seed"

    if database_path is not None and database_path.exists() and use_sqlite_correction_map:
        try:
            correction_map = _load_sqlite_correction_map(database_path)
        except (OSError, sqlite3.Error, ValueError):
            correction_map = {}
        else:
            accepted_words = _merge_words(seed_words, tuple(correction_map.values()))
            if correction_map:
                source = "seed+sqlite_corrections"

    if database_path is not None and database_path.exists() and use_sqlite_lexicon:
        try:
            sqlite_words = _load_sqlite_words(database_path)
        except (OSError, sqlite3.Error, ValueError):
            sqlite_words = None
        else:
            if sqlite_words:
                accepted_words = list(sqlite_words)
                source = "sqlite"

    return RuntimeLexicon(
        accepted_words=tuple(accepted_words),
        candidate_words=tuple(accepted_words),
        correction_map=correction_map,
        source=source,
    )


def _load_sqlite_words(database_path: Path) -> tuple[str, ...]:
    query = """
        SELECT normalized_word, word
        FROM words_clean
        WHERE is_active = 1 AND is_trusted = 1
        ORDER BY is_common DESC, row_order ASC
    """
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(query).fetchall()
    words = _collect_unique_words(rows)
    if not words:
        raise ValueError(f"{database_path} does not contain any active trusted lexicon rows.")
    return words


def _load_sqlite_correction_map(database_path: Path) -> dict[str, str]:
    query = """
        SELECT word, normalized_word
        FROM words_clean
        WHERE is_active = 1
          AND is_trusted = 1
          AND word != normalized_word
        ORDER BY is_common DESC, row_order ASC
    """
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(query).fetchall()

    correction_map: dict[str, str] = {}
    for raw_word, normalized_word in rows:
        raw_form = _clean_word(raw_word)
        canonical_word = _clean_word(normalized_word)
        if not raw_form or not canonical_word or raw_form in correction_map:
            continue
        correction_map[raw_form] = canonical_word
    return correction_map


def _load_seed_words(seed_path: Path) -> tuple[str, ...]:
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

    return tuple(ordered_words)


def _collect_unique_words(rows: list[tuple[str, str]]) -> tuple[str, ...]:
    ordered_words: list[str] = []
    seen_words: set[str] = set()

    for normalized_word, fallback_word in rows:
        word = _clean_word(normalized_word or fallback_word)
        if not word or word in seen_words:
            continue
        seen_words.add(word)
        ordered_words.append(word)

    return tuple(ordered_words)


def _merge_words(primary_words: tuple[str, ...], extra_words: tuple[str, ...]) -> list[str]:
    merged = list(primary_words)
    seen_words = set(primary_words)

    for word in extra_words:
        if not word or word in seen_words:
            continue
        seen_words.add(word)
        merged.append(word)

    return merged


def _clean_word(value: str) -> str:
    return value.strip()
