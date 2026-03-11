from services.rules.shuddho_rules.engine import RuleEngine


def test_rule_engine_detects_repeated_word() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("বাংলা বাংলা ভাষা সুন্দর।")
    assert any(suggestion.subtype == "repeated_word" for suggestion in suggestions)


def test_rule_engine_detects_duplicate_punctuation_and_spacing() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি বাংলা লিখি  ।।")
    subtypes = {suggestion.subtype for suggestion in suggestions}
    assert "duplicate_punctuation" in subtypes
    assert "space_before_punctuation" in subtypes

