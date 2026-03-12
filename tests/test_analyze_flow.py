import sqlite3
from pathlib import Path

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager


def test_analyze_flow_merges_rule_and_spell_outputs() -> None:
    text = "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা বাংলা ভাষা সুন্দর।।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine()
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))

    subtypes = {suggestion.subtype for suggestion in merged}
    assert "safe_exact_typo" in subtypes
    assert "duplicate_punctuation" in subtypes
    assert "repeated_word" in subtypes


def test_analyze_flow_surfaces_sqlite_normalized_word_suggestions(tmp_path: Path) -> None:
    database_path = tmp_path / "shuddho_lexicon.db"
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
        connection.execute(
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
            (1, "অইউরোপীয়", "অইউরোপীয়", "fixture.csv", 1, 1, 1),
        )

    text = "অইউরোপীয়"
    normalizer = BanglaNormalizer()
    spell = SpellEngine(lexicon_db_path=database_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), [])

    assert len(merged) == 1
    assert merged[0].original_text == "অইউরোপীয়"
    assert merged[0].replacement_options[0] == "অইউরোপীয়"
