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


def test_rule_engine_detects_extra_whitespace_between_words() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("সে  স্কুলে যায় ।")

    extra_whitespace = next(suggestion for suggestion in suggestions if suggestion.subtype == "extra_whitespace")
    spacing_before_punctuation = next(
        suggestion for suggestion in suggestions if suggestion.subtype == "space_before_punctuation"
    )

    assert extra_whitespace.original_text == "  "
    assert extra_whitespace.replacement_options == [" "]
    assert spacing_before_punctuation.original_text == " ।"
