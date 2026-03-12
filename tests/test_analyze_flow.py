from pathlib import Path

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager


def test_analyze_flow_merges_rule_and_spell_outputs(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
            ("বংলা", "বাংলা", "fixture.csv", "1", "0", "1"),
        ],
    )

    text = "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা বাংলা ভাষা সুন্দর।।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))

    subtypes = {suggestion.subtype for suggestion in merged}
    assert "safe_exact_typo" in subtypes
    assert "duplicate_punctuation" in subtypes
    assert "repeated_word" in subtypes


def test_analyze_flow_surfaces_csv_direct_map_suggestion(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
        ],
    )

    text = "অইউরোপীয়"
    normalizer = BanglaNormalizer()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), [])

    assert len(merged) == 1
    assert merged[0].original_text == "অইউরোপীয়"
    assert merged[0].replacement_options == ["অইউরোপীয়"]


def test_analyze_flow_does_not_emit_random_valid_word_suggestion(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
            ("ভাল", "ভাল", "fixture.csv", "1", "0", "1"),
        ],
    )

    text = "আমি ভাত খাচ্ছি"
    normalizer = BanglaNormalizer()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), [])

    assert merged == []


def _write_clean_csv_fixture(
    base_dir: Path,
    *,
    rows: list[tuple[str, str, str, str, str, str]],
) -> Path:
    runtime_csv_path = base_dir / "words_clean.csv"
    lines = ["word,normalized_word,source,is_trusted,is_common,is_active"]
    lines.extend(",".join(row) for row in rows)
    runtime_csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime_csv_path
