from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.release_contract import (
    ACTION_PROVIDERS,
    BASE_CAPABILITY_KEYS as CAPABILITY_KEYS,
    BASE_KILL_SWITCHES,
    OPTIONAL_CAPABILITIES,
    OPTIONAL_CAPABILITY_KEYS,
    OPTIONAL_ROLLBACK_KEYS,
    ROLLBACK_KEYS,
    required_conditional_gate_ids,
    required_feature_flags,
    validate_optional_rollback,
)
from scripts.coworker_model_evidence import (
    ModelEvidenceError,
    validate_live_model_evidence,
)
from scripts.coworker_quality_evidence import (
    QualityEvidenceError,
    validate_live_quality_evidence,
)
from scripts.staging_gate import evaluate_required as evaluate_staging, load_evidence

BASE_MONITORING = {
    "queue_age",
    "task_success",
    "provider_errors",
    "latency",
    "token_cost",
    "storage_growth",
    "agent_failures",
}
EXPECTED_KILL_SWITCHES = dict(BASE_KILL_SWITCHES)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_ref(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 500


def load_rollout(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Rollout manifest must be a JSON object")
    return value


def declared_action_providers(rollout: dict) -> set[str]:
    capabilities = rollout.get("capabilities") if isinstance(rollout, dict) else {}
    actions_enabled = (
        isinstance(capabilities, dict)
        and capabilities.get("actions") is True
    )
    value = rollout.get("action_providers") if isinstance(rollout, dict) else None
    if value is None:
        return {"google"} if actions_enabled else set()
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
    ):
        return set()
    return set(value)


def validate_rollout(rollout: dict, *, max_cohort_users: int) -> list[str]:
    failures: list[str] = []
    required_keys = {
        "release_id",
        "environment",
        "cohort",
        "capabilities",
        "rollback",
        "monitoring",
        "incident",
    }
    allowed_keys = required_keys | {"action_providers"}
    if not required_keys.issubset(rollout) or not set(rollout).issubset(allowed_keys):
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
    if (
        not isinstance(capabilities, dict)
        or not CAPABILITY_KEYS.issubset(capabilities)
        or not set(capabilities).issubset(CAPABILITY_KEYS | OPTIONAL_CAPABILITY_KEYS)
    ):
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
            for item in OPTIONAL_CAPABILITIES:
                if capabilities.get(item.capability) is not True:
                    continue
                if any(
                    capabilities.get(dependency) is not True
                    for dependency in item.dependencies
                ):
                    failures.append(f"{item.capability}_dependency")

    providers_value = rollout.get("action_providers")
    if providers_value is not None:
        providers_valid = (
            isinstance(providers_value, list)
            and len(providers_value) == len(set(providers_value))
            and all(
                isinstance(item, str) and item in ACTION_PROVIDERS
                for item in providers_value
            )
        )
        if not providers_valid:
            failures.append("action_providers")
        else:
            actions_enabled = (
                isinstance(capabilities, dict)
                and capabilities.get("actions") is True
            )
            if not actions_enabled and providers_value:
                failures.append("action_providers_without_actions")
            if actions_enabled and "google" not in providers_value:
                failures.append("action_providers_google_required")
    providers_shape_valid = (
        providers_value is None
        or (
            isinstance(providers_value, list)
            and len(providers_value) == len(set(providers_value))
            and all(
                isinstance(item, str) and item in ACTION_PROVIDERS
                for item in providers_value
            )
        )
    )
    if providers_shape_valid and isinstance(capabilities, dict):
        declared = declared_action_providers(rollout)
        for item in OPTIONAL_CAPABILITIES:
            if capabilities.get(item.capability) is not True:
                continue
            if any(
                provider not in declared
                for provider in item.required_providers
            ):
                failures.append(f"{item.capability}_provider")

    rollback = rollout["rollback"]
    if (
        not isinstance(rollback, dict)
        or not ROLLBACK_KEYS.issubset(rollback)
        or not set(rollback).issubset(ROLLBACK_KEYS | OPTIONAL_ROLLBACK_KEYS)
    ):
        failures.append("rollback")
    else:
        if not text_ref(rollback["runbook_reference"]):
            failures.append("rollback_runbook")
        for key, expected in EXPECTED_KILL_SWITCHES.items():
            if rollback.get(key) != expected:
                failures.append(key)
        if isinstance(capabilities, dict):
            failures.extend(
                validate_optional_rollback(capabilities, rollback)
            )

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


def evaluate_release(
    evidence: dict,
    rollout: dict,
    *,
    max_cohort_users: int = 25,
    quality_evidence: dict | None = None,
    model_evidence: dict | None = None,
    rollout_sha256: str | None = None,
) -> dict:
    capabilities = rollout.get("capabilities") if isinstance(rollout, dict) else {}
    if not isinstance(capabilities, dict):
        capabilities = {}
    action_providers = declared_action_providers(rollout)
    conditional_gate_ids = required_conditional_gate_ids(
        capabilities,
        action_providers,
    )
    staging = evaluate_staging(evidence, conditional_gate_ids)
    model_identity = None
    if model_evidence is not None:
        model_passed = False
        try:
            if rollout_sha256 is None:
                raise ModelEvidenceError(
                    "Rollout SHA-256 is required for planner evidence verification."
                )
            provider_model = model_evidence.get("provider_model")
            validate_live_model_evidence(
                model_evidence,
                release_id=rollout.get("release_id"),
                rollout_sha256=rollout_sha256,
                expected_provider_model=provider_model,
                min_pass_rate=1.0,
            )
            model_identity = (
                model_evidence["provider_model"],
                model_evidence["source_revision"],
            )
            model_passed = True
        except ModelEvidenceError:
            model_passed = False
        for check in staging["checks"]:
            if check["id"] == "model":
                check["passed"] = model_passed
                break
        staging["missing"] = [
            item["id"] for item in staging["checks"] if not item["passed"]
        ]
        staging["passed"] = len(staging["checks"]) - len(staging["missing"])
        staging["decision"] = "GO" if not staging["missing"] else "NO-GO"
    if quality_evidence is not None:
        quality_passed = False
        try:
            if rollout_sha256 is None:
                raise QualityEvidenceError(
                    "Rollout SHA-256 is required for quality evidence verification."
                )
            validate_live_quality_evidence(
                quality_evidence,
                release_id=rollout.get("release_id"),
                rollout_sha256=rollout_sha256,
                min_pass_rate=1.0,
                min_fact_recall=1.0,
                expected_provider_model=(
                    model_identity[0] if model_identity is not None else None
                ),
                expected_source_revision=(
                    model_identity[1] if model_identity is not None else None
                ),
            )
            quality_passed = True
        except QualityEvidenceError:
            quality_passed = False
        for check in staging["checks"]:
            if check["id"] == "quality":
                check["passed"] = quality_passed
                break
        staging["missing"] = [
            item["id"] for item in staging["checks"] if not item["passed"]
        ]
        staging["passed"] = len(staging["checks"]) - len(staging["missing"])
        staging["decision"] = "GO" if not staging["missing"] else "NO-GO"
    cohort_record = evidence.get("cohort_admission")
    cohort_ref = cohort_record.get("evidence") if isinstance(cohort_record, dict) else None
    cohort_passed = (
        isinstance(cohort_record, dict)
        and cohort_record.get("status") == "passed"
        and isinstance(cohort_ref, str)
        and bool(cohort_ref.strip())
    )
    staging["required"] += 1
    staging["checks"].append({
        "id": "cohort_admission",
        "passed": cohort_passed,
        "description": "Backend cohort admission allows invited accounts and rejects non-members before workspace provisioning.",
        "evidence": cohort_ref,
    })
    if cohort_passed:
        staging["passed"] += 1
    else:
        staging["decision"] = "NO-GO"
        staging["missing"].append("cohort_admission")
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
            "research": capabilities.get("research") is True,
            "actions": capabilities.get("actions") is True,
            "microsoft_actions": (
                capabilities.get("actions") is True
                and "microsoft" in action_providers
            ),
        },
        "action_providers": sorted(action_providers),
        "required_feature_gates": required_feature_flags(capabilities),
    }



def main() -> None:
    parser = argparse.ArgumentParser(description="Make the final Shuddho controlled-cohort GO/NO-GO decision.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--quality-eval", type=Path, required=True)
    parser.add_argument("--model-eval", type=Path, required=True)
    parser.add_argument("--max-cohort-users", type=int, default=25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.max_cohort_users < 1:
        raise SystemExit("--max-cohort-users must be positive")

    result = evaluate_release(
        load_evidence(args.evidence),
        load_rollout(args.rollout),
        max_cohort_users=args.max_cohort_users,
        quality_evidence=load_evidence(args.quality_eval),
        model_evidence=load_evidence(args.model_eval),
        rollout_sha256=file_sha256(args.rollout),
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
