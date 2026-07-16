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

    duplicate_punctuation = next(suggestion for suggestion in suggestions if suggestion.subtype == "duplicate_punctuation")
    spacing = next(suggestion for suggestion in suggestions if suggestion.subtype == "space_before_punctuation")

    assert duplicate_punctuation.rule_id == "PUNC_001"
    assert spacing.rule_id == "PUNC_002"


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


def test_rule_engine_detects_familiar_second_person_present_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("তুমি স্কুলে যায়।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "casual_pronoun_verb_mismatch")
    assert mismatch.original_text == "যায়"
    assert mismatch.replacement_options == ["যাও"]


def test_rule_engine_detects_first_person_verb_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আমি যায়।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "first_person_verb_mismatch")
    assert mismatch.original_text == "যায়"
    assert mismatch.replacement_options == ["যাই"]


def test_rule_engine_detects_honorific_present_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("আপনি ভাত খায়।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "honorific_pronoun_verb_mismatch")
    assert mismatch.original_text == "খায়"
    assert mismatch.replacement_options == ["খান"]


def test_rule_engine_detects_third_person_reverse_direction_mismatch() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("সে স্কুলে যাই।")
    mismatch = next(suggestion for suggestion in suggestions if suggestion.subtype == "third_person_verb_mismatch")
    assert mismatch.original_text == "যাই"
    assert mismatch.replacement_options == ["যায়"]


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


def test_rule_engine_surfaces_exact_typos_as_spelling_errors() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("শুদ্ধ বাংলা ব্যকরণ আর বঙ্গলা দরকার।")

    spellings = [suggestion for suggestion in suggestions if suggestion.rule_id == "SPELL_001"]

    assert spellings
    assert all(suggestion.subtype == "spelling_error" for suggestion in spellings)


def test_rule_engine_covers_requested_contextual_agreement_examples() -> None:
    engine = RuleEngine()
    examples = [
        ("আমি স্কুলে যায়।", "যায়", "যাই", "কর্তা ‘আমি’ হলে ক্রিয়াটি ‘যাই’ হওয়া উচিত।"),
        ("আমি ভাত খায়।", "খায়", "খাই", "কর্তা ‘আমি’ হলে ক্রিয়াটি ‘খাই’ হওয়া উচিত।"),
        ("আমি বই পড়ে।", "পড়ে", "পড়ি", "কর্তা ‘আমি’ হলে ক্রিয়াটি ‘পড়ি’ হওয়া উচিত।"),
        ("আমি কাজ করে।", "করে", "করি", "কর্তা ‘আমি’ হলে ক্রিয়াটি ‘করি’ হওয়া উচিত।"),
        ("আমি কাল যাবেন।", "যাবেন", "যাব", "কর্তা ‘আমি’ হলে ক্রিয়াটি ‘যাব’ হওয়া উচিত।"),
        ("সে স্কুলে যাই।", "যাই", "যায়", "কর্তা ‘সে’ হলে ক্রিয়াটি ‘যায়’ হওয়া উচিত।"),
        ("সে ভাত খাই।", "খাই", "খায়", "কর্তা ‘সে’ হলে ক্রিয়াটি ‘খায়’ হওয়া উচিত।"),
        ("সে বই পড়ি।", "পড়ি", "পড়ে", "কর্তা ‘সে’ হলে ক্রিয়াটি ‘পড়ে’ হওয়া উচিত।"),
        ("সে কাজ করি।", "করি", "করে", "কর্তা ‘সে’ হলে ক্রিয়াটি ‘করে’ হওয়া উচিত।"),
        ("তুমি স্কুলে যায়।", "যায়", "যাও", "কর্তা ‘তুমি’ হলে ক্রিয়াটি ‘যাও’ হওয়া উচিত।"),
        ("তুমি বই পড়েন।", "পড়েন", "পড়ো", "কর্তা ‘তুমি’ হলে ক্রিয়াটি ‘পড়ো’ হওয়া উচিত।"),
        ("আপনি স্কুলে যাও।", "যাও", "যান", "সম্বোধন ‘আপনি’ হলে সম্মানসূচক ক্রিয়া ‘যান’ ব্যবহার করা উচিত।"),
        ("আপনি বই পড়ো।", "পড়ো", "পড়েন", "সম্বোধন ‘আপনি’ হলে সম্মানসূচক ক্রিয়া ‘পড়েন’ ব্যবহার করা উচিত।"),
        ("তিনি কাজ করো।", "করো", "করেন", "কর্তা ‘তিনি’ হলে সম্মানসূচক ক্রিয়া ‘করেন’ ব্যবহার করা উচিত।"),
    ]

    for text, original, replacement, explanation in examples:
        suggestions = engine.analyze(text)
        match = next(suggestion for suggestion in suggestions if suggestion.original_text == original)
        assert match.replacement_options == [replacement]
        assert match.explanation_bn == explanation


def test_rule_engine_keeps_valid_sentence_clean_when_agreement_is_correct() -> None:
    engine = RuleEngine()

    suggestions = engine.analyze("আমি আজ স্কুলে যাই।")

    assert all(suggestion.category != "grammar" for suggestion in suggestions)


def test_rule_engine_skips_quoted_agreement_text() -> None:
    engine = RuleEngine()

    suggestions = engine.analyze("সে বলল, “আমি স্কুলে যায়।”")

    assert all(suggestion.original_text != "যায়" for suggestion in suggestions)

def test_rule_engine_detects_requested_paragraph_typoes_without_ai() -> None:
    engine = RuleEngine()
    text = "আজ সকালবেলা সূর্য উদয় হইল।\nসব পাখিরা নীল আকাশে উড়িতেছে আর মিষ্টি সুরে গান গাচ্ছে।\nএই অপরুপ দৃশ্যটি দেখে আমার চোখ অশ্রুজলে ভরে গেল।\nপ্রকৃতির এই রূপ দেখে আমি অত্যাধিক আনন্দিত হইলাম।"
    suggestions = engine.analyze(text)
    replacements = {suggestion.original_text: suggestion.replacement_options[0] for suggestion in suggestions}
    assert replacements["অপরুপ"] == "অপরূপ"
    assert replacements["অত্যাধিক"] == "অত্যধিক"
    assert replacements["গান গাচ্ছে"] == "গান গাইছে"
    for original in ("অপরুপ", "অত্যাধিক"):
        suggestion = next(item for item in suggestions if item.original_text == original)
        assert text[suggestion.span_start:suggestion.span_end] == original


def test_rule_engine_does_not_fabricate_for_clean_requested_words() -> None:
    engine = RuleEngine()
    suggestions = engine.analyze("এই অপরূপ দৃশ্যটি দেখে আমি অত্যধিক আনন্দিত হলাম।")
    assert all(suggestion.original_text not in {"অপরূপ", "অত্যধিক"} for suggestion in suggestions)
