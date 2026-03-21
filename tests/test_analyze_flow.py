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
    assert merged[0].subtype == "dictionary_variant"
    assert merged[0].replacement_options == ["অইউরোপীয়"]


def test_analyze_flow_returns_sentence_grounded_spacing_and_punctuation_suggestions(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("যায়", "যায়", "fixture.csv", "1", "0", "1"),
        ],
    )

    text = "সে  স্কুলে যায় ।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))

    by_subtype = {suggestion.subtype: suggestion for suggestion in merged}

    assert normalized.text == "সে স্কুলে যায়।"
    assert by_subtype["extra_whitespace"].original_text == "  "
    assert by_subtype["dictionary_variant"].replacement_options == ["যায়"]
    assert by_subtype["space_before_punctuation"].original_text == " ।"


def test_analyze_flow_returns_repeated_word_and_duplicate_punctuation_for_exact_spans(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[("যায়", "যায়", "fixture.csv", "1", "0", "1")],
    )

    text = "আমি আমি স্কুলে যাই।।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))

    by_subtype = {suggestion.subtype: suggestion for suggestion in merged}

    assert by_subtype["repeated_word"].span_start == 0
    assert by_subtype["repeated_word"].span_end == 7
    assert by_subtype["duplicate_punctuation"].replacement_options == ["।"]


def test_analyze_flow_preserves_whitelisted_reduplication(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[("যায়", "যায়", "fixture.csv", "1", "0", "1")],
    )

    text = "সে ধীরে ধীরে হাঁটে।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))

    assert all(suggestion.subtype != "repeated_word" for suggestion in merged)


def test_analyze_flow_returns_honorific_mismatch_suggestion(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[("যায়", "যায়", "fixture.csv", "1", "0", "1")],
    )

    text = "আপনি যাও।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))

    mismatch = next(suggestion for suggestion in merged if suggestion.subtype == "honorific_pronoun_verb_mismatch")
    assert mismatch.original_text == "যাও"
    assert mismatch.replacement_options == ["যান"]


def test_analyze_flow_returns_document_priority_rules_in_one_sentence(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[
            ("যায়", "যায়", "fixture.csv", "1", "0", "1"),
            ("অইউরোপীয়", "অইউরোপীয়", "fixture.csv", "1", "0", "1"),
        ],
    )

    text = "বাড়িথেকে আমি ৫কেজি চাল কিনি।তুমি করুন।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))
    subtypes = {suggestion.subtype for suggestion in merged}

    assert "fused_postposition" in subtypes
    assert "number_unit_spacing" in subtypes
    assert "space_after_punctuation" in subtypes
    assert "casual_pronoun_verb_mismatch" in subtypes


def test_analyze_flow_returns_mixed_digit_and_code_mix_suggestions(tmp_path: Path) -> None:
    runtime_csv_path = _write_clean_csv_fixture(
        tmp_path,
        rows=[("যায়", "যায়", "fixture.csv", "1", "0", "1")],
    )

    text = "আমি আগামীকাল সকালে তোমাদের সাথে tomorrow আসব। আজ ২১/03/2026, সময় 5টা।"
    normalizer = BanglaNormalizer()
    rules = RuleEngine()
    spell = SpellEngine(runtime_csv_path=runtime_csv_path)
    manager = SuggestionManager()

    normalized = normalizer.normalize(text)
    merged = manager.merge(text, normalized, spell.analyze(normalized.text), rules.analyze(text))
    subtypes = {suggestion.subtype for suggestion in merged}

    assert "code_mixed_latin" in subtypes
    assert "mixed_digit_style" in subtypes


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
