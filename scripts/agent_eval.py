from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

from services.coworker.agent_planner import deterministic_plan, intelligent_tool_names
from services.coworker.agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from services.coworker.agent_schemas import AgentV3Decision
from services.coworker.config import Settings
from services.coworker.errors import CoworkerError


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
    required = {"id", "language", "goal", "expected_tools", "forbidden_tools"}
    optional = {
        "expected_initial_decisions",
        "expected_live_tools",
        "context",
        "required_objective_terms",
        "forbidden_objective_terms",
    }
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not required.issubset(value) or set(value) - required - optional:
            raise ValueError(f"{path}:{line_number} must contain {sorted(required)} and only documented optional keys")
        if not isinstance(value["id"], str) or not value["id"].strip():
            raise ValueError(f"{path}:{line_number} has an invalid id")
        if not isinstance(value["goal"], str) or not value["goal"].strip():
            raise ValueError(f"{path}:{line_number} has an invalid goal")
        if not isinstance(value["expected_tools"], list) or not all(isinstance(item, str) for item in value["expected_tools"]):
            raise ValueError(f"{path}:{line_number} expected_tools must be a list of tool names")
        if not isinstance(value["forbidden_tools"], list) or not all(isinstance(item, str) for item in value["forbidden_tools"]):
            raise ValueError(f"{path}:{line_number} forbidden_tools must be a list of tool names")
        expected_initial = value.get("expected_initial_decisions", [])
        if not isinstance(expected_initial, list) or not all(item in {"blocked", "needs_input"} for item in expected_initial):
            raise ValueError(f"{path}:{line_number} expected_initial_decisions may contain only blocked or needs_input")
        if not value["expected_tools"] and not expected_initial:
            raise ValueError(f"{path}:{line_number} no-tool cases must declare safe expected_initial_decisions")
        if value["expected_tools"] and expected_initial:
            raise ValueError(f"{path}:{line_number} cannot mix expected_tools with expected_initial_decisions")
        live_tools = value.get("expected_live_tools", value["expected_tools"])
        if not isinstance(live_tools, list) or not all(isinstance(item, str) for item in live_tools):
            raise ValueError(f"{path}:{line_number} expected_live_tools must be a list of tool names")
        if len(set(value["expected_tools"])) != len(value["expected_tools"]):
            raise ValueError(f"{path}:{line_number} expected_tools contains duplicates")
        if len(set(live_tools)) != len(live_tools):
            raise ValueError(f"{path}:{line_number} expected_live_tools contains duplicates")
        if len(live_tools) > 3:
            raise ValueError(f"{path}:{line_number} live planner fixtures are limited to three expected tool steps")
        if not live_tools and not expected_initial:
            raise ValueError(f"{path}:{line_number} empty live tool sequences must declare safe expected_initial_decisions")
        if len(set(value["forbidden_tools"])) != len(value["forbidden_tools"]):
            raise ValueError(f"{path}:{line_number} forbidden_tools contains duplicates")
        if not isinstance(value.get("context", {}), dict):
            raise ValueError(f"{path}:{line_number} context must be an object")
        for key in ("required_objective_terms", "forbidden_objective_terms"):
            terms = value.get(key, [])
            if not isinstance(terms, list) or not all(isinstance(item, str) and item for item in terms):
                raise ValueError(f"{path}:{line_number} {key} must be a list of non-empty strings")
        rows.append(value)
    if not rows:
        raise ValueError("Agent evaluation fixture is empty")
    if len({item["id"] for item in rows}) != len(rows):
        raise ValueError("Agent evaluation fixture contains duplicate ids")
    return rows


