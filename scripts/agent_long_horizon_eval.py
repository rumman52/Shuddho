from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from services.coworker.agent_limits import AGENT_MAX_TOOL_STEPS
from services.coworker.agent_router import qualify_agent_goal
from services.coworker.config import Settings


DEFAULT_CASES = Path("tests/fixtures/agent_long_horizon_cases.jsonl")
REQUIRED_TARGETS = (2, 5, 10, 20)
REQUIRED_WORKFLOWS = ("research", "document", "email", "meeting", "transaction")

REQUIRED_SEQUENCE = {
    "research": (
        "search_sources",
        "inspect_sources",
        "synthesize",
        "cite",
        "deliver",
    ),
    "document": (
        "locate_document",
        "read_document",
        "draft_changes",
        "validate_output",
        "produce_output",
    ),
    "email": (
        "gather_context",
        "draft_email",
        "review_draft",
        "prepared_action",
        "immutable_preview",
        "human_approval",
        "execution_gateway",
        "provider_mutation",
        "provider_receipt",
        "deliver_receipt",
    ),
    "meeting": (
        "calendar_context",
        "document_context",
        "agenda",
        "meeting_preparation",
        "follow_up_draft",
    ),
    "transaction": (
        "fresh_terms",
        "transaction_binding",
        "prepared_action",
        "immutable_preview",
        "human_approval",
        "execution_gateway",
        "provider_mutation",
        "provider_receipt",
        "reconciliation",
        "deliver_confirmation",
    ),
}

CONSEQUENTIAL_WORKFLOWS = {"email", "transaction"}
APPROVAL_SEQUENCE = (
    "prepared_action",
    "immutable_preview",
    "human_approval",
    "execution_gateway",
    "provider_mutation",
    "provider_receipt",
)


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
        actions_enabled=True,
        personal_transactions_enabled=True,
    )


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    required = {
        "id",
        "workflow",
        "goal",
        "target_steps",
        "tool_steps",
        "expected_route",
        "required_evidence",
        "milestones",
    }
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if set(value) != required:
            raise ValueError(
                f"{path}:{line_number} must contain exactly {sorted(required)}"
            )
        if not isinstance(value["milestones"], list) or not value["milestones"]:
            raise ValueError(f"{path}:{line_number} milestones must be a non-empty list")
        rows.append(value)
    if not rows:
        raise ValueError("Long-horizon evaluation fixture is empty")
    return rows


def load_cases(path: Path) -> list[dict]:
    return _load_jsonl(path)


def _ordered(names: list[str], required: tuple[str, ...]) -> bool:
    position = -1
    for name in required:
        try:
            position = names.index(name, position + 1)
        except ValueError:
            return False
    return True


def _route(case: dict, settings: Settings) -> tuple[bool, dict]:
    expected = case["expected_route"]
    actual = qualify_agent_goal(case["goal"], settings)
    snapshot = {
        "execution": actual.execution,
        "capability": actual.capability,
        "tools": actual.tools,
        "consequential": actual.consequential,
    }
    passed = (
        snapshot["execution"] == expected["execution"]
        and snapshot["capability"] == expected["capability"]
        and snapshot["tools"] == expected["tools"]
        and snapshot["consequential"] is expected["consequential"]
    )
    return passed, snapshot


