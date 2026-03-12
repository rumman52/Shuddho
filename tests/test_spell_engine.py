import sqlite3
from pathlib import Path

from services.spell.shuddho_spell.engine import SpellEngine


def test_spell_engine_flags_unknown_bangla_word(tmp_path: Path) -> None:
    lexicon_path = tmp_path / "seed_lexicon.txt"
    lexicon_path.write_text(
        "\n".join(
            [
                "# test seed lexicon",
                "শুদ্ধ",
                "বাংলা",
                "ব্যাকরণ",
                "আর",
                "লেখা",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = SpellEngine(
        lexicon_path=lexicon_path,
        use_sqlite_lexicon=False,
        use_sqlite_correction_map=False,
    )

    suggestions = engine.analyze("শুদ্ধ বাংলা ব্যাকরণ আর বংলা লেখা")
    assert any(suggestion.original_text == "বংলা" for suggestion in suggestions)


def test_spell_engine_ignores_known_words(tmp_path: Path) -> None:
    lexicon_path = tmp_path / "seed_lexicon.txt"
    lexicon_path.write_text(
        "\n".join(
            [
                "# test seed lexicon",
                "আমি",
                "বাংলা",
                "লিখি",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = SpellEngine(
        lexicon_path=lexicon_path,
        use_sqlite_lexicon=False,
        use_sqlite_correction_map=False,
    )

    assert engine.analyze("আমি বাংলা লিখি") == []


def test_spell_engine_defaults_to_seed_and_uses_sqlite_direct_maps_safely(tmp_path: Path) -> None:
    lexicon_path = tmp_path / "seed_lexicon.txt"
    lexicon_path.write_text(
        "\n".join(
            [
                "# test seed lexicon",
                "আমি",
                "বাংলা",
                "লিখি",
                "শুদ্ধ",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    database_path = tmp_path / "shuddho_lexicon.db"
    _create_runtime_lexicon_fixture(database_path)

    engine = SpellEngine(lexicon_path=lexicon_path, lexicon_db_path=database_path)

    assert engine.lexicon_source == "seed+sqlite_corrections"
    assert "অইউরোপীয়" in engine.lexicon
    assert "অইউরোপীয়" not in engine.lexicon
    assert "শরদ" not in engine.lexicon
    assert engine.analyze("অইউরোপীয়") == []

    suggestions = engine.analyze("অইউরোপীয়")
    assert len(suggestions) == 1
    assert suggestions[0].replacement_options == ["অইউরোপীয়"]
    assert suggestions[0].confidence >= 0.99

    assert engine.analyze("শবদ") == []


def test_spell_engine_can_opt_into_sqlite_accepted_words_without_using_sqlite_fuzzy_candidates(
    tmp_path: Path,
) -> None:
    lexicon_path = tmp_path / "seed_lexicon.txt"
    lexicon_path.write_text(
        "\n".join(
            [
                "# test seed lexicon",
                "আমি",
                "বাংলা",
                "লিখি",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    database_path = tmp_path / "shuddho_lexicon.db"
    _create_runtime_lexicon_fixture(database_path)

    engine = SpellEngine(
        lexicon_path=lexicon_path,
        lexicon_db_path=database_path,
        use_sqlite_lexicon=True,
        use_sqlite_correction_map=True,
    )

    assert engine.lexicon_source == "sqlite"
    assert "শরদ" in engine.lexicon
    assert engine.analyze("শরদ") == []
    assert engine.analyze("শবদ") == []


def _create_runtime_lexicon_fixture(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE words_clean (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_order INTEGER NOT NULL,
                word TEXT NOT NULL,
                normalized_word TEXT NOT NULL,
                source TEXT NOT NULL,
                is_trusted INTEGER NOT NULL,
                is_common INTEGER NOT NULL,
                is_active INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO words_clean (
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
            [
                (1, "অইউরোপীয়", "অইউরোপীয়", "fixture.csv", 1, 0, 1),
                (2, "শরদ", "শরদ", "fixture.csv", 1, 0, 1),
                (3, "শাদ", "শাদ", "fixture.csv", 1, 0, 1),
                (4, "শোদ", "শোদ", "fixture.csv", 1, 0, 1),
            ],
        )
