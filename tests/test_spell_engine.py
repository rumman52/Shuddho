from services.spell.shuddho_spell.engine import SpellEngine


def test_spell_engine_flags_unknown_bangla_word() -> None:
    engine = SpellEngine()
    suggestions = engine.analyze("শুদ্ধ বাংলা ব্যকরণ আর বংলা লেখা")
    assert any(suggestion.original_text == "বংলা" for suggestion in suggestions)


def test_spell_engine_ignores_known_words() -> None:
    engine = SpellEngine()
    suggestions = engine.analyze("আমি বাংলা লিখি")
    assert suggestions == []