def evaluate(cases: list[dict]) -> dict:
    settings = evaluation_settings()
    results: list[dict] = []
    scenario_failures: list[str] = []
    total_milestones = 0
    completed_milestones = 0
    per_target: dict[int, list[float]] = defaultdict(list)
    per_workflow: dict[str, list[float]] = defaultdict(list)

    target_coverage = {int(case["target_steps"]) for case in cases}
    workflow_coverage = {str(case["workflow"]) for case in cases}

    for case in cases:
        case_id = str(case["id"])
        workflow = str(case["workflow"])
        target_steps = int(case["target_steps"])
        tool_steps = int(case["tool_steps"])
        milestones = list(case["milestones"])
        names = [str(item.get("name") or "") for item in milestones]
        ordinals = [int(item.get("ordinal") or 0) for item in milestones]
        states = [str(item.get("state") or "") for item in milestones]
        evidence = {
            str(token)
            for item in milestones
            for token in list(item.get("evidence") or [])
        }

        failures: list[str] = []
        if len(milestones) != target_steps:
            failures.append("target_step_count")
        if ordinals != list(range(1, len(milestones) + 1)):
            failures.append("ordinal_sequence")
        if len(set(names)) != len(names):
            failures.append("duplicate_milestone")
        if tool_steps < 0 or tool_steps > AGENT_MAX_TOOL_STEPS:
            failures.append("tool_step_safety_limit")

        completed = sum(1 for state in states if state == "completed")
        total_milestones += target_steps
        completed_milestones += min(completed, target_steps)
        completion_rate = round(completed / target_steps, 4) if target_steps else 0.0
        per_target[target_steps].append(completion_rate)
        per_workflow[workflow].append(completion_rate)
        if completion_rate != 1.0:
            failures.append("milestone_completion")

        required_sequence = REQUIRED_SEQUENCE.get(workflow)
        if required_sequence and not _ordered(names, required_sequence):
            failures.append("required_sequence")

        missing_evidence = sorted(set(case["required_evidence"]) - evidence)
        if missing_evidence:
            failures.append("required_evidence")

        if workflow in CONSEQUENTIAL_WORKFLOWS:
            if not _ordered(names, APPROVAL_SEQUENCE):
                failures.append("approval_boundary_order")
            if "provider_mutation" in names and "human_approval" in names:
                if names.index("provider_mutation") < names.index("human_approval"):
                    failures.append("provider_mutation_before_approval")

        if workflow == "transaction":
            if not _ordered(
                names,
                (
                    "fresh_terms",
                    "transaction_binding",
                    "immutable_preview",
                    "human_approval",
                    "execution_gateway",
                    "provider_receipt",
                    "reconciliation",
                ),
            ):
                failures.append("transaction_safety_order")

        route_ok, actual_route = _route(case, settings)
        if not route_ok:
            failures.append("route_contract")

        passed = not failures
        if not passed:
            scenario_failures.append(case_id)
        results.append(
            {
                "id": case_id,
                "workflow": workflow,
                "target_steps": target_steps,
                "tool_steps": tool_steps,
                "completion_rate": completion_rate,
                "passed": passed,
                "failures": failures,
                "missing_evidence": missing_evidence,
                "route": actual_route,
            }
        )

    scenario_count = len(cases)
    passed_count = scenario_count - len(scenario_failures)
    scenario_completion_rate = round(passed_count / scenario_count, 4)
    milestone_completion_rate = round(
        completed_milestones / total_milestones,
        4,
    ) if total_milestones else 0.0

    completion_by_target = {
        str(target): round(sum(values) / len(values), 4)
        for target, values in sorted(per_target.items())
    }
    completion_by_workflow = {
        workflow: round(sum(values) / len(values), 4)
        for workflow, values in sorted(per_workflow.items())
    }
    long_horizon = [
        item for item in results
        if item["target_steps"] >= 10
    ]
    long_horizon_completion_rate = round(
        sum(1 for item in long_horizon if item["passed"]) / len(long_horizon),
        4,
    ) if long_horizon else 0.0

    transaction_cases = [
        item for item in results if item["workflow"] == "transaction"
    ]
    transaction_completion_rate = round(
        sum(1 for item in transaction_cases if item["passed"]) / len(transaction_cases),
        4,
    ) if transaction_cases else 0.0

    coverage_failures: list[str] = []
    for target in REQUIRED_TARGETS:
        if target not in target_coverage:
            coverage_failures.append(f"missing_target_{target}")
    for workflow in REQUIRED_WORKFLOWS:
        if workflow not in workflow_coverage:
            coverage_failures.append(f"missing_workflow_{workflow}")

    return {
        "mode": "offline-realistic-trace",
        "scenario_count": scenario_count,
        "scenarios_passed": passed_count,
        "scenarios_failed": len(scenario_failures),
        "scenario_completion_rate": scenario_completion_rate,
        "milestone_count": total_milestones,
        "milestones_completed": completed_milestones,
        "milestone_completion_rate": milestone_completion_rate,
        "completion_rate_by_target_steps": completion_by_target,
        "completion_rate_by_workflow": completion_by_workflow,
        "long_horizon_completion_rate": long_horizon_completion_rate,
        "transaction_completion_rate": transaction_completion_rate,
        "tool_step_safety_limit": AGENT_MAX_TOOL_STEPS,
        "target_step_coverage": sorted(target_coverage),
        "workflow_coverage": sorted(workflow_coverage),
        "coverage_failures": coverage_failures,
        "scenario_failures": scenario_failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Qualify realistic multi-step Shuddho workflows. "
            "Workflow milestones are measured separately from bounded Agent tool steps."
        )
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--release-id", default="ci-long-horizon-contract")
    parser.add_argument("--min-scenario-completion-rate", type=float, default=1.0)
    parser.add_argument("--min-milestone-completion-rate", type=float, default=1.0)
    parser.add_argument("--min-long-horizon-completion-rate", type=float, default=1.0)
    parser.add_argument("--min-transaction-completion-rate", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--controlled-staging",
        action="store_true",
        help="Bind externally collected scenario evidence to an exact deployed source revision.",
    )
    args = parser.parse_args()

    cases = load_cases(args.cases)
    result = evaluate(cases)
    gate_failures = list(result["coverage_failures"])
    thresholds = {
        "scenario_completion_rate": args.min_scenario_completion_rate,
        "milestone_completion_rate": args.min_milestone_completion_rate,
        "long_horizon_completion_rate": args.min_long_horizon_completion_rate,
        "transaction_completion_rate": args.min_transaction_completion_rate,
    }
    for key, minimum in thresholds.items():
        if result[key] < minimum:
            gate_failures.append(key)

    source_revision = None
    if args.controlled_staging:
        source_revision = (
            os.environ.get("SHUDDHO_SOURCE_REVISION")
            or os.environ.get("RENDER_GIT_COMMIT")
            or ""
        ).strip().lower()
        if (
            len(source_revision) != 40
            or any(char not in "0123456789abcdef" for char in source_revision)
        ):
            raise SystemExit(
                "Controlled-staging long-horizon qualification requires a full lowercase source revision."
            )

    result["release_id"] = args.release_id
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["fixture_sha256"] = sha256_file(args.cases)
    result["source_revision"] = source_revision
    result["gate_decision"] = "PASS" if not gate_failures else "FAIL"
    result["gate_failures"] = gate_failures

    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)

    if gate_failures:
        raise SystemExit(
            "Long-horizon workflow qualification failed: "
            + ", ".join(gate_failures)
        )


if __name__ == "__main__":
    main()
