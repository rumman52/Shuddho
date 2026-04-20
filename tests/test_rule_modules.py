from services.rules.shuddho_rules import RuleConfig, RuleEngine
from services.rules.shuddho_rules.rules.postposition import fused_postposition_rule
from services.rules.shuddho_rules.rules.punctuation import duplicate_punctuation_rule


def test_punctuation_module_exposes_duplicate_punctuation_rule() -> None:
    suggestions = duplicate_punctuation_rule("আমি লিখি।।")

    duplicate = next(suggestion for suggestion in suggestions if suggestion.subtype == "duplicate_punctuation")
    assert duplicate.replacement_options == ["।"]


def test_postposition_module_exposes_fused_postposition_rule() -> None:
    suggestions = fused_postposition_rule("বাড়িথেকে এসেছি।")

    postposition = next(suggestion for suggestion in suggestions if suggestion.subtype == "fused_postposition")
    assert postposition.replacement_options == ["বাড়ি থেকে"]


def test_rule_engine_can_disable_noisy_rule_groups() -> None:
    engine = RuleEngine(config=RuleConfig(allow_noisy_rules=False))
    suggestions = engine.analyze("আমি আগামীকাল সকালে তোমাদের সাথে tomorrow আসব।")

    assert all(suggestion.subtype != "code_mixed_latin" for suggestion in suggestions)
