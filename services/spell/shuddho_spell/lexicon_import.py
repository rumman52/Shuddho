from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


CLEAN_COLUMNS = ("word", "normalized_word", "source", "is_trusted", "is_common", "is_active")
REVIEW_COLUMNS = ("original_word", "normalized_word", "reasons")
SUMMARY_INT_KEYS = {
    "raw_tokens": "raw_tokens",
    "clean_unique_rows_exported": "clean_unique_rows_exported",
    "duplicates_removed": "duplicates_removed",
    "hard_rejected": "hard_rejected",
    "flagged_for_review": "flagged_for_review",
}
TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}


@dataclass(frozen=True)
class LexiconImportPaths:
    clean_csv_path: Path
    review_csv_path: Path
    summary_path: Path
    database_path: Path
    seed_lexicon_path: Path

    @classmethod
    def defaults(cls, repo_root: Path | None = None) -> "LexiconImportPaths":
        root = repo_root or Path(__file__).resolve().parents[3]
        return cls(
            clean_csv_path=root / "data" / "imports" / "lexicon" / "words_clean.csv",
            review_csv_path=root / "data" / "imports" / "lexicon" / "words_review_flagged.csv",
            summary_path=root / "data" / "imports" / "lexicon" / "cleaning_summary.txt",
            database_path=root / "data" / "shuddho_lexicon.db",
            seed_lexicon_path=root / "services" / "spell" / "data" / "seed_lexicon.txt",
        )


@dataclass(frozen=True)
class ParsedImportReport:
    raw_summary_text: str
    raw_tokens: int | None
    clean_unique_rows_exported: int | None
    duplicates_removed: int | None
    hard_rejected: int | None
    flagged_for_review: int | None
    sample_cleaned_words: list[str]


@dataclass(frozen=True)
class LexiconImportResult:
    database_path: Path
    clean_rows: int
    review_rows: int
    report_rows: int


def import_lexicon_to_sqlite(paths: LexiconImportPaths | None = None) -> LexiconImportResult:
    resolved_paths = paths or LexiconImportPaths.defaults()
    _validate_source_paths(resolved_paths)

    resolved_paths.database_path.parent.mkdir(parents=True, exist_ok=True)
    temp_database_path = resolved_paths.database_path.with_suffix(f"{resolved_paths.database_path.suffix}.tmp")
    if temp_database_path.exists():
        temp_database_path.unlink()

    try:
        clean_rows, review_rows = _build_database(temp_database_path, resolved_paths)
        temp_database_path.replace(resolved_paths.database_path)
    finally:
        if temp_database_path.exists():
            temp_database_path.unlink()

    return LexiconImportResult(
        database_path=resolved_paths.database_path,
        clean_rows=clean_rows,
        review_rows=review_rows,
        report_rows=1,
    )


def export_seed_lexicon(
    database_path: Path,
    output_path: Path | None = None,
    *,
    only_active: bool = True,
) -> int:
    seed_output_path = output_path or LexiconImportPaths.defaults().seed_lexicon_path
    query = """
        SELECT normalized_word, word
        FROM words_clean
        {where_clause}
        ORDER BY row_order ASC
    """
    where_clause = "WHERE is_active = 1" if only_active else ""
    with closing(sqlite3.connect(database_path)) as connection:
        cursor = connection.execute(query.format(where_clause=where_clause))
        words = _collect_unique_export_words(cursor.fetchall())

    seed_output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Exported from data/shuddho_lexicon.db via scripts/import_lexicon_to_sqlite.py",
        *words,
    ]
    seed_output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(words)


