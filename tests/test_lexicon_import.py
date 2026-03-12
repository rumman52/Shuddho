from __future__ import annotations

import sqlite3
from pathlib import Path
from textwrap import dedent

from services.spell.shuddho_spell.lexicon_import import LexiconImportPaths, export_seed_lexicon, import_lexicon_to_sqlite


def test_import_lexicon_to_sqlite_creates_expected_tables_and_indexes(tmp_path: Path) -> None:
    paths = _write_import_fixture(tmp_path)

    result = import_lexicon_to_sqlite(paths)

    assert result.clean_rows == 2
    assert result.review_rows == 2
    assert result.report_rows == 1
    assert result.database_path.exists()

    with sqlite3.connect(result.database_path) as connection:
        clean_rows = connection.execute(
            """
            SELECT word, normalized_word, source, is_trusted, is_common, is_active
            FROM words_clean
            ORDER BY row_order
            """
        ).fetchall()
        review_rows = connection.execute(
            """
            SELECT original_word, normalized_word, reasons, reason_count
            FROM words_review_flagged
            ORDER BY row_order
            """
        ).fetchall()
        report_row = connection.execute(
            """
            SELECT raw_tokens,
                   clean_unique_rows_exported,
                   duplicates_removed,
                   hard_rejected,
                   flagged_for_review,
                   sample_cleaned_words
            FROM import_reports
            """
        ).fetchone()
        clean_indexes = {row[1] for row in connection.execute("PRAGMA index_list('words_clean')").fetchall()}
        review_indexes = {row[1] for row in connection.execute("PRAGMA index_list('words_review_flagged')").fetchall()}

    assert clean_rows == [
        ("বাংলা", "বাংলা", "seed.csv", 1, 1, 1),
        ("বাংলালী", "বাংলালি", "seed.csv", 1, 0, 0),
    ]
    assert review_rows == [
        ("অংশগুলো", "অংশগুলো", "possible_inflected_form", 1),
        ("অংশগ্রহণকারীও", "অংশগ্রহণকারীও", "possible_concatenated_phrase|possible_emphasis_variant", 2),
    ]
    assert report_row == (25, 2, 1, 0, 2, "বাংলা\nবাংলালি")
    assert "idx_words_clean_word" in clean_indexes
    assert "idx_words_clean_normalized_word" in clean_indexes
    assert "idx_words_review_flagged_original_word" in review_indexes
    assert "idx_words_review_flagged_normalized_word" in review_indexes


def test_import_lexicon_to_sqlite_overwrites_existing_database_and_exports_seed(tmp_path: Path) -> None:
    paths = _write_import_fixture(tmp_path)
    import_lexicon_to_sqlite(paths)

    paths.clean_csv_path.write_text(
        dedent(
            """\
            word,normalized_word,source,is_trusted,is_common,is_active
            শব্দ,শব্দ,refresh.csv,1,1,1
            শব্দ,শব্দ,refresh.csv,1,1,1
            পুরোনো,পুরোনো,refresh.csv,1,0,0
            """
        ),
        encoding="utf-8",
    )
    paths.review_csv_path.write_text(
        dedent(
            """\
            original_word,normalized_word,reasons
            অপেক্ষমান,অপেক্ষমান,possible_inflected_form
            """
        ),
        encoding="utf-8",
    )
    paths.summary_path.write_text(
        dedent(
            """\
            Raw tokens: 3
            Clean unique rows exported: 2
            Duplicates removed: 1
            Hard rejected: 0
            Flagged for review: 1

            Sample cleaned words:
            শব্দ
            পুরোনো
            """
        ),
        encoding="utf-8",
    )

    result = import_lexicon_to_sqlite(paths)
    exported_rows = export_seed_lexicon(result.database_path, paths.seed_lexicon_path)

    assert result.clean_rows == 2
    assert result.review_rows == 1
    assert exported_rows == 1
    assert paths.seed_lexicon_path.read_text(encoding="utf-8").splitlines() == [
        "# Exported from data/shuddho_lexicon.db via scripts/import_lexicon_to_sqlite.py",
        "শব্দ",
    ]

    with sqlite3.connect(result.database_path) as connection:
        clean_count = connection.execute("SELECT COUNT(*) FROM words_clean").fetchone()[0]
        report_count = connection.execute("SELECT COUNT(*) FROM import_reports").fetchone()[0]
        review_count = connection.execute("SELECT COUNT(*) FROM words_review_flagged").fetchone()[0]

    assert clean_count == 2
    assert report_count == 1
    assert review_count == 1


def _write_import_fixture(base_dir: Path) -> LexiconImportPaths:
    imports_dir = base_dir / "imports" / "lexicon"
    imports_dir.mkdir(parents=True)
    database_path = base_dir / "shuddho_lexicon.db"
    seed_output_path = base_dir / "seed_lexicon.txt"

    clean_csv_path = imports_dir / "words_clean.csv"
    review_csv_path = imports_dir / "words_review_flagged.csv"
    summary_path = imports_dir / "cleaning_summary.txt"

    clean_csv_path.write_text(
        dedent(
            """\
            word,normalized_word,source,is_trusted,is_common,is_active
            বাংলা,বাংলা,seed.csv,1,1,1
            বাংলালী,বাংলালি,seed.csv,1,0,0
            """
        ),
        encoding="utf-8",
    )
    review_csv_path.write_text(
        dedent(
            """\
            original_word,normalized_word,reasons
            অংশগুলো,অংশগুলো,possible_inflected_form
            অংশগ্রহণকারীও,অংশগ্রহণকারীও,possible_concatenated_phrase | possible_emphasis_variant
            """
        ),
        encoding="utf-8",
    )
    summary_path.write_text(
        dedent(
            """\
            Raw tokens: 25
            Clean unique rows exported: 2
            Duplicates removed: 1
            Hard rejected: 0
            Flagged for review: 2

            Sample cleaned words:
            বাংলা
            বাংলালি
            """
        ),
        encoding="utf-8",
    )

    return LexiconImportPaths(
        clean_csv_path=clean_csv_path,
        review_csv_path=review_csv_path,
        summary_path=summary_path,
        database_path=database_path,
        seed_lexicon_path=seed_output_path,
    )