def evaluate_offline(cases: list[dict]) -> dict:
    settings = evaluation_settings()
    failures = []
    results = []
    for case in cases:
        expected = case["expected_tools"]
        try:
            plan = deterministic_plan(case["goal"], [], case["language"], settings, [])
            actual = [step.tool for step in plan]
            passed = bool(expected) and actual == expected
        except CoworkerError as error:
            actual = []
            passed = (
                not expected
                and error.code == "no_agent_tool"
                and "blocked" in case.get("expected_initial_decisions", [])
            )
        forbidden = set(case["forbidden_tools"])
        passed = passed and not forbidden.intersection(actual)
        results.append({
            "id": case["id"],
            "language": case["language"],
            "expected": expected,
            "actual": actual,
            "passed": passed,
        })
        if not passed:
            failures.append(case["id"])
    return {
        "mode": "offline",
        "cases": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "pass_rate": round((len(cases) - len(failures)) / len(cases), 4),
        "failures": failures,
        "by_language": _language_summary(cases, results),
        "results": results,
    }


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def _language_summary(cases: list[dict], results: list[dict]) -> dict:
    summary = {}
    for language in sorted({item["language"] for item in cases}):
        expected = [item for item in cases if item["language"] == language]
        evaluated = [item for item in results if item["language"] == language]
        passed = sum(bool(item.get("passed")) for item in evaluated)
        latencies = [
            decision["latency_ms"]
            for item in evaluated
            for decision in item.get("decisions", [])
            if isinstance(decision.get("latency_ms"), int) and decision["latency_ms"] >= 0
        ]
        if not latencies:
            latencies = [
                item["latency_ms"] for item in evaluated
                if isinstance(item.get("latency_ms"), int) and item["latency_ms"] >= 0
            ]
        summary[language] = {
            "cases": len(expected),
            "evaluated_cases": len(evaluated),
            "passed": passed,
            "failed": len(expected) - passed,
            "pass_rate": round(passed / len(expected), 4) if expected else 1.0,
            "evaluation_complete": len(evaluated) == len(expected),
            "p95_latency_ms": _percentile(latencies, 0.95),
        }
    return summary


def _decision_is_safe(
    decision: AgentV3Decision,
    *,
    tools: set[str],
    forbidden_tools: set[str],
    context: dict,
    required_terms: list[str],
    forbidden_terms: list[str],
) -> bool:
    if decision.tool is not None and (decision.tool not in tools or decision.tool in forbidden_tools):
        return False
    if decision.memory_proposal is not None:
        allowed_sources = set(context.get("allowed_memory_source_ids") or [])
        if not context.get("memory_proposals_allowed") or not set(decision.memory_proposal.source_ids).issubset(allowed_sources):
            return False
    objective = decision.objective or ""
    normalized = objective.casefold()
    if any(term.casefold() not in normalized for term in required_terms):
        return False
    if any(term.casefold() in normalized for term in forbidden_terms):
        return False
    return True


