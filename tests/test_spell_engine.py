from pathlib import Path

from services.spell.shuddho_spell.engine import SpellCandidate, SpellEngine
from services.spell.shuddho_spell.runtime_lexicon import load_runtime_lexicon
from shared.schemas.python_models import AnalyzeMode, SuggestionCategory, SuggestionKind


def test_runtime_lexicon_loads_from_main_csv_without_sqlite_runtime(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09df", "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc", "fixture.csv", "1", "0", "1"),
            ("\u09b6\u09b0\u09a6", "\u09b6\u09b0\u09a6", "fixture.csv", "1", "0", "1"),
            ("\u09b6\u09be\u09a6", "\u09b6\u09be\u09a6", "fixture.csv", "1", "0", "1"),
        ],
    )
    fallback_seed_path = tmp_path / "seed_lexicon.txt"
    fallback_seed_path.write_text("# legacy fallback\n\u0986\u09ae\u09bf\n", encoding="utf-8")

    runtime_lexicon = load_runtime_lexicon(runtime_csv_path, fallback_seed_path=fallback_seed_path)

    assert runtime_lexicon.source == "words_clean.csv"
    assert runtime_lexicon.accepted_words == runtime_lexicon.candidate_words
    assert runtime_lexicon.accepted_words == (
        "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc",
        "\u09b6\u09b0\u09a6",
        "\u09b6\u09be\u09a6",
    )
    assert runtime_lexicon.correction_map == {
        "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09df": "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc"
    }


