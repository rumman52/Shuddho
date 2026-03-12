from pathlib import Path

from services.spell.shuddho_spell.engine import SpellEngine
from services.spell.shuddho_spell.runtime_lexicon import load_runtime_lexicon


def test_runtime_lexicon_loads_from_main_csv_without_sqlite_runtime(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
            ("শরদ", "শরদ", "fixture.csv", "1", "0", "1"),
            ("শাদ", "শাদ", "fixture.csv", "1", "0", "1"),
        ],
    )
    fallback_seed_path = tmp_path / "seed_lexicon.txt"
    fallback_seed_path.write_text("# legacy fallback\nআমি\n", encoding="utf-8")

    runtime_lexicon = load_runtime_lexicon(runtime_csv_path, fallback_seed_path=fallback_seed_path)

    assert runtime_lexicon.source == "words_clean.csv"
    assert runtime_lexicon.accepted_words == runtime_lexicon.candidate_words
    assert runtime_lexicon.accepted_words == ("অইউরোপীয়",)
    assert runtime_lexicon.correction_map == {"অইউরোপীয়": "অইউরোপীয়"}


def test_spell_engine_uses_main_csv_direct_mapping_and_accepts_canonical_target(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.lexicon_source == "words_clean.csv"
    assert engine.analyze("অইউরোপীয়") == []

    suggestions = engine.analyze("অইউরোপীয়")
    assert len(suggestions) == 1
    assert suggestions[0].replacement_options == ["অইউরোপীয়"]
    assert suggestions[0].confidence >= 0.99


def test_spell_engine_candidate_pool_ignores_noisy_self_canonical_rows(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
            ("শরদ", "শরদ", "fixture.csv", "1", "0", "1"),
            ("শাদ", "শাদ", "fixture.csv", "1", "0", "1"),
            ("শোদ", "শোদ", "fixture.csv", "1", "0", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.analyze("শবদ") == []


def test_spell_engine_does_not_emit_random_suggestion_for_ami_bhat_khacchi(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
            ("ভাল", "ভাল", "fixture.csv", "1", "0", "1"),
            ("ভালো", "ভালো", "fixture.csv", "1", "0", "1"),
            ("খাচ্ছি", "খাচ্ছি", "fixture.csv", "1", "0", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.analyze("আমি ভাত খাচ্ছি") == []


def test_spell_engine_uses_seed_only_as_missing_csv_fallback(tmp_path: Path) -> None:
    fallback_seed_path = tmp_path / "seed_lexicon.txt"
    fallback_seed_path.write_text("# legacy fallback\nআমি\nবাংলা\nলিখি\n", encoding="utf-8")
    missing_csv_path = tmp_path / "missing_words_clean.csv"

    engine = SpellEngine(runtime_csv_path=missing_csv_path, fallback_seed_path=fallback_seed_path)

    assert engine.lexicon_source == "seed_fallback"
    assert engine.analyze("আমি বাংলা লিখি") == []


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
