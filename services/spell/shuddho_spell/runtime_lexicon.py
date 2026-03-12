from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REQUIRED_COLUMNS = ("word", "normalized_word", "source", "is_trusted", "is_common", "is_active")
TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}


@dataclass(frozen=True)
class RuntimeLexicon:
    accepted_words: tuple[str, ...]
    candidate_words: tuple[str, ...]
    correction_map: dict[str, str]
    source: str


def load_runtime_lexicon(
    clean_csv_path: Path,
    *,
    fallback_seed_path: Path | None = None,
) -> RuntimeLexicon:
    if clean_csv_path.exists():
        runtime_lexicon = _load_runtime_lexicon_from_csv(clean_csv_path)
        if runtime_lexicon.correction_map:
            return runtime_lexicon

    if fallback_seed_path is not None and fallback_seed_path.exists():
        return _load_seed_fallback(fallback_seed_path)

    raise FileNotFoundError(f"Missing runtime lexicon source: {clean_csv_path}")


def _load_runtime_lexicon_from_csv(clean_csv_path: Path) -> RuntimeLexicon:
    accepted_words: list[str] = []
    seen_words: set[str] = set()
    correction_map: dict[str, str] = {}

    with clean_csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, clean_csv_path)

        for row_index, row in enumerate(reader, start=1):
            if not _parse_bool(row.get("is_active"), "is_active", clean_csv_path, row_index):
                continue
            if not _parse_bool(row.get("is_trusted"), "is_trusted", clean_csv_path, row_index):
                continue

            raw_word = _require_text(row, "word", clean_csv_path, row_index)
            canonical_word = _require_text(row, "normalized_word", clean_csv_path, row_index)
            if raw_word == canonical_word:
                continue
            if raw_word in correction_map:
                continue

            correction_map[raw_word] = canonical_word
            if canonical_word in seen_words:
                continue
            seen_words.add(canonical_word)
            accepted_words.append(canonical_word)

    return RuntimeLexicon(
        accepted_words=tuple(accepted_words),
        candidate_words=tuple(accepted_words),
        correction_map=correction_map,
        source="words_clean.csv",
    )


def _load_seed_fallback(seed_path: Path) -> RuntimeLexicon:
    words: list[str] = []
    seen_words: set[str] = set()

    for line in seed_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        word = stripped.split("\t")[0].strip()
        if not word or word in seen_words:
            continue
        seen_words.add(word)
        words.append(word)

    return RuntimeLexicon(
        accepted_words=tuple(words),
        candidate_words=tuple(words),
        correction_map={},
        source="seed_fallback",
    )


def _require_columns(fieldnames: list[str] | None, csv_path: Path) -> None:
    if fieldnames is None:
        raise ValueError(f"{csv_path} is missing a header row.")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing_columns:
        raise ValueError(f"{csv_path} is missing expected columns: {', '.join(missing_columns)}")


def _require_text(row: dict[str, str | None], key: str, csv_path: Path, row_index: int) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{csv_path} row {row_index} has an empty {key!r} value.")
    return value


def _parse_bool(value: str | None, key: str, csv_path: Path, row_index: int) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{csv_path} row {row_index} has an invalid boolean value for {key!r}: {value!r}")
