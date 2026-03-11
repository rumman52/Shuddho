from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager


def test_analyze_flow_merges_rule_and_spell_outputs() -> None:
    text = "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা ভাষা সুন্দর।।"
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