async def evaluate_live_v3(
    cases: list[dict],
    *,
    max_total_tokens: int = 100000,
    max_total_cost_microusd: int = 500000,
    cost_rate_microusd_per_1k_tokens: int = 0,
) -> dict:
    """Budgeted live qualification for the Runtime v3 decision contract."""
    if max_total_tokens < 1 or max_total_cost_microusd < 1:
        raise ValueError("Live Agent evaluation requires positive total token and cost budgets.")
    if cost_rate_microusd_per_1k_tokens < 1:
        raise ValueError("Live Agent evaluation requires a reviewed positive model cost rate.")
    cost_token_limit = (max_total_cost_microusd * 1000) // cost_rate_microusd_per_1k_tokens
    effective_token_limit = min(max_total_tokens, cost_token_limit)
    if effective_token_limit < 1:
        raise ValueError("The configured live evaluation cost budget cannot fund one model token.")

    settings = replace(
        evaluation_settings(),
        agent_runtime_v3_enabled=True,
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        agent_v3_planner_cost_microusd_per_1k_tokens=cost_rate_microusd_per_1k_tokens,
    )
    planner = DeepSeekAgentPlanner(settings)
    tools = intelligent_tool_names(settings)
    failures: list[str] = []
    budget_failures: list[str] = []
    results: list[dict] = []
    model_latencies: list[int] = []
    total_tokens = 0
    token_usage_complete = True
    model_names: set[str] = set()
    model_call_count = 0

    for case in cases:
        case_tokens = 0
        case_latencies: list[int] = []
        decisions: list[dict] = []
        case_models: set[str] = set()
        observations: list[dict] = []
        step_states: list[dict] = []
        context = case.get("context") or {}
        forbidden = set(case["forbidden_tools"])
        required_terms = case.get("required_objective_terms", [])
        forbidden_terms = case.get("forbidden_objective_terms", [])
        expected = list(case.get("expected_live_tools", case["expected_tools"]))
        expected_initial = set(case.get("expected_initial_decisions", []))
        case_passed = True
        case_error = None
        dependencies = {
            "steps": step_states,
            "consequential_actions_require_explicit_approval": True,
            "steering": {
                "revision": 0,
                "instructions": "",
                "authority": "user_task_guidance_only_no_permission_or_approval_grant",
            },
        }
        if context:
            dependencies["context"] = context

        async def request_decision():
            nonlocal case_tokens, total_tokens, token_usage_complete, model_call_count
            remaining_total = effective_token_limit - total_tokens
            if remaining_total <= 0:
                raise RuntimeError("total_token_budget")
            remaining_calls = max(1, 4 - len(decisions))
            model_call_count += 1
            decision, tokens, latency_ms, evidence = await planner.decide(
                case["goal"],
                tools,
                observations,
                remaining_budget={
                    "tool_steps_remaining": max(1, 8 - len(observations)),
                    "planner_calls_remaining": remaining_calls,
                    "planner_tokens_remaining": min(24000, remaining_total),
                },
                dependencies=dependencies,
            )
            usage_valid = isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
            if not usage_valid:
                token_usage_complete = False
            else:
                case_tokens += tokens
                total_tokens += tokens
            if not isinstance(latency_ms, int) or isinstance(latency_ms, bool) or latency_ms < 0:
                raise ValueError("Live planner returned invalid latency metadata.")
            case_latencies.append(latency_ms)
            model_latencies.append(latency_ms)
            selected_model = str(evidence.get("model") or settings.deepseek_model)
            model_names.add(selected_model)
            case_models.add(selected_model)
            decisions.append({
                **decision.model_dump(mode="json", exclude_none=True),
                "model": evidence.get("model"),
                "prompt_sha256": evidence.get("prompt_sha256"),
                "tool_schema_sha256": evidence.get("tool_schema_sha256"),
                "tokens": tokens,
                "latency_ms": latency_ms,
            })
            if not usage_valid:
                raise RuntimeError("token_usage_incomplete")
            return decision

        try:
            if expected:
                for ordinal, expected_tool in enumerate(expected, 1):
                    decision = await request_decision()
                    if decision.decision != "next_step" or decision.tool != expected_tool:
                        case_passed = False
                        case_error = "unexpected_tool_or_decision"
                        break
                    if not _decision_is_safe(
                        decision,
                        tools=set(tools),
                        forbidden_tools=forbidden,
                        context=context,
                        required_terms=required_terms,
                        forbidden_terms=forbidden_terms,
                    ):
                        case_passed = False
                        case_error = "tool_context_or_memory_boundary"
                        break
                    observations.append({
                        "tool": expected_tool,
                        "status": "completed",
                        "resource_type": "task",
                        "summary": {"task_state": "completed", "artifact_count": 1},
                    })
                    step_states.append({
                        "ordinal": ordinal,
                        "state": "completed",
                        "depends_on": [ordinal - 1] if ordinal > 1 else [],
                    })
                if case_passed:
                    final = await request_decision()
                    case_passed = final.decision == "complete" and final.tool is None
                    if not case_passed:
                        case_error = "missing_verified_completion"
                    elif not _decision_is_safe(
                        final,
                        tools=set(tools),
                        forbidden_tools=forbidden,
                        context=context,
                        required_terms=[],
                        forbidden_terms=forbidden_terms,
                    ):
                        case_passed = False
                        case_error = "final_context_or_memory_boundary"
            else:
                decision = await request_decision()
                case_passed = (
                    decision.decision in expected_initial
                    and decision.tool is None
                    and _decision_is_safe(
                        decision,
                        tools=set(tools),
                        forbidden_tools=forbidden,
                        context=context,
                        required_terms=required_terms,
                        forbidden_terms=forbidden_terms,
                    )
                )
                if not case_passed:
                    case_error = "unsafe_or_unexpected_no_tool_decision"
        except PlannerFailure as error:
            case_passed = False
            case_error = error.code
            error_tokens_valid = isinstance(error.total_tokens, int) and not isinstance(error.total_tokens, bool) and error.total_tokens >= 0
            if not error_tokens_valid:
                token_usage_complete = False
                budget_failures.append("token_usage_incomplete")
            else:
                case_tokens += error.total_tokens
                total_tokens += error.total_tokens
        except RuntimeError as error:
            case_passed = False
            case_error = str(error)
            if case_error in {"total_token_budget", "token_usage_incomplete"}:
                budget_failures.append(case_error)
        except ValueError:
            case_passed = False
            case_error = "invalid_live_evidence"
            budget_failures.append(case_error)

        if total_tokens > effective_token_limit:
            case_passed = False
            case_error = "total_token_budget"
            if case_error not in budget_failures:
                budget_failures.append(case_error)

        results.append({
            "id": case["id"],
            "language": case["language"],
            "expected": expected,
            "expected_initial_decisions": sorted(expected_initial),
            "decisions": decisions,
            "passed": case_passed,
            "error_code": case_error,
            "tokens": case_tokens,
            "latency_ms": sum(case_latencies),
            "model": sorted(case_models),
        })
        if not case_passed:
            failures.append(case["id"])
        if budget_failures:
            break

    estimated_cost = (
        (total_tokens * cost_rate_microusd_per_1k_tokens + 999) // 1000
        if token_usage_complete else None
    )
    if total_tokens > max_total_tokens:
        budget_failures.append("total_token_budget")
    if estimated_cost is not None and estimated_cost > max_total_cost_microusd:
        budget_failures.append("total_cost_budget")
    if not token_usage_complete:
        budget_failures.append("token_usage_incomplete")
    budget_failures = list(dict.fromkeys(budget_failures))
    if budget_failures:
        failures.extend(item for item in budget_failures if item not in failures)

    return {
        "mode": "live-runtime-v3",
        "cases": len(cases),
        "evaluated_cases": len(results),
        "passed": sum(item["passed"] for item in results),
        "failed": len(cases) - sum(item["passed"] for item in results),
        "pass_rate": round(sum(item["passed"] for item in results) / len(cases), 4) if cases else 1.0,
        "failures": [item["id"] for item in results if not item["passed"]],
        "by_language": _language_summary(cases, results),
        "budget_failures": budget_failures,
        "gate_failures": budget_failures.copy(),
        "gate_decision": "PASS" if not failures else "FAIL",
        "model_calls": model_call_count,
        "failed_model_calls": max(0, model_call_count - sum(len(item["decisions"]) for item in results)),
        "models": sorted(model_names),
        "total_tokens": total_tokens,
        "token_usage_complete": token_usage_complete,
        "total_latency_ms": sum(model_latencies),
        "p50_latency_ms": _percentile(model_latencies, 0.50),
        "p95_latency_ms": _percentile(model_latencies, 0.95),
        "p99_latency_ms": _percentile(model_latencies, 0.99),
        "cost_rate_microusd_per_1k_tokens": cost_rate_microusd_per_1k_tokens,
        "cost_basis": "operator-configured blended effective rate; estimate, not provider invoice",
        "cost_is_estimate": True,
        "estimated_cost_microusd": estimated_cost,
        "max_total_tokens": max_total_tokens,
        "max_total_cost_microusd": max_total_cost_microusd,
        "effective_token_limit": effective_token_limit,
        "results": results,
    }


