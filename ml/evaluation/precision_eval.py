from __future__ import annotations

import json
from pathlib import Path

from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer
from services.rules.shuddho_rules.engine import RuleEngine
from services.spell.shuddho_spell.engine import SpellEngine
from services.suggestion_manager.shuddho_suggestion_manager.manager import SuggestionManager


def evaluate_fixture(path: str | Path) -> dict[str, float]:
    normalizer = BanglaNormalizer()
    spell = SpellEngine()
    rules = RuleEngine()
    manager = SuggestionManager()

    total_expected = 0
    total_predicted = 0
    total_matched = 0

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        text = record["text"]
        expected = set(record["expected_subtypes"])
        normalized = normalizer.normalize(text)
        suggestions = manager.merge(
            text,
            normalized,
            spell.analyze(normalized.text),
            rules.analyze(text)
        )
        predicted = {suggestion.subtype for suggestion in suggestions}
        total_expected += len(expected)
        total_predicted += len(predicted)
        total_matched += len(expected & predicted)

    precision = total_matched / total_predicted if total_predicted else 0.0
    recall = total_matched / total_expected if total_expected else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4)}


if __name__ == "__main__":
    result = evaluate_fixture("shared/fixtures/evaluation_cases.jsonl")
    print(json.dumps(result, indent=2))
