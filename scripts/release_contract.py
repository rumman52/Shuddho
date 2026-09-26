from __future__ import annotations

from dataclasses import dataclass


RELEASE_CONTRACT_VERSION = 1
ACTION_PROVIDERS = frozenset({"google", "microsoft", "linkedin"})

REQUIRED_GATES = {
    "ci": "Dedicated repository CI, including Coworker/Temporal recovery, is green.",
    "identity": "Managed identity is configured and owner isolation is verified.",
    "database": "Production PostgreSQL is configured with TLS and migrations applied.",
    "storage": "Private object storage is configured and owner-scoped download checks pass.",
    "temporal": "Production Temporal is reachable and worker restart/replay has been verified.",
    "model": "A live DeepSeek call and planner evaluation have passed in staging.",
    "quality": "Curated multilingual live Coworker quality/fidelity evaluation passed with recorded latency and token evidence.",
    "backup_restore": "Database/object backup and restore has been exercised successfully.",
    "deletion": "Retention/deletion operations have been verified against owned data.",
    "parallel_restart": "Two-branch AgentWorkflow v2 restart completes without duplicate child tasks or artifacts.",
    "fan_in": "Fan-in starts only after every persisted dependency completes.",
    "flag_rollback": "Disabling Agent parallel execution routes new runs back to v1.",
}
COHORT_ADMISSION_GATE = {
    "cohort_admission": (
        "Backend cohort admission allows invited accounts and rejects non-members "
        "before workspace provisioning."
    )
}

BASE_CAPABILITY_KEYS = frozenset({
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
})

BASE_KILL_SWITCHES = {
    "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
    "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
    "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
    "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
    "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
}

BASE_CONDITIONAL_GATES = {
    "research": "Live search provider retrieval/citation validation passed.",
    "actions": "Live Google approval/execution/receipt validation passed without auto-approval.",
    "microsoft_actions": "Live Microsoft Graph approval/execution/receipt validation passed without auto-approval.",
}


@dataclass(frozen=True)
class StagingGate:
    key: str
    description: str
    provider: str | None = None


@dataclass(frozen=True)
class OptionalCapability:
    capability: str
    rollback_key: str
    kill_switch: str
    dependencies: tuple[str, ...]
    staging_gates: tuple[StagingGate, ...]
    required_providers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActivationRequirement:
    key: str
    status: str
    ledger_schema_version: int
    ledger_event_type: str
    ledger_artifact_key: str
    capability: str | None = None
    provider: str | None = None
    binds_rollout_manifest: bool = True