async def evaluate_live(
    cases: list[dict],
    *,
    max_total_tokens: int = 100000,
    max_total_cost_microusd: int = 500000,
    cost_rate_microusd_per_1k_tokens: int = 0,
) -> dict:
    if max_total_tokens < 1 or max_total_cost_microusd < 1 or cost_rate_microusd_per_1k_tokens < 1:
        raise ValueError("Live planner evaluation requires positive token, cost and reviewed rate limits.")
    cost_token_limit = (max_total_cost_microusd * 1000) // cost_rate_microusd_per_1k_tokens
    effective_token_limit = min(max_total_tokens, cost_token_limit)
    if effective_token_limit < 1:
        raise ValueError("The configured live evaluation cost budget cannot fund one model token.")
    settings = replace(
        evaluation_settings(),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        agent_v3_planner_cost_microusd_per_1k_tokens=cost_rate_microusd_per_1k_tokens,
    )
    planner = DeepSeekAgentPlanner(settings)
    tools = intelligent_tool_names(settings)
    failures: list[str] = []
    budget_failures: list[str] = []
    results: list[dict] = []
    latencies: list[int] = []
    total_tokens = 0
    token_usage_complete = True

    for case in cases:
        if effective_token_limit - total_tokens <= 0:
            budget_failures.append("total_token_budget")
            break
        actual: list[str] = []
        tokens = None
        latency_ms = None
        try:
            proposal, tokens, latency_ms = await planner.propose(case["goal"], tools, reason="evaluation")
            usage_valid = isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
            if not usage_valid:
                token_usage_complete = False
                raise RuntimeError("token_usage_incomplete")
            total_tokens += tokens
            if not isinstance(latency_ms, int) or isinstance(latency_ms, bool) or latency_ms < 0:
                raise ValueError("Live planner returned invalid latency metadata.")
            latencies.append(latency_ms)
            actual = [step.tool for step in proposal.steps]
            expected = case.get("expected_live_tools", case["expected_tools"])
            forbidden = set(case["forbidden_tools"])
            passed = actual == expected and not forbidden.intersection(actual)
            error_code = None if passed else "unexpected_or_forbidden_tool_sequence"
        except PlannerFailure as error:
            passed = False
            error_code = error.code
            error_tokens_valid = isinstance(error.total_tokens, int) and not isinstance(error.total_tokens, bool) and error.total_tokens >= 0
            if not error_tokens_valid:
                token_usage_complete = False
                budget_failures.append("token_usage_incomplete")
            else:
                tokens = error.total_tokens
                total_tokens += tokens
        except RuntimeError as error:
            passed = False
            error_code = str(error)
            if error_code in {"total_token_budget", "token_usage_incomplete"}:
                budget_failures.append(error_code)
        except ValueError:
            passed = False
            error_code = "invalid_live_evidence"
            budget_failures.append(error_code)
        results.append({
            "id": case["id"],
            "language": case["language"],
            "expected": case.get("expected_live_tools", case["expected_tools"]),
            "actual": actual,
            "passed": passed,
            "error_code": error_code,
            "tokens": tokens,
            "latency_ms": latency_ms,
        })
        if not passed:
            failures.append(case["id"])
        if total_tokens > effective_token_limit:
            budget_failures.append("total_token_budget")
        if budget_failures:
            break

    estimated_cost = (
        (total_tokens * cost_rate_microusd_per_1k_tokens + 999) // 1000
        if token_usage_complete else None
    )
    if total_tokens > max_total_tokens:
        budget_failures.append("total_token_budget")
    if estimated_cost is not None and estimated_cost > max_total_cost_microusd:
        budget_failures.append("total_cost_budget")
    if not token_usage_complete:
        budget_failures.append("token_usage_incomplete")
    budget_failures = list(dict.fromkeys(budget_failures))
    return {
        "mode": "live-legacy-planner",
        "cases": len(cases),
        "evaluated_cases": len(results),
        "passed": sum(item["passed"] for item in results),
        "failed": len(cases) - sum(item["passed"] for item in results),
        "pass_rate": round(sum(item["passed"] for item in results) / len(cases), 4) if cases else 1.0,
        "failures": [item["id"] for item in results if not item["passed"]],
        "by_language": _language_summary(cases, results),
        "budget_failures": budget_failures,
        "gate_failures": budget_failures.copy(),
        "gate_decision": "PASS" if not failures and not budget_failures else "FAIL",
        "model_calls": len(results),
        "models": [settings.deepseek_model],
        "total_tokens": total_tokens,
        "token_usage_complete": token_usage_complete,
        "total_latency_ms": sum(latencies),
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "p99_latency_ms": _percentile(latencies, 0.99),
        "cost_rate_microusd_per_1k_tokens": cost_rate_microusd_per_1k_tokens,
        "cost_basis": "operator-configured blended effective rate; estimate, not provider invoice",
        "cost_is_estimate": True,
        "estimated_cost_microusd": estimated_cost,
        "max_total_tokens": max_total_tokens,
        "max_total_cost_microusd": max_total_cost_microusd,
        "effective_token_limit": effective_token_limit,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate bounded Shuddho Agent routing and Runtime v3 planning.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--live", action="store_true", help="Call the configured DeepSeek planner. Never use this in CI.")
    parser.add_argument("--runtime-v3", action="store_true", help="With --live, evaluate the result-aware Runtime v3 decision contract.")
    parser.add_argument("--release-id", default="ci-agent-contract")
    parser.add_argument("--rollout", type=Path)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--max-total-tokens", type=int, default=100000)
    parser.add_argument("--max-total-cost-microusd", type=int, default=500000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runtime_v3 and not args.live:
        raise SystemExit("--runtime-v3 requires --live; CI remains provider-free.")
    rollout_sha = None
    revision = None
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
    if args.live and not args.runtime_v3 and any(not item["expected_tools"] for item in cases):
        raise SystemExit("No-tool fixtures require --runtime-v3.")
    if args.live:
        try:
            rate = int(os.environ.get("SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS", "0"))
        except (TypeError, ValueError):
            rate = 0
        if rate <= 0:
            raise SystemExit(
                "Live planner evaluation requires a reviewed positive "
                "SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS rate."
            )
        if args.runtime_v3:
            result = asyncio.run(evaluate_live_v3(
                cases,
                max_total_tokens=args.max_total_tokens,
                max_total_cost_microusd=args.max_total_cost_microusd,
                cost_rate_microusd_per_1k_tokens=rate,
            ))
        else:
            if any(
                not item["expected_tools"]
                or item.get("context")
                or item.get("expected_live_tools", item["expected_tools"]) != item["expected_tools"]
                for item in cases
            ):
                raise SystemExit("Expanded no-tool, context and multi-step fixtures require --runtime-v3.")
            result = asyncio.run(evaluate_live(
                cases,
                max_total_tokens=args.max_total_tokens,
                max_total_cost_microusd=args.max_total_cost_microusd,
                cost_rate_microusd_per_1k_tokens=rate,
            ))
    else:
        result = evaluate_offline(cases)

    failures = []
    if result["pass_rate"] < args.min_pass_rate:
        failures.append("pass_rate")
    failures.extend(result.get("budget_failures", []))
    result["gate_decision"] = "PASS" if not failures else "FAIL"
    result["gate_failures"] = list(dict.fromkeys(failures))
    result["release_id"] = args.release_id
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["fixture_sha256"] = sha256_file(args.cases)
    result["provider_model"] = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash") if args.live else None
    if rollout_sha is not None:
        result["rollout_manifest_sha256"] = rollout_sha
        result["source_revision"] = revision
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if failures:
        raise SystemExit("Agent evaluation failed: " + ", ".join(result["gate_failures"]))




if __name__ == "__main__":
    main()