def test_spell_engine_uses_main_csv_direct_mapping_and_accepts_canonical_target(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09df", "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc", "fixture.csv", "1", "0", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.lexicon_source == "words_clean.csv"
    assert engine.analyze("\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc") == []

    suggestions = engine.analyze("\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09df")
    assert len(suggestions) == 1
    assert suggestions[0].category == SuggestionCategory.SPELLING
    assert suggestions[0].subtype == "spelling_error"
    assert suggestions[0].suggestion_kind == SuggestionKind.TRUE_SPELLING_ERROR
    assert suggestions[0].replacement_options == ["\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc"]
    assert suggestions[0].confidence >= 0.99
    assert "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc" in suggestions[0].explanation_bn


def test_spell_engine_candidate_pool_remains_conservative_with_self_canonical_rows(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09df", "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc", "fixture.csv", "1", "0", "1"),
            ("\u09b6\u09b0\u09a6", "\u09b6\u09b0\u09a6", "fixture.csv", "1", "0", "1"),
            ("\u09b6\u09be\u09a6", "\u09b6\u09be\u09a6", "fixture.csv", "1", "0", "1"),
            ("\u09b6\u09cb\u09a6", "\u09b6\u09cb\u09a6", "fixture.csv", "1", "0", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.analyze("\u09b6\u09ac\u09a6") == []


def test_spell_engine_does_not_emit_random_suggestion_for_ami_bhat_khacchi(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09df", "\u0985\u0987\u0989\u09b0\u09cb\u09aa\u09c0\u09af\u09bc", "fixture.csv", "1", "0", "1"),
            ("\u09ad\u09be\u09b2", "\u09ad\u09be\u09b2", "fixture.csv", "1", "0", "1"),
            ("\u09ad\u09be\u09b2\u09cb", "\u09ad\u09be\u09b2\u09cb", "fixture.csv", "1", "0", "1"),
            ("\u0996\u09be\u099a\u09cd\u099b\u09bf", "\u0996\u09be\u099a\u09cd\u099b\u09bf", "fixture.csv", "1", "0", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.analyze("\u0986\u09ae\u09bf \u09ad\u09be\u09a4 \u0996\u09be\u099a\u09cd\u099b\u09bf") == []


def test_spell_engine_accepts_self_canonical_words_from_main_csv(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u09ac\u09be\u0982\u09b2\u09be", "\u09ac\u09be\u0982\u09b2\u09be", "fixture.csv", "1", "1", "1"),
            ("\u09b2\u09bf\u0996\u09bf", "\u09b2\u09bf\u0996\u09bf", "fixture.csv", "1", "1", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.lexicon_source == "words_clean.csv"
    assert engine.analyze("\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf") == []


def test_spell_engine_uses_seed_only_as_missing_csv_fallback(tmp_path: Path) -> None:
    fallback_seed_path = tmp_path / "seed_lexicon.txt"
    fallback_seed_path.write_text(
        "# legacy fallback\n\u0986\u09ae\u09bf\n\u09ac\u09be\u0982\u09b2\u09be\n\u09b2\u09bf\u0996\u09bf\n",
        encoding="utf-8",
    )
    missing_csv_path = tmp_path / "missing_words_clean.csv"

    engine = SpellEngine(runtime_csv_path=missing_csv_path, fallback_seed_path=fallback_seed_path)

    assert engine.lexicon_source == "seed_fallback"
    assert engine.analyze("\u0986\u09ae\u09bf \u09ac\u09be\u0982\u09b2\u09be \u09b2\u09bf\u0996\u09bf") == []


def test_runtime_lexicon_uses_csv_even_when_it_contains_only_self_canonical_rows(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u09ac\u09be\u0982\u09b2\u09be", "\u09ac\u09be\u0982\u09b2\u09be", "fixture.csv", "1", "1", "1"),
        ],
    )
    fallback_seed_path = tmp_path / "seed_lexicon.txt"
    fallback_seed_path.write_text("# legacy fallback\nfallback\n", encoding="utf-8")

    runtime_lexicon = load_runtime_lexicon(runtime_csv_path, fallback_seed_path=fallback_seed_path)

    assert runtime_lexicon.source == "words_clean.csv"
    assert runtime_lexicon.accepted_words == ("\u0986\u09ae\u09bf", "\u09ac\u09be\u0982\u09b2\u09be")
    assert runtime_lexicon.correction_map == {}


def test_spell_engine_treats_curated_variant_override_as_optional_style_guidance(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0995\u09bf\u09a8\u09cd\u09a4", "\u0995\u09bf\u09a8\u09cd\u09a4", "fixture.csv", "1", "1", "1"),
            ("\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
            ("\u0986\u09b8\u09ac", "\u0986\u09b8\u09ac", "fixture.csv", "1", "1", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    suggestions = engine.analyze("\u0995\u09bf\u09a8\u09cd\u09a4 \u0986\u09ae\u09bf \u0986\u09b8\u09ac")

    assert len(suggestions) == 1
    assert suggestions[0].rule_id == "SPELL_002"
    assert suggestions[0].category == SuggestionCategory.STYLE
    assert suggestions[0].subtype == "orthography_variant"
    assert suggestions[0].suggestion_kind == SuggestionKind.ORTHOGRAPHY_VARIANT
    assert suggestions[0].is_variant_only is True
    assert suggestions[0].optional_mode_visibility == [AnalyzeMode.STRICT, AnalyzeMode.FORMAL]
    assert suggestions[0].original_text == "\u0995\u09bf\u09a8\u09cd\u09a4"
    assert suggestions[0].replacement_options == ["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]
    assert suggestions[0].source.value == "spell"
    assert suggestions[0].severity.value == "low"


def test_spell_engine_personal_dictionary_accepts_variant_and_canonical_forms(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0995\u09bf\u09a8\u09cd\u09a4", "\u0995\u09bf\u09a8\u09cd\u09a4", "fixture.csv", "1", "1", "1"),
            ("\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "\u0995\u09bf\u09a8\u09cd\u09a4\u09c1", "fixture.csv", "1", "1", "1"),
        ],
    )

    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    assert engine.analyze("\u0995\u09bf\u09a8\u09cd\u09a4", personal_dictionary=["\u0995\u09bf\u09a8\u09cd\u09a4"]) == []
    assert engine.analyze("\u0995\u09bf\u09a8\u09cd\u09a4", personal_dictionary=["\u0995\u09bf\u09a8\u09cd\u09a4\u09c1"]) == []


def test_spell_engine_suppresses_ambiguous_generic_candidates(tmp_path: Path, monkeypatch) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
        ],
    )
    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    def fake_generate_candidates(token: str) -> list[SpellCandidate]:
        assert token == "\u0995\u09cd\u09b2\u09ae"
        return [
            SpellCandidate(word="\u0995\u09b2\u09ae", score=0.96),
            SpellCandidate(word="\u0995\u09c1\u09b2\u09ae", score=0.94),
        ]

    monkeypatch.setattr(engine, "generate_candidates", fake_generate_candidates)

    assert engine.analyze("\u0995\u09cd\u09b2\u09ae") == []


def test_spell_engine_personal_dictionary_suppresses_generic_candidate_targets(tmp_path: Path, monkeypatch) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("\u0986\u09ae\u09bf", "\u0986\u09ae\u09bf", "fixture.csv", "1", "1", "1"),
        ],
    )
    engine = SpellEngine(runtime_csv_path=runtime_csv_path)

    def fake_generate_candidates(token: str) -> list[SpellCandidate]:
        assert token == "\u09b0\u09be\u09b9\u09c1\u09b2\u09b2"
        return [SpellCandidate(word="\u09b0\u09be\u09b9\u09c1\u09b2", score=0.97)]

    monkeypatch.setattr(engine, "generate_candidates", fake_generate_candidates)

    assert engine.analyze("\u09b0\u09be\u09b9\u09c1\u09b2\u09b2", personal_dictionary=["\u09b0\u09be\u09b9\u09c1\u09b2"]) == []


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
