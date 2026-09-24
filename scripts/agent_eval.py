from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

from services.coworker.agent_planner import deterministic_plan, intelligent_tool_names
from services.coworker.agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from services.coworker.config import Settings


DEFAULT_CASES = Path("tests/fixtures/agent_eval_cases.jsonl")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        required = {"id", "language", "goal", "expected_tools", "forbidden_tools"}
        if set(value) != required:
            raise ValueError(f"{path}:{line_number} must contain exactly {sorted(required)}")
        if not value["expected_tools"]:
            raise ValueError(f"{path}:{line_number} must contain at least one expected tool")
        rows.append(value)
    if not rows:
        raise ValueError("Agent evaluation fixture is empty")
    return rows


def evaluate_offline(cases: list[dict]) -> dict:
    settings = evaluation_settings()
    failures = []
    results = []
    for case in cases:
        plan = deterministic_plan(case["goal"], [], case["language"], settings, [])
        actual = [step.tool for step in plan]
        expected = case["expected_tools"]
        forbidden = set(case["forbidden_tools"])
        passed = actual == expected and not forbidden.intersection(actual)
        results.append({"id": case["id"], "language": case["language"], "expected": expected, "actual": actual, "passed": passed})
        if not passed:
            failures.append(case["id"])
    return {
        "mode": "offline",
        "cases": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "pass_rate": round((len(cases) - len(failures)) / len(cases), 4),
        "failures": failures,
        "results": results,
    }


async def evaluate_live(cases: list[dict]) -> dict:
    settings = replace(
        evaluation_settings(),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    )
    planner = DeepSeekAgentPlanner(settings)
    tools = intelligent_tool_names(settings)
    failures = []
    results = []
    for case in cases:
        try:
            proposal, tokens, latency_ms = await planner.propose(case["goal"], tools, reason="evaluation")
            actual = [step.tool for step in proposal.steps]
            expected = case["expected_tools"]
            forbidden = set(case["forbidden_tools"])
            passed = actual == expected and not forbidden.intersection(actual)
            results.append({
                "id": case["id"], "language": case["language"], "expected": expected, "actual": actual,
                "passed": passed, "tokens": tokens, "latency_ms": latency_ms,
            })
        except PlannerFailure as error:
            passed = False
            results.append({"id": case["id"], "language": case["language"], "expected": case["expected_tools"],
                            "actual": [], "passed": False, "error_code": error.code})
        if not passed:
            failures.append(case["id"])
    return {
        "mode": "live",
        "cases": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "pass_rate": round((len(cases) - len(failures)) / len(cases), 4),
        "failures": failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate bounded Shuddho agent routing without user data.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--live", action="store_true", help="Call the configured DeepSeek planner. Never use this in CI.")
    parser.add_argument("--release-id", default="ci-agent-contract")
    parser.add_argument("--rollout", type=Path)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rollout_sha = None
    if args.live:
        if args.rollout is None:
            raise SystemExit("--rollout is required with --live.")
        rollout = json.loads(args.rollout.read_text(encoding="utf-8"))
        if not isinstance(rollout, dict):
            raise SystemExit("Rollout manifest must contain a JSON object.")
        if rollout.get("release_id") != args.release_id:
            raise SystemExit("Planner release_id does not match the rollout manifest.")
        rollout_sha = sha256_file(args.rollout)
        revision = (
            os.environ.get("SHUDDHO_SOURCE_REVISION")
            or os.environ.get("RENDER_GIT_COMMIT")
            or os.environ.get("GITHUB_SHA")
            or ""
        ).strip().lower()
        if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
            raise SystemExit("Live planner evaluation requires a full lowercase source revision.")
    cases = load_cases(args.cases)
    result = asyncio.run(evaluate_live(cases)) if args.live else evaluate_offline(cases)
    failures = [] if result["pass_rate"] >= args.min_pass_rate else ["pass_rate"]
    result["gate_decision"] = "PASS" if not failures else "FAIL"
    result["gate_failures"] = failures
    result["release_id"] = args.release_id
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["fixture_sha256"] = sha256_file(args.cases)
    result["provider_model"] = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash") if args.live else None
    if args.live:
        result["rollout_manifest_sha256"] = rollout_sha
        result["source_revision"] = revision
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if failures:
        raise SystemExit(f"Agent evaluation failed: pass_rate={result['pass_rate']} required={args.min_pass_rate}")


if __name__ == "__main__":
    main()
