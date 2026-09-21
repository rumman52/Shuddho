from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_GATES = {
    "ci": "Dedicated repository CI, including Coworker/Temporal recovery, is green.",
    "identity": "Managed identity is configured and owner isolation is verified.",
    "database": "Production PostgreSQL is configured with TLS and migrations applied.",
    "storage": "Private object storage is configured and owner-scoped download checks pass.",
    "temporal": "Production Temporal is reachable and worker restart/replay has been verified.",
    "model": "A live DeepSeek call and planner evaluation have passed in staging.",
    "backup_restore": "Database/object backup and restore has been exercised successfully.",
    "deletion": "Retention/deletion operations have been verified against owned data.",
    "parallel_restart": "Two-branch AgentWorkflow v2 restart completes without duplicate child tasks or artifacts.",
    "fan_in": "Fan-in starts only after every persisted dependency completes.",
    "flag_rollback": "Disabling Agent parallel execution routes new runs back to v1.",
}
CONDITIONAL_GATES = {
    "research": "Live search provider retrieval/citation validation passed.",
    "actions": "Live Google approval/execution/receipt validation passed without auto-approval.",
}


def load_evidence(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Staging evidence must be a JSON object")
    return value


def evaluate(evidence: dict, *, require_research: bool, require_actions: bool) -> dict:
    required = dict(REQUIRED_GATES)
    if require_research:
        required["research"] = CONDITIONAL_GATES["research"]
    if require_actions:
        required["actions"] = CONDITIONAL_GATES["actions"]
    checks = []
    for key, description in required.items():
        record = evidence.get(key)
        passed = isinstance(record, dict) and record.get("status") == "passed"
        checks.append({
            "id": key,
            "passed": passed,
            "description": description,
            "evidence": record.get("evidence") if isinstance(record, dict) else None,
        })
    missing = [item["id"] for item in checks if not item["passed"]]
    return {
        "decision": "GO" if not missing else "NO-GO",
        "required": len(checks),
        "passed": len(checks) - len(missing),
        "missing": missing,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Shuddho Coworker production staging evidence.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--require-research", action="store_true")
    parser.add_argument("--require-actions", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(load_evidence(args.evidence), require_research=args.require_research, require_actions=args.require_actions)
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if result["decision"] != "GO":
        raise SystemExit("Staging gate is NO-GO: " + ", ".join(result["missing"]))


if __name__ == "__main__":
    main()
