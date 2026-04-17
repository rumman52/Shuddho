from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_COLUMNS = ("word", "normalized_word", "source", "is_trusted", "is_common", "is_active")
TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}


@dataclass(frozen=True)
class RuntimeLexiconSnapshot:
    accepted_words: tuple[str, ...]
    candidate_words: tuple[str, ...]
    correction_map: dict[str, str]
    runtime_source: str
    runtime_source_of_truth: str
    runtime_path: Path | None
    runtime_exists: bool
    version: str | None
    checksum: str | None
    accepted_word_count: int
    candidate_word_count: int
    correction_map_count: int
    import_database_path: Path | None
    import_database_exists: bool
    loaded_at: datetime


class LexiconRepository:
    def __init__(
        self,
        clean_csv_path: Path,
        *,
        fallback_seed_path: Path | None = None,
        import_database_path: Path | None = None,
    ) -> None:
        self.clean_csv_path = clean_csv_path
        self.fallback_seed_path = fallback_seed_path
        self.import_database_path = import_database_path
        self._snapshot = self._load_snapshot()

    @property
    def snapshot(self) -> RuntimeLexiconSnapshot:
        return self._snapshot

    def reload(self) -> RuntimeLexiconSnapshot:
        self._snapshot = self._load_snapshot()
        return self._snapshot

    def _load_snapshot(self) -> RuntimeLexiconSnapshot:
        if self.clean_csv_path.exists():
            accepted_words, candidate_words, correction_map = _load_runtime_lexicon_from_csv(self.clean_csv_path)
            checksum = _checksum_path(self.clean_csv_path)
            version = checksum[:12] if checksum else None
            return RuntimeLexiconSnapshot(
                accepted_words=accepted_words,
                candidate_words=candidate_words,
                correction_map=correction_map,
                runtime_source="words_clean.csv",
                runtime_source_of_truth="csv_runtime",
                runtime_path=self.clean_csv_path,
                runtime_exists=True,
                version=version,
                checksum=checksum,
                accepted_word_count=len(accepted_words),
                candidate_word_count=len(candidate_words),
                correction_map_count=len(correction_map),
                import_database_path=self.import_database_path,
                import_database_exists=bool(self.import_database_path and self.import_database_path.exists()),
                loaded_at=datetime.now(timezone.utc),
            )

        if self.fallback_seed_path is not None and self.fallback_seed_path.exists():
            accepted_words = _load_seed_fallback(self.fallback_seed_path)
            checksum = _checksum_path(self.fallback_seed_path)
            version = checksum[:12] if checksum else None
            return RuntimeLexiconSnapshot(
                accepted_words=accepted_words,
                candidate_words=accepted_words,
                correction_map={},
                runtime_source="seed_fallback",
                runtime_source_of_truth="seed_fallback",
                runtime_path=self.fallback_seed_path,
                runtime_exists=True,
                version=version,
                checksum=checksum,
                accepted_word_count=len(accepted_words),
                candidate_word_count=len(accepted_words),
                correction_map_count=0,
                import_database_path=self.import_database_path,
                import_database_exists=bool(self.import_database_path and self.import_database_path.exists()),
                loaded_at=datetime.now(timezone.utc),
            )

        raise FileNotFoundError(f"Missing runtime lexicon source: {self.clean_csv_path}")


def _load_runtime_lexicon_from_csv(clean_csv_path: Path) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]:
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
            if canonical_word not in seen_words:
                seen_words.add(canonical_word)
                accepted_words.append(canonical_word)

            if raw_word == canonical_word:
                continue
            if raw_word in correction_map:
                continue

            correction_map[raw_word] = canonical_word

    accepted = tuple(accepted_words)
    return accepted, accepted, correction_map


def _load_seed_fallback(seed_path: Path) -> tuple[str, ...]:
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

    return tuple(words)


def _checksum_path(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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
