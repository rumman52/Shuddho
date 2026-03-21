from services.rules.shuddho_rules.engine import RuleEngine


def test_rule_engine_detects_repeated_word() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("বাংলা বাংলা ভাষা সুন্দর।")
    assert any(suggestion.subtype == "repeated_word" for suggestion in suggestions)


def test_rule_engine_does_not_flag_whitelisted_reduplication() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("সে ধীরে ধীরে হাঁটে।")
    assert all(suggestion.subtype != "repeated_word" for suggestion in suggestions)


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


def test_rule_engine_detects_bangla_full_stop() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি স্কুলে যাই.")
    full_stop = next(suggestion for suggestion in suggestions if suggestion.subtype == "bangla_full_stop")
    assert full_stop.replacement_options == ["।"]


def test_rule_engine_detects_missing_space_after_terminator() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি গেলাম।তুমি এলে?")
    spacing = next(suggestion for suggestion in suggestions if suggestion.subtype == "space_after_punctuation")
    assert spacing.original_text == "।ত"
    assert spacing.replacement_options == ["। ত"]


def test_rule_engine_detects_duplicate_negation() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি যাব না না।")
    duplicate_negation = next(suggestion for suggestion in suggestions if suggestion.subtype == "duplicate_negation")
    assert duplicate_negation.replacement_options == ["না"]


def test_rule_engine_detects_honorific_pronoun_verb_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আপনি যাও।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "honorific_pronoun_verb_mismatch")
    assert mismatch.original_text == "যাও"
    assert mismatch.replacement_options == ["যান"]


def test_rule_engine_detects_casual_pronoun_verb_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("তুমি করুন।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "casual_pronoun_verb_mismatch")
    assert mismatch.original_text == "করুন"
    assert mismatch.replacement_options == ["করো"]


def test_rule_engine_detects_first_person_verb_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি যায়।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "first_person_verb_mismatch")
    assert mismatch.original_text == "যায়"
    assert mismatch.replacement_options == ["যাই"]


def test_rule_engine_detects_mixed_address_register() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আপনি কি তুমি আসবে?")
    mixed_register = next(suggestion for suggestion in suggestions if suggestion.subtype == "mixed_address_register")
    assert mixed_register.original_text in {"আপনি", "তুমি"}


def test_rule_engine_detects_fused_postposition() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("বাড়িথেকে এসেছি।")
    postposition = next(suggestion for suggestion in suggestions if suggestion.subtype == "fused_postposition")
    assert postposition.original_text == "বাড়িথেকে"
    assert postposition.replacement_options == ["বাড়ি থেকে"]


def test_rule_engine_detects_genitive_spacing() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("বাংলা এর ইতিহাস")
    genitive = next(suggestion for suggestion in suggestions if suggestion.subtype == "genitive_spacing")
    assert genitive.original_text == "বাংলা এর"
    assert genitive.replacement_options == ["বাংলার"]


def test_rule_engine_detects_repeated_coordinator() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("রুটি এবং এবং চা")
    coordinator = next(suggestion for suggestion in suggestions if suggestion.subtype == "repeated_coordinator")
    assert coordinator.replacement_options == ["এবং"]


def test_rule_engine_detects_mixed_digit_style() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আজ ২১/03/2026, সময় 5টা")
    digit_style = next(suggestion for suggestion in suggestions if suggestion.subtype == "mixed_digit_style")
    assert len(digit_style.replacement_options) == 2


def test_rule_engine_detects_number_unit_spacing() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("৫কেজি চাল")
    unit_spacing = next(suggestion for suggestion in suggestions if suggestion.subtype == "number_unit_spacing")
    assert unit_spacing.replacement_options == ["৫ কেজি"]


def test_rule_engine_detects_code_mixed_latin_word() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি আগামীকাল সকালে তোমাদের সাথে tomorrow আসব।")
    code_mix = next(suggestion for suggestion in suggestions if suggestion.subtype == "code_mixed_latin")
    assert code_mix.original_text == "tomorrow"
    assert code_mix.replacement_options == ["আগামীকাল"]


def test_rule_engine_detects_unbalanced_delimiter() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("সে বলল (আমি যাব।")
    assert any(suggestion.subtype == "unbalanced_delimiter" for suggestion in suggestions)