OPTIONAL_CAPABILITIES = (
    OptionalCapability(
        capability="connector_reads",
        rollback_key="connector_reads_kill_switch",
        kill_switch="SHUDDHO_CONNECTOR_READS_ENABLED=false",
        dependencies=("connector_trust_boundary", "context_retrieval", "runtime_v3"),
        required_providers=("google",),
        staging_gates=(
            StagingGate(
                "connector_reads",
                "Live Google read consent, bounded Gmail/Calendar synchronization, cursor recovery, owner isolation, grant expiry/revocation, disconnect invalidation and Agent-context containment passed in controlled staging.",
                provider="google",
            ),
        ),
    ),
    OptionalCapability(
        capability="connector_trust_boundary",
        rollback_key="connector_trust_boundary_kill_switch",
        kill_switch="SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=false",
        dependencies=("actions",),
        staging_gates=(
            StagingGate(
                "connector_trust_boundary",
                "Deterministic connector capability contracts, audience/scope/owner/destination enforcement, revocation races, secret exclusion and fixed-egress provider dispatch passed in controlled staging.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_attachments",
        rollback_key="action_attachments_kill_switch",
        kill_switch="SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
        dependencies=("actions", "artifact_services"),
        staging_gates=(
            StagingGate(
                "action_attachments",
                "Live approved email attachment validation passed with an immutable artifact manifest and provider receipt.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_reminders",
        rollback_key="action_reminders_kill_switch",
        kill_switch="SHUDDHO_ACTION_REMINDERS_ENABLED=false",
        dependencies=("actions",),
        staging_gates=(
            StagingGate(
                "action_reminders_google",
                "Live Google Calendar explicit-reminder validation passed through immutable approval and exact provider receipt checks.",
            ),
            StagingGate(
                "action_reminders_microsoft",
                "Live Microsoft Calendar explicit-reminder validation passed through immutable approval and exact provider receipt checks.",
                provider="microsoft",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_recipients",
        rollback_key="action_recipients_kill_switch",
        kill_switch="SHUDDHO_ACTION_RECIPIENTS_ENABLED=false",
        dependencies=("actions",),
        staging_gates=(
            StagingGate(
                "action_recipients",
                "Live saved-recipient CRUD, exact value preservation, owner isolation, cross-owner denial, deletion and cleanup passed.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_document_sharing",
        rollback_key="action_document_sharing_kill_switch",
        kill_switch="SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false",
        dependencies=("actions", "artifact_services"),
        staging_gates=(
            StagingGate(
                "action_document_sharing",
                "Live Google Drive sharing passed exact owned-artifact hash binding, explicit approval, reader-only permission and provider receipt validation.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_email_threading",
        rollback_key="action_email_threading_kill_switch",
        kill_switch="SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false",
        dependencies=("actions",),
        staging_gates=(
            StagingGate(
                "action_email_threading",
                "Live Gmail owned-thread follow-up passed send-only parent binding, explicit approval, exact recipient/subject preservation and stable provider thread identity.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_social_publishing",
        rollback_key="action_social_publishing_kill_switch",
        kill_switch="SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false",
        dependencies=("actions",),
        required_providers=("linkedin",),
        staging_gates=(
            StagingGate(
                "action_social_publishing",
                "Live LinkedIn personal text publishing passed exact member/text binding, no auto-publish, wrong-hash denial, explicit approval and confirmed provider post receipt.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_selection",
        rollback_key="action_selection_kill_switch",
        kill_switch="SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false",
        dependencies=("actions", "agent_runtime", "intelligent_planner"),
        staging_gates=(
            StagingGate(
                "action_selection",
                "Live Agent planner selected only opaque attached-action handles and still paused for explicit user approval.",
            ),
        ),
    ),
    OptionalCapability(
        capability="action_proposals",
        rollback_key="action_proposals_kill_switch",
        kill_switch="SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false",
        dependencies=("actions", "agent_runtime", "intelligent_planner"),
        staging_gates=(
            StagingGate(
                "action_proposals",
                "Live Agent generated only inert typed action proposals; promotion created a separate preview and never auto-approved or executed it.",
            ),
        ),
    ),
    OptionalCapability(
        capability="agent_linkedin_proposals",
        rollback_key="agent_linkedin_proposals_kill_switch",
        kill_switch="SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false",
        dependencies=("action_proposals", "action_social_publishing"),
        staging_gates=(
            StagingGate(
                "agent_linkedin_proposals",
                "Live intelligent planner generated only an inert personal LinkedIn text proposal; wrong-hash promotion failed; exact user-selected LinkedIn promotion created one unapproved immutable preview with no provider mutation.",
            ),
        ),
    ),
    OptionalCapability(
        capability="personal_goals",
        rollback_key="personal_goals_kill_switch",
        kill_switch="SHUDDHO_PERSONAL_GOALS_ENABLED=false",
        dependencies=("agent_runtime",),
        staging_gates=(
            StagingGate(
                "personal_goals",
                "Owner-scoped persistent goal CRUD, revision conflicts, lifecycle transitions and exact AgentRun revision binding passed in controlled staging.",
            ),
        ),
    ),
    OptionalCapability(
        capability="automations",
        rollback_key="automations_kill_switch",
        kill_switch="SHUDDHO_AUTOMATIONS_ENABLED=false",
        dependencies=("personal_goals", "agent_runtime"),
        staging_gates=(
            StagingGate(
                "automations",
                "Temporal Schedule reconciliation, canonical occurrence dedupe, restart recovery, quiet hours, expiry and durable in-app notification delivery passed in controlled staging.",
            ),
        ),
    ),
    OptionalCapability(
        capability="context_retrieval",
        rollback_key="context_retrieval_kill_switch",
        kill_switch="SHUDDHO_CONTEXT_RETRIEVAL_ENABLED=false",
        dependencies=("agent_runtime", "runtime_v3", "memory"),
        staging_gates=(
            StagingGate(
                "context_retrieval",
                "Owner-scoped document context, provenance, deletion invalidation, reviewable memory proposals, cross-owner denial and restart-safe retrieval passed in controlled staging.",
            ),
        ),
    ),
    OptionalCapability(
        capability="runtime_v3",
        rollback_key="runtime_v3_kill_switch",
        kill_switch="SHUDDHO_AGENT_RUNTIME_V3_ENABLED=false",
        dependencies=("agent_runtime", "intelligent_planner"),
        staging_gates=(
            StagingGate(
                "runtime_v3",
                "Result-aware Agent Runtime v3 changed its next step from verified observations, rejected unverified completion, respected planner/tool budgets, and preserved v1/v2 workflow compatibility and rollback routing.",
            ),
        ),
    ),
)

ACTIVATION_REQUIREMENTS = (
    ActivationRequirement(
        key="connector_reads",
        status="connector_reads_verified",
        ledger_schema_version=22,
        ledger_event_type="connector_reads_verified",
        ledger_artifact_key="connector_reads_activation",
        capability="connector_reads",
    ),
    ActivationRequirement(
        key="connector_trust_boundary",
        status="connector_trust_boundary_verified",
        ledger_schema_version=21,
        ledger_event_type="connector_trust_boundary_verified",
        ledger_artifact_key="connector_trust_boundary_activation",
        capability="connector_trust_boundary",
    ),
    ActivationRequirement(
        key="microsoft_actions",
        status="microsoft_rollout_verified",
        ledger_schema_version=6,
        ledger_event_type="microsoft_rollout_verified",
        ledger_artifact_key="rollout_activation",
        provider="microsoft",
        binds_rollout_manifest=False,
    ),
    ActivationRequirement(
        key="action_selection",
        status="action_selection_verified",
        ledger_schema_version=7,
        ledger_event_type="action_selection_verified",
        ledger_artifact_key="action_selection_activation",
        capability="action_selection",
        binds_rollout_manifest=False,
    ),
    ActivationRequirement(
        key="action_proposals",
        status="action_proposals_verified",
        ledger_schema_version=8,
        ledger_event_type="action_proposals_verified",
        ledger_artifact_key="action_proposals_activation",
        capability="action_proposals",
    ),
    ActivationRequirement(
        key="action_attachments",
        status="action_attachments_verified",
        ledger_schema_version=9,
        ledger_event_type="action_attachments_verified",
        ledger_artifact_key="action_attachments_activation",
        capability="action_attachments",
    ),
    ActivationRequirement(
        key="action_reminders",
        status="action_reminders_verified",
        ledger_schema_version=10,
        ledger_event_type="action_reminders_verified",
        ledger_artifact_key="action_reminders_activation",
        capability="action_reminders",
    ),
    ActivationRequirement(
        key="action_recipients",
        status="action_recipients_verified",
        ledger_schema_version=11,
        ledger_event_type="action_recipients_verified",
        ledger_artifact_key="action_recipients_activation",
        capability="action_recipients",
    ),
    ActivationRequirement(
        key="action_document_sharing",
        status="action_document_sharing_verified",
        ledger_schema_version=12,
        ledger_event_type="action_document_sharing_verified",
        ledger_artifact_key="action_document_sharing_activation",
        capability="action_document_sharing",
    ),
    ActivationRequirement(
        key="action_email_threading",
        status="action_email_threading_verified",
        ledger_schema_version=13,
        ledger_event_type="action_email_threading_verified",
        ledger_artifact_key="action_email_threading_activation",
        capability="action_email_threading",
    ),
    ActivationRequirement(
        key="action_social_publishing",
        status="action_social_publishing_verified",
        ledger_schema_version=14,
        ledger_event_type="action_social_publishing_verified",
        ledger_artifact_key="action_social_publishing_activation",
        capability="action_social_publishing",
    ),
    ActivationRequirement(
        key="agent_linkedin_proposals",
        status="agent_linkedin_proposals_verified",
        ledger_schema_version=15,
        ledger_event_type="agent_linkedin_proposals_verified",
        ledger_artifact_key="agent_linkedin_proposals_activation",
        capability="agent_linkedin_proposals",
    ),
    ActivationRequirement(
        key="personal_goals",
        status="personal_goals_verified",
        ledger_schema_version=17,
        ledger_event_type="personal_goals_verified",
        ledger_artifact_key="personal_goals_activation",
        capability="personal_goals",
    ),
    ActivationRequirement(
        key="automations",
        status="automations_verified",
        ledger_schema_version=18,
        ledger_event_type="automations_verified",
        ledger_artifact_key="automations_activation",
        capability="automations",
    ),
    ActivationRequirement(
        key="context_retrieval",
        status="context_retrieval_verified",
        ledger_schema_version=20,
        ledger_event_type="context_retrieval_verified",
        ledger_artifact_key="context_retrieval_activation",
        capability="context_retrieval",
    ),
    ActivationRequirement(
        key="runtime_v3",
        status="runtime_v3_verified",
        ledger_schema_version=19,
        ledger_event_type="runtime_v3_verified",
        ledger_artifact_key="runtime_v3_activation",
        capability="runtime_v3",
    ),
)

ACTIVATION_REQUIREMENTS_BY_KEY = {
    item.key: item for item in ACTIVATION_REQUIREMENTS
}

OPTIONAL_CAPABILITY_KEYS = frozenset(
    item.capability for item in OPTIONAL_CAPABILITIES
)
OPTIONAL_ROLLBACK_KEYS = frozenset(
    item.rollback_key for item in OPTIONAL_CAPABILITIES
)
OPTIONAL_KILL_SWITCHES = {
    item.rollback_key: item.kill_switch
    for item in OPTIONAL_CAPABILITIES
}
EXPECTED_KILL_SWITCHES = {
    **BASE_KILL_SWITCHES,
    **OPTIONAL_KILL_SWITCHES,
}
ROLLBACK_KEYS = frozenset({"runbook_reference", *BASE_KILL_SWITCHES})

CONDITIONAL_GATES = dict(BASE_CONDITIONAL_GATES)
for _capability in OPTIONAL_CAPABILITIES:
    for _gate in _capability.staging_gates:
        if _gate.key in CONDITIONAL_GATES:
            raise RuntimeError(f"Duplicate staging gate key: {_gate.key}")
        CONDITIONAL_GATES[_gate.key] = _gate.description


def required_conditional_gate_ids(
    capabilities: dict,
    action_providers: set[str] | frozenset[str],
) -> tuple[str, ...]:
    required: list[str] = []
    if capabilities.get("research") is True:
        required.append("research")
    if capabilities.get("actions") is True:
        required.append("actions")
        if "microsoft" in action_providers:
            required.append("microsoft_actions")
    for item in OPTIONAL_CAPABILITIES:
        if capabilities.get(item.capability) is not True:
            continue
        for gate in item.staging_gates:
            if gate.provider is None or gate.provider in action_providers:
                required.append(gate.key)
    return tuple(required)


def required_feature_flags(capabilities: dict) -> dict[str, bool]:
    return {
        item.capability: capabilities.get(item.capability) is True
        for item in OPTIONAL_CAPABILITIES
    }


def normalize_capabilities(capabilities: dict) -> dict:
    normalized = dict(capabilities)
    for capability in OPTIONAL_CAPABILITY_KEYS:
        normalized.setdefault(capability, False)
    return normalized


def required_activation_requirements(
    capabilities: dict,
    action_providers: set[str] | frozenset[str],
) -> tuple[ActivationRequirement, ...]:
    normalized = normalize_capabilities(capabilities)
    required: list[ActivationRequirement] = []
    for item in ACTIVATION_REQUIREMENTS:
        if item.provider is not None:
            if (
                normalized.get("actions") is True
                and item.provider in action_providers
            ):
                required.append(item)
            continue
        if (
            item.capability is not None
            and normalized.get(item.capability) is True
        ):
            required.append(item)
    return tuple(required)


def validate_optional_capabilities(
    capabilities: dict,
    action_providers: set[str] | frozenset[str],
) -> list[str]:
    failures: list[str] = []
    for item in OPTIONAL_CAPABILITIES:
        if capabilities.get(item.capability) is not True:
            continue
        if any(capabilities.get(key) is not True for key in item.dependencies):
            failures.append(f"{item.capability}_dependency")
        if any(provider not in action_providers for provider in item.required_providers):
            failures.append(f"{item.capability}_provider")
    return failures


def validate_optional_rollback(
    capabilities: dict,
    rollback: dict,
) -> list[str]:
    failures: list[str] = []
    for item in OPTIONAL_CAPABILITIES:
        if capabilities.get(item.capability) is not True:
            continue
        if rollback.get(item.rollback_key) != item.kill_switch:
            failures.append(item.rollback_key)
    return failures


def expected_staging_evidence_keys() -> frozenset[str]:
    return frozenset({
        *REQUIRED_GATES,
        *CONDITIONAL_GATES,
        *COHORT_ADMISSION_GATE,
    })


def expected_rollout_capability_keys() -> frozenset[str]:
    return frozenset({*BASE_CAPABILITY_KEYS, *OPTIONAL_CAPABILITY_KEYS})


def expected_rollout_rollback_keys() -> frozenset[str]:
    return frozenset({*ROLLBACK_KEYS, *OPTIONAL_ROLLBACK_KEYS})


if {
    item.capability
    for item in ACTIVATION_REQUIREMENTS
    if item.capability is not None
} != OPTIONAL_CAPABILITY_KEYS:
    raise RuntimeError(
        "Every optional controlled-release capability must have one activation requirement."
    )
