from __future__ import annotations

from shared.schemas.python_models import Suggestion

from .config import RuleConfig
from .rules.agreement import build_rule_definitions as build_agreement_rules
from .rules.base import RuleDefinition
from .rules.exact_typos import build_rule_definitions as build_exact_typo_rules
from .rules.postposition import build_rule_definitions as build_postposition_rules
from .rules.punctuation import build_rule_definitions as build_punctuation_rules
from .rules.register import build_rule_definitions as build_register_rules
from .rules.spacing import build_rule_definitions as build_spacing_rules
from .rules.structural import build_rule_definitions as build_structural_rules


class RuleEngine:
    def __init__(self, *, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()
        self.rule_definitions = _build_rule_definitions()
        self.rule_metadata = {definition.key: definition for definition in self.rule_definitions}

    def analyze(self, text: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for definition in self.rule_definitions:
            if not self.config.is_enabled(definition.key, noisy=definition.noisy):
                continue
            suggestions.extend(definition.analyze(text))
        return suggestions


def _build_rule_definitions() -> tuple[RuleDefinition, ...]:
    return (
        *build_structural_rules(),
        *build_punctuation_rules(),
        *build_spacing_rules(),
        *build_agreement_rules(),
        *build_register_rules(),
        *build_postposition_rules(),
        *build_exact_typo_rules(),
    )
