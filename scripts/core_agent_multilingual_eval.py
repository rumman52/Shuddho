from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from services.coworker.agent_router import qualify_agent_goal
from services.coworker.config import Settings

DEFAULT_CASES = Path("tests/fixtures/core_agent_multilingual_cases.jsonl")
REQUIRED_LANGUAGES = {"en", "bn", "banglish", "bn-en-mixed", "es", "ar"}
REQUIRED_EQUIVALENCE_GROUPS = {
    "reminder",
    "email_draft",
    "email_send",
    "flight_booking",
    "direct_question",
}

def evaluation_settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        auth_issuer="https://identity.example.test/auth/v1",
        environment="development",
        storage_backend="local",
        work_services_enabled=True,
        artifact_services_enabled=True,
        research_services_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        actions_enabled=True,
        personal_transactions_enabled=True,
    )

def load_cases(path: Path) -> list[dict]:
    rows: list[dict] = []
    required = {
        "id", "equivalence", "language", "goal", "execution", "capability",
        "tools", "consequential", "reason_code",
    }
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if set(value) != required:
            raise ValueError(f"{path}:{line_number} must contain exactly {sorted(required)}")
        rows.append(value)
    if not rows:
        raise ValueError("Multilingual Core Agent qualification fixture is empty")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Multilingual Core Agent qualification fixture has duplicate ids")
    return rows

def evaluate(cases: list[dict]) -> dict:
    settings = evaluation_settings()
    results = []
    failures = []
    groups: dict[str, list[dict]] = defaultdict(list)
    languages = set()

    for case in cases:
        languages.add(case["language"])
        decision = qualify_agent_goal(case["goal"], settings)
        actual = {
            "execution": decision.execution,
            "capability": decision.capability,
            "tools": decision.tools,
            "consequential": decision.consequential,
            "reason_code": decision.reason_code,
        }
        expected = {
            "execution": case["execution"],
            "capability": case["capability"],
            "tools": case["tools"],
            "consequential": case["consequential"],
            "reason_code": case["reason_code"],
        }
        passed = actual == expected
        item = {
            "id": case["id"],
            "equivalence": case["equivalence"],
            "language": case["language"],
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
        results.append(item)
        groups[case["equivalence"]].append(item)
        if not passed:
            failures.append(case["id"])

    equivalence_failures = []
    for group_name, items in groups.items():
        signatures = {
            (
                item["actual"]["execution"],
                item["actual"]["capability"],
                tuple(item["actual"]["tools"]),
                item["actual"]["consequential"],
                item["actual"]["reason_code"],
            )
            for item in items
        }
        if len(signatures) != 1:
            equivalence_failures.append(group_name)

    coverage_failures = []
    for language in sorted(REQUIRED_LANGUAGES - languages):
        coverage_failures.append(f"missing_language_{language}")
    for group_name in sorted(REQUIRED_EQUIVALENCE_GROUPS - set(groups)):
        coverage_failures.append(f"missing_equivalence_{group_name}")

    passed_count = len(cases) - len(failures)
    return {
        "cases": len(cases),
        "passed": passed_count,
        "failed": len(failures),
        "pass_rate": round(passed_count / len(cases), 4),
        "languages": sorted(languages),
        "equivalence_groups": sorted(groups),
        "equivalence_failures": equivalence_failures,
        "coverage_failures": coverage_failures,
        "failures": failures,
        "results": results,
    }

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Qualify multilingual Core Agent route and safety equivalence."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()

    result = evaluate(load_cases(args.cases))
    gate_failures = list(result["coverage_failures"])
    gate_failures.extend(f"equivalence_{name}" for name in result["equivalence_failures"])
    if result["pass_rate"] < args.min_pass_rate:
        gate_failures.append("pass_rate")
    result["required_pass_rate"] = args.min_pass_rate
    result["gate_failures"] = gate_failures
    result["gate_decision"] = "PASS" if not gate_failures else "FAIL"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if gate_failures:
        raise SystemExit(
            "Multilingual Core Agent qualification failed: " + ", ".join(gate_failures)
        )

if __name__ == "__main__":
    main()
