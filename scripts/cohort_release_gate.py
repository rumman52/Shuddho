from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.staging_gate import evaluate as evaluate_staging, load_evidence

CAPABILITY_KEYS = {
    "coworker",
    "work_services",
    "artifact_services",
    "agent_runtime",
    "intelligent_planner",
    "memory",
    "handoffs",
    "multi_handoffs",
    "dependency_graph",
    "parallel_execution",
    "outcome_replan",
    "research",
    "actions",
}
BASE_MONITORING = {
    "queue_age",
    "task_success",
    "provider_errors",
    "latency",
    "token_cost",
    "storage_growth",
    "agent_failures",
}
ROLLBACK_KEYS = {
    "runbook_reference",
    "global_kill_switch",
    "agent_kill_switch",
    "parallel_kill_switch",
    "research_kill_switch",
    "actions_kill_switch",
}
EXPECTED_KILL_SWITCHES = {
    "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
    "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
    "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
    "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
    "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
}


def text_ref(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 500


def load_rollout(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Rollout manifest must be a JSON object")
    return value


def validate_rollout(rollout: dict, *, max_cohort_users: int) -> list[str]:
    failures: list[str] = []
    if set(rollout) != {"release_id", "environment", "cohort", "capabilities", "rollback", "monitoring", "incident"}:
        failures.append("manifest_shape")
        return failures

    if not text_ref(rollout["release_id"]):
        failures.append("release_id")
    if rollout["environment"] != "production":
        failures.append("environment")

    cohort = rollout["cohort"]
    if not isinstance(cohort, dict) or set(cohort) != {"reference", "max_users"}:
        failures.append("cohort")
    else:
        if not text_ref(cohort["reference"]):
            failures.append("cohort_reference")
        users = cohort["max_users"]
        if not isinstance(users, int) or isinstance(users, bool) or not 1 <= users <= max_cohort_users:
            failures.append("cohort_max_users")

    capabilities = rollout["capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != CAPABILITY_KEYS:
        failures.append("capabilities")
    else:
        if any(not isinstance(value, bool) for value in capabilities.values()):
            failures.append("capability_types")
        else:
            if not capabilities["coworker"] or not capabilities["work_services"]:
                failures.append("core_capabilities")
            agent_children = {
                "intelligent_planner", "memory", "handoffs", "multi_handoffs",
                "dependency_graph", "parallel_execution", "outcome_replan",
            }
            if not capabilities["agent_runtime"] and any(capabilities[key] for key in agent_children):
                failures.append("agent_dependency")
            if capabilities["multi_handoffs"] and not capabilities["handoffs"]:
                failures.append("multi_handoff_dependency")
            if capabilities["parallel_execution"] and not capabilities["dependency_graph"]:
                failures.append("parallel_dependency")
            if capabilities["outcome_replan"] and not capabilities["intelligent_planner"]:
                failures.append("replan_dependency")

    rollback = rollout["rollback"]
    if not isinstance(rollback, dict) or set(rollback) != ROLLBACK_KEYS:
        failures.append("rollback")
    else:
        if not text_ref(rollback["runbook_reference"]):
            failures.append("rollback_runbook")
        for key, expected in EXPECTED_KILL_SWITCHES.items():
            if rollback.get(key) != expected:
                failures.append(key)

    monitoring = rollout["monitoring"]
    required_monitoring = set(BASE_MONITORING)
    if isinstance(capabilities, dict):
        if capabilities.get("research") is True:
            required_monitoring.add("research")
        if capabilities.get("actions") is True:
            required_monitoring.add("actions")
    if not isinstance(monitoring, dict):
        failures.append("monitoring")
    else:
        allowed = BASE_MONITORING | {"research", "actions"}
        if not required_monitoring.issubset(monitoring) or not set(monitoring).issubset(allowed):
            failures.append("monitoring_shape")
        for key in required_monitoring:
            if not text_ref(monitoring.get(key)):
                failures.append("monitoring_" + key)

    incident = rollout["incident"]
    if not isinstance(incident, dict) or set(incident) != {"oncall_reference", "change_reference"}:
        failures.append("incident")
    else:
        if not text_ref(incident["oncall_reference"]):
            failures.append("incident_oncall")
        if not text_ref(incident["change_reference"]):
            failures.append("incident_change")

    return sorted(set(failures))


def evaluate_release(evidence: dict, rollout: dict, *, max_cohort_users: int = 25) -> dict:
    capabilities = rollout.get("capabilities") if isinstance(rollout, dict) else {}
    require_research = isinstance(capabilities, dict) and capabilities.get("research") is True
    require_actions = isinstance(capabilities, dict) and capabilities.get("actions") is True
    staging = evaluate_staging(
        evidence,
        require_research=require_research,
        require_actions=require_actions,
    )
    rollout_failures = validate_rollout(rollout, max_cohort_users=max_cohort_users)
    decision = "GO_CONTROLLED_COHORT" if staging["decision"] == "GO" and not rollout_failures else "NO-GO"
    return {
        "decision": decision,
        "release_id": rollout.get("release_id") if isinstance(rollout, dict) else None,
        "cohort_max_users": (
            rollout.get("cohort", {}).get("max_users")
            if isinstance(rollout.get("cohort"), dict) else None
        ) if isinstance(rollout, dict) else None,
        "staging": staging,
        "rollout_failures": rollout_failures,
        "required_provider_gates": {
            "research": require_research,
            "actions": require_actions,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the final Shuddho controlled-cohort GO/NO-GO decision.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--max-cohort-users", type=int, default=25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.max_cohort_users < 1:
        raise SystemExit("--max-cohort-users must be positive")

    result = evaluate_release(
        load_evidence(args.evidence),
        load_rollout(args.rollout),
        max_cohort_users=args.max_cohort_users,
    )
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if result["decision"] != "GO_CONTROLLED_COHORT":
        missing = result["staging"]["missing"] + result["rollout_failures"]
        raise SystemExit("Controlled cohort is NO-GO: " + ", ".join(missing))


if __name__ == "__main__":
    main()
