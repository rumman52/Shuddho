from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.coworker.agent_router import qualify_agent_goal
from services.coworker.config import Settings


DEFAULT_CASES = Path("tests/fixtures/core_agent_route_cases.jsonl")


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
    )


def load_cases(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        required = {"id", "goal", "execution", "capability", "tools"}
        if set(value) != required:
            raise ValueError(f"{path}:{line_number} must contain exactly {sorted(required)}")
        rows.append(value)
    if not rows:
        raise ValueError("Core Agent routing benchmark is empty")
    return rows


def evaluate(cases: list[dict]) -> dict:
    cfg = evaluation_settings()
    results = []
    failures = []
    for case in cases:
        decision = qualify_agent_goal(case["goal"], cfg)
        actual = {
            "execution": decision.execution,
            "capability": decision.capability,
            "tools": decision.tools,
        }
        expected = {
            "execution": case["execution"],
            "capability": case["capability"],
            "tools": case["tools"],
        }
        passed = actual == expected
        results.append(
            {
                "id": case["id"],
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
        )
        if not passed:
            failures.append(case["id"])
    passed_count = len(cases) - len(failures)
    return {
        "cases": len(cases),
        "passed": passed_count,
        "failed": len(failures),
        "pass_rate": round(passed_count / len(cases), 4),
        "failures": failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the deterministic Shuddho Core Agent request router."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--min-pass-rate", type=float, default=0.95)
    args = parser.parse_args()

    result = evaluate(load_cases(args.cases))
    result["required_pass_rate"] = args.min_pass_rate
    result["gate_decision"] = (
        "PASS" if result["pass_rate"] >= args.min_pass_rate else "FAIL"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["gate_decision"] != "PASS":
        raise SystemExit(
            "Core Agent routing gate failed: "
            f"pass_rate={result['pass_rate']} required={args.min_pass_rate}"
        )


if __name__ == "__main__":
    main()
