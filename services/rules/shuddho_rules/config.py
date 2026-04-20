from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleConfig:
    enabled_rules: frozenset[str] | None = None
    disabled_rules: frozenset[str] = field(default_factory=frozenset)
    allow_noisy_rules: bool = True

    def is_enabled(self, rule_key: str, *, noisy: bool = False) -> bool:
        if not self.allow_noisy_rules and noisy:
            return False
        if self.enabled_rules is not None and rule_key not in self.enabled_rules:
            return False
        return rule_key not in self.disabled_rules