def _build_database(database_path: Path, paths: LexiconImportPaths) -> tuple[int, int]:
    report = parse_import_report(paths.summary_path)
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            _create_schema(connection)
            connection.executemany(
                """
                INSERT OR IGNORE INTO words_clean (
                    row_order,
                    word,
                    normalized_word,
                    source,
                    is_trusted,
                    is_common,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                _iter_clean_rows(paths.clean_csv_path),
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO words_review_flagged (
                    row_order,
                    original_word,
                    normalized_word,
                    reasons,
                    reason_count
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                _iter_review_rows(paths.review_csv_path),
            )
            connection.execute(
                """
                INSERT INTO import_reports (
                    clean_source_path,
                    review_source_path,
                    summary_source_path,
                    raw_tokens,
                    clean_unique_rows_exported,
                    duplicates_removed,
                    hard_rejected,
                    flagged_for_review,
                    sample_cleaned_words,
                    raw_summary_text,
                    imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(paths.clean_csv_path),
                    str(paths.review_csv_path),
                    str(paths.summary_path),
                    report.raw_tokens,
                    report.clean_unique_rows_exported,
                    report.duplicates_removed,
                    report.hard_rejected,
                    report.flagged_for_review,
                    "\n".join(report.sample_cleaned_words),
                    report.raw_summary_text,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            _create_indexes(connection)
            clean_rows = _count_rows(connection, "words_clean")
            review_rows = _count_rows(connection, "words_review_flagged")
    return clean_rows, review_rows


def parse_import_report(summary_path: Path) -> ParsedImportReport:
    raw_summary_text = summary_path.read_text(encoding="utf-8-sig")
    metrics: dict[str, int | None] = {value: None for value in SUMMARY_INT_KEYS.values()}
    sample_cleaned_words: list[str] = []
    in_sample_section = False

    for line in raw_summary_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() == "sample cleaned words:":
            in_sample_section = True
            continue
        if in_sample_section:
            sample_cleaned_words.append(stripped)
            continue
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", maxsplit=1)
        normalized_key = key.strip().lower().replace(" ", "_")
        metric_key = SUMMARY_INT_KEYS.get(normalized_key)
        if metric_key is None:
            continue
        metrics[metric_key] = _parse_optional_int(raw_value.strip())

    return ParsedImportReport(
        raw_summary_text=raw_summary_text,
        raw_tokens=metrics["raw_tokens"],
        clean_unique_rows_exported=metrics["clean_unique_rows_exported"],
        duplicates_removed=metrics["duplicates_removed"],
        hard_rejected=metrics["hard_rejected"],
        flagged_for_review=metrics["flagged_for_review"],
        sample_cleaned_words=sample_cleaned_words,
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE words_clean (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_order INTEGER NOT NULL,
            word TEXT NOT NULL,
            normalized_word TEXT NOT NULL,
            source TEXT NOT NULL,
            is_trusted INTEGER NOT NULL CHECK (is_trusted IN (0, 1)),
            is_common INTEGER NOT NULL CHECK (is_common IN (0, 1)),
            is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
            UNIQUE (word, normalized_word, source)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE words_review_flagged (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_order INTEGER NOT NULL,
            original_word TEXT NOT NULL,
            normalized_word TEXT NOT NULL,
            reasons TEXT NOT NULL,
            reason_count INTEGER NOT NULL CHECK (reason_count >= 0),
            UNIQUE (original_word, normalized_word, reasons)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE import_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clean_source_path TEXT NOT NULL,
            review_source_path TEXT NOT NULL,
            summary_source_path TEXT NOT NULL,
            raw_tokens INTEGER,
            clean_unique_rows_exported INTEGER,
            duplicates_removed INTEGER,
            hard_rejected INTEGER,
            flagged_for_review INTEGER,
            sample_cleaned_words TEXT NOT NULL,
            raw_summary_text TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
        """
    )


def _create_indexes(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE INDEX idx_words_clean_word ON words_clean (word)")
    connection.execute("CREATE INDEX idx_words_clean_normalized_word ON words_clean (normalized_word)")
    connection.execute("CREATE INDEX idx_words_review_flagged_original_word ON words_review_flagged (original_word)")
    connection.execute("CREATE INDEX idx_words_review_flagged_normalized_word ON words_review_flagged (normalized_word)")


def _iter_clean_rows(csv_path: Path) -> Iterator[tuple[int, str, str, str, int, int, int]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, CLEAN_COLUMNS, csv_path)
        for row_order, row in enumerate(reader, start=1):
            yield (
                row_order,
                _require_text(row, "word", csv_path, row_order),
                _require_text(row, "normalized_word", csv_path, row_order),
                _require_text(row, "source", csv_path, row_order),
                _parse_bool_flag(row.get("is_trusted"), "is_trusted", csv_path, row_order),
                _parse_bool_flag(row.get("is_common"), "is_common", csv_path, row_order),
                _parse_bool_flag(row.get("is_active"), "is_active", csv_path, row_order),
            )


def _iter_review_rows(csv_path: Path) -> Iterator[tuple[int, str, str, str, int]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, REVIEW_COLUMNS, csv_path)
        for row_order, row in enumerate(reader, start=1):
            normalized_reasons = _normalize_reasons(row.get("reasons"))
            yield (
                row_order,
                _require_text(row, "original_word", csv_path, row_order),
                _require_text(row, "normalized_word", csv_path, row_order),
                normalized_reasons,
                0 if not normalized_reasons else len(normalized_reasons.split("|")),
            )


def _require_columns(fieldnames: list[str] | None, required_columns: tuple[str, ...], csv_path: Path) -> None:
    if fieldnames is None:
        raise ValueError(f"{csv_path} is missing a header row.")
    missing_columns = [column for column in required_columns if column not in fieldnames]
    if missing_columns:
        raise ValueError(f"{csv_path} is missing expected columns: {', '.join(missing_columns)}")


def _require_text(row: dict[str, str | None], key: str, csv_path: Path, row_order: int) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{csv_path} row {row_order} has an empty {key!r} value.")
    return value


def _parse_bool_flag(value: str | None, key: str, csv_path: Path, row_order: int) -> int:
    normalized = (value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return 1
    if normalized in FALSE_VALUES:
        return 0
    raise ValueError(f"{csv_path} row {row_order} has an invalid boolean value for {key!r}: {value!r}")


def _normalize_reasons(value: str | None) -> str:
    if value is None:
        return ""
    normalized_parts = [part.strip() for part in value.split("|") if part.strip()]
    return "|".join(normalized_parts)


def _parse_optional_int(value: str) -> int | None:
    digits_only = value.replace(",", "").strip()
    if not digits_only:
        return None
    return int(digits_only)


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0]) if row is not None else 0


def _collect_unique_export_words(rows: Iterable[tuple[str, str]]) -> list[str]:
    exported_words: list[str] = []
    seen_words: set[str] = set()
    for normalized_word, fallback_word in rows:
        candidate = (normalized_word or fallback_word).strip()
        if not candidate or candidate in seen_words:
            continue
        seen_words.add(candidate)
        exported_words.append(candidate)
    return exported_words


def _validate_source_paths(paths: LexiconImportPaths) -> None:
    for source_path in (paths.clean_csv_path, paths.review_csv_path, paths.summary_path):
        if not source_path.exists():
            raise FileNotFoundError(f"Missing lexicon import source: {source_path}")
