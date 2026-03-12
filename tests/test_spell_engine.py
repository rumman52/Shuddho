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

    engine = SpellEngine(lexicon_path=lexicon_path)
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

    engine = SpellEngine(lexicon_path=lexicon_path)

    assert engine.analyze("আমি বাংলা লিখি") == []


def test_spell_engine_uses_sqlite_lexicon_canonical_words_and_direct_mappings(tmp_path: Path) -> None:
    database_path = tmp_path / "shuddho_lexicon.db"
    _create_runtime_lexicon_fixture(database_path)

    engine = SpellEngine(lexicon_db_path=database_path)

    assert engine.lexicon_source == "sqlite"
    assert "অইউরোপীয়" in engine.lexicon
    assert "অইউরোপীয়" not in engine.lexicon
    assert engine.correction_map["অইউরোপীয়"] == "অইউরোপীয়"
    assert engine.analyze("অইউরোপীয়") == []

    suggestions = engine.analyze("অইউরোপীয়")
    assert len(suggestions) == 1
    assert suggestions[0].original_text == "অইউরোপীয়"
    assert suggestions[0].replacement_options[0] == "অইউরোপীয়"
    assert suggestions[0].confidence >= 0.98


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
                (1, "অইউরোপীয়", "অইউরোপীয়", "fixture.csv", 1, 1, 1),
                (2, "আমি", "আমি", "fixture.csv", 1, 1, 1),
                (3, "বাংলা", "বাংলা", "fixture.csv", 1, 1, 1),
            ],
        )
