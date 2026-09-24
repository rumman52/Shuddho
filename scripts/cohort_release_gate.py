from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.staging_gate import evaluate as evaluate_staging, load_evidence

ACTION_PROVIDERS = {"google", "microsoft", "linkedin"}

OPTIONAL_CAPABILITY_KEYS = {"action_attachments", "action_reminders", "action_recipients", "action_document_sharing", "action_email_threading", "action_social_publishing", "action_selection", "action_proposals"}

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
OPTIONAL_ROLLBACK_KEYS = {
    "action_attachments_kill_switch",
    "action_reminders_kill_switch",
    "action_recipients_kill_switch",
    "action_document_sharing_kill_switch",
    "action_email_threading_kill_switch",
    "action_social_publishing_kill_switch",
    "action_selection_kill_switch",
    "action_proposals_kill_switch",
}
EXPECTED_KILL_SWITCHES = {
    "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
    "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
    "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
    "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
    "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
    "action_attachments_kill_switch": "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
    "action_reminders_kill_switch": "SHUDDHO_ACTION_REMINDERS_ENABLED=false",
    "action_recipients_kill_switch": "SHUDDHO_ACTION_RECIPIENTS_ENABLED=false",
    "action_document_sharing_kill_switch": "SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false",
    "action_email_threading_kill_switch": "SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false",
    "action_social_publishing_kill_switch": "SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false",
    "action_selection_kill_switch": "SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false",
    "action_proposals_kill_switch": "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false",
}


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
            if capabilities.get("action_attachments") is True and (
                not capabilities["actions"]
                or not capabilities["artifact_services"]
            ):
                failures.append("action_attachments_dependency")
            if capabilities.get("action_reminders") is True and not capabilities["actions"]:
                failures.append("action_reminders_dependency")
            if capabilities.get("action_recipients") is True and not capabilities["actions"]:
                failures.append("action_recipients_dependency")
            if capabilities.get("action_document_sharing") is True and (
                not capabilities["actions"] or not capabilities["artifact_services"]
            ):
                failures.append("action_document_sharing_dependency")
            if capabilities.get("action_email_threading") is True and not capabilities["actions"]:
                failures.append("action_email_threading_dependency")
            if capabilities.get("action_social_publishing") is True and not capabilities["actions"]:
                failures.append("action_social_publishing_dependency")
            if capabilities.get("action_selection") is True and (
                not capabilities["actions"]
                or not capabilities["agent_runtime"]
                or not capabilities["intelligent_planner"]
            ):
                failures.append("action_selection_dependency")
            if capabilities.get("action_proposals") is True and (
                not capabilities["actions"]
                or not capabilities["agent_runtime"]
                or not capabilities["intelligent_planner"]
            ):
                failures.append("action_proposals_dependency")

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
            if (
                isinstance(capabilities, dict)
                and capabilities.get("action_social_publishing") is True
                and "linkedin" not in providers_value
            ):
                failures.append("action_social_publishing_provider")

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
            if key in {"action_attachments_kill_switch", "action_reminders_kill_switch", "action_recipients_kill_switch", "action_document_sharing_kill_switch", "action_email_threading_kill_switch", "action_social_publishing_kill_switch", "action_selection_kill_switch", "action_proposals_kill_switch"}:
                continue
            if rollback.get(key) != expected:
                failures.append(key)
        if isinstance(capabilities, dict) and capabilities.get("action_attachments") is True:
            if rollback.get("action_attachments_kill_switch") != EXPECTED_KILL_SWITCHES["action_attachments_kill_switch"]:
                failures.append("action_attachments_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_reminders") is True:
            if rollback.get("action_reminders_kill_switch") != EXPECTED_KILL_SWITCHES["action_reminders_kill_switch"]:
                failures.append("action_reminders_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_recipients") is True:
            if rollback.get("action_recipients_kill_switch") != EXPECTED_KILL_SWITCHES["action_recipients_kill_switch"]:
                failures.append("action_recipients_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_document_sharing") is True:
            if rollback.get("action_document_sharing_kill_switch") != EXPECTED_KILL_SWITCHES["action_document_sharing_kill_switch"]:
                failures.append("action_document_sharing_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_email_threading") is True:
            if rollback.get("action_email_threading_kill_switch") != EXPECTED_KILL_SWITCHES["action_email_threading_kill_switch"]:
                failures.append("action_email_threading_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_social_publishing") is True:
            if rollback.get("action_social_publishing_kill_switch") != EXPECTED_KILL_SWITCHES["action_social_publishing_kill_switch"]:
                failures.append("action_social_publishing_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_selection") is True:
            if rollback.get("action_selection_kill_switch") != EXPECTED_KILL_SWITCHES["action_selection_kill_switch"]:
                failures.append("action_selection_kill_switch")
        if isinstance(capabilities, dict) and capabilities.get("action_proposals") is True:
            if rollback.get("action_proposals_kill_switch") != EXPECTED_KILL_SWITCHES["action_proposals_kill_switch"]:
                failures.append("action_proposals_kill_switch")

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
    action_providers = declared_action_providers(rollout)
    require_microsoft_actions = (
        require_actions and "microsoft" in action_providers
    )
    require_action_attachments = (
        isinstance(capabilities, dict)
        and capabilities.get("action_attachments") is True
    )
    require_action_reminders = (
        isinstance(capabilities, dict)
        and capabilities.get("action_reminders") is True
    )
    require_action_recipients = (
        isinstance(capabilities, dict)
        and capabilities.get("action_recipients") is True
    )
    require_action_document_sharing = (
        isinstance(capabilities, dict)
        and capabilities.get("action_document_sharing") is True
    )
    require_action_email_threading = (
        isinstance(capabilities, dict)
        and capabilities.get("action_email_threading") is True
    )
    require_action_social_publishing = (
        isinstance(capabilities, dict)
        and capabilities.get("action_social_publishing") is True
    )
    require_action_selection = (
        isinstance(capabilities, dict)
        and capabilities.get("action_selection") is True
    )
    require_action_proposals = (
        isinstance(capabilities, dict)
        and capabilities.get("action_proposals") is True
    )
    staging = evaluate_staging(
        evidence,
        require_research=require_research,
        require_actions=require_actions,
        require_microsoft_actions=require_microsoft_actions,
        require_action_attachments=require_action_attachments,
        require_action_reminders=require_action_reminders,
        require_microsoft_action_reminders=(
            require_action_reminders and require_microsoft_actions
        ),
        require_action_recipients=require_action_recipients,
        require_action_document_sharing=require_action_document_sharing,
        require_action_email_threading=require_action_email_threading,
        require_action_social_publishing=require_action_social_publishing,
        require_action_selection=require_action_selection,
        require_action_proposals=require_action_proposals,
    )
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
            "research": require_research,
            "actions": require_actions,
            "microsoft_actions": require_microsoft_actions,
        },
        "action_providers": sorted(action_providers),
        "required_feature_gates": {
            "action_attachments": require_action_attachments,
            "action_reminders": require_action_reminders,
            "action_recipients": require_action_recipients,
            "action_document_sharing": require_action_document_sharing,
            "action_email_threading": require_action_email_threading,
            "action_social_publishing": require_action_social_publishing,
            "action_selection": require_action_selection,
            "action_proposals": require_action_proposals,
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
