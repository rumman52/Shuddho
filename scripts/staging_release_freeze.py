from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.staging_release_evidence import (
    MAX_ROLLOUT_MANIFEST_BYTES,
    StagingReleaseEvidenceError,
    parse_evidence_json,
    parse_time,
    _read_rollout_manifest,
    write_private_json,
)


SCHEMA_VERSION = 1  # PA-10 rollout / freeze evidence version
RUNTIME_SCHEMA_VERSION = 3  # /api/v1/runtime-manifest/v3
EXPECTED_SCHEMA_REVISION = "0073_worker_runtime_identity"
from services.coworker.runtime_identity import WORKER_IDENTITY_KEYS
EVIDENCE_KIND = "pa10_staging_release_freeze"
PRODUCTION_ENVIRONMENTS = {"prod", "production"}
ALLOWED_ACTION_PROVIDERS = {"google", "microsoft", "linkedin", "opentable"}

RUNTIME_CAPABILITY_KEYS = frozenset({
    "coworker",
    "conversations",
    "projects",
    "fly_github",
    "conversation_replies",
    "agent_browser_read",
    "reviewed_research",
    "work_services",
    "artifact_services",
    "agent_runtime",
    "runtime_v3",
    "context_retrieval",
    "personal_goals",
    "automations",
    "intelligent_planner",
    "memory",
    "handoffs",
    "multi_handoffs",
    "dependency_graph",
    "parallel_execution",
    "outcome_replan",
    "research",
    "actions",
    "connector_trust_boundary",
    "connector_reads",
    "browser",
    "code_execution",
    "agent_sandbox_tool",
    "action_attachments",
    "action_reminders",
    "action_recipients",
    "action_document_sharing",
    "action_email_threading",
    "action_social_publishing",
    "personal_transactions",
    "restaurant_reservations",
    "shopping_checkout",
    "travel_booking",
    "action_selection",
    "action_proposals",
    "negotiation_proposal_promotion",
    "agent_linkedin_proposals",
    "browser_push",
})

# The formal PA-10 rollout/worker/generation contract has exactly 43
# independently reviewed flags. The API also emits one *derived UI indicator*:
# it must be present, boolean, and identical to conversation_replies. Do not
# silently allow arbitrary extra keys or relabel it as independent authority.
DERIVED_RUNTIME_CAPABILITY_KEYS = frozenset({"grounded_conversation_replies"})
API_RUNTIME_CAPABILITY_KEYS = RUNTIME_CAPABILITY_KEYS | DERIVED_RUNTIME_CAPABILITY_KEYS


def api_runtime_capabilities_match_rollout(actual: object, declared: object) -> bool:
    """Validate the complete 44-field API readback against 43 reviewed flags.

    The extra UI-derived field cannot grant anything not already enabled by
    the canonical conversation_replies flag. Worker and rollout inventories
    stay strict at the original 43 keys.
    """
    return (
        isinstance(actual, dict)
        and isinstance(declared, dict)
        and set(actual) == API_RUNTIME_CAPABILITY_KEYS
        and set(declared) == RUNTIME_CAPABILITY_KEYS
        and all(type(value) is bool for value in actual.values())
        and all(type(value) is bool for value in declared.values())
        and all(actual[key] is declared[key] for key in RUNTIME_CAPABILITY_KEYS)
        and actual["grounded_conversation_replies"] is actual["conversation_replies"]
    )


PA10_REQUIRED_TRUE = frozenset({
    "coworker",
    "work_services",
    "agent_runtime",
    "runtime_v3",
    "context_retrieval",
    "personal_goals",
    "automations",
    "intelligent_planner",
    "actions",
    "connector_trust_boundary",
    "connector_reads",
    "browser_push",
})

PA10_REQUIRED_FALSE = frozenset({
    "conversations",
    "projects",
    "fly_github",
    "conversation_replies",
    "agent_browser_read",
    "reviewed_research",
    "research",
    "browser",
    "code_execution",
    "agent_sandbox_tool",
    "action_attachments",
    "action_reminders",
    "action_recipients",
    "action_document_sharing",
    "action_email_threading",
    "action_social_publishing",
    "personal_transactions",
    "restaurant_reservations",
    "shopping_checkout",
    "travel_booking",
    "action_selection",
    "action_proposals",
    "negotiation_proposal_promotion",
    "agent_linkedin_proposals",
})

PA10_REQUIRED_ACTION_PROVIDERS = frozenset({"google", "microsoft"})

EXPECTED_ROLLBACK = {
    "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
    "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
    "personal_goals_kill_switch": "SHUDDHO_PERSONAL_GOALS_ENABLED=false",
    "automations_kill_switch": "SHUDDHO_AUTOMATIONS_ENABLED=false",
    "runtime_v3_kill_switch": "SHUDDHO_AGENT_RUNTIME_V3_ENABLED=false",
    "context_retrieval_kill_switch": "SHUDDHO_CONTEXT_RETRIEVAL_ENABLED=false",
    "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
    "connector_trust_boundary_kill_switch": "SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=false",
    "connector_reads_kill_switch": "SHUDDHO_CONNECTOR_READS_ENABLED=false",
    "browser_push_kill_switch": "SHUDDHO_BROWSER_PUSH_ENABLED=false",
}

REQUIRED_MONITORING = frozenset({
    "queue_age",
    "task_success",
    "provider_errors",
    "latency",
    "token_cost",
    "agent_failures",
})


class StagingReleaseFreezeError(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE", "").lower() != "true":
        raise StagingReleaseFreezeError(
            "Set SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE=true only for an approved controlled-staging freeze."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise StagingReleaseFreezeError(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a dedicated synthetic staging identity."
        )


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise StagingReleaseFreezeError(f"{name} is required.")
    return value


def clean_origin(value: str) -> str:
    # urlparse silently strips CR/LF/TAB and leading C0 bytes; reject them
    # before parsing so a bearer-token destination is never normalized silently.
    if not isinstance(value, str) or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value):
        raise StagingReleaseFreezeError(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    clean = value.rstrip("/")
    try:
        parsed = urlparse(clean)
        hostname = parsed.hostname or ""
        port = parsed.port  # Force validation of malformed/out-of-range ports.
    except ValueError:
        raise StagingReleaseFreezeError(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        ) from None

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        is_ip_address = False
    else:
        is_ip_address = True

    labels = hostname.split(".")
    # Resolvers may accept shortened, octal or hexadecimal IPv4 notation that
    # ipaddress rejects (for example 127.1 and 0x7f.1). These are not DNS names.
    numeric_address = all(re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", label) for label in labels)
    public_dns_name = (
        hostname.isascii()
        and len(hostname) <= 253
        and len(labels) >= 2
        and all(
            1 <= len(label) <= 63
            and label[0].isalnum()
            and label[-1].isalnum()
            and all(char.isascii() and (char.isalnum() or char == "-") for char in label)
            for label in labels
        )
    )
    internal_dns_name = hostname.endswith(
        (".localhost", ".local", ".internal", ".home.arpa")
    )
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or is_ip_address
        or numeric_address
        or not public_dns_name
        or internal_dns_name
        or port == 0
    ):
        raise StagingReleaseFreezeError(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    return clean


def valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def text_ref(value: object, *, maximum: int = 500) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _load_json_snapshot(path: Path, label: str) -> tuple[dict, str]:
    """Use the existing bounded, no-follow evidence reader for one snapshot."""
    try:
        value, digest = _read_rollout_manifest(path)
    except (StagingReleaseEvidenceError, RecursionError) as error:
        raise StagingReleaseFreezeError(
            f"Could not read {label}: {error}"
        ) from None
    if not isinstance(value, dict):
        raise StagingReleaseFreezeError(f"{label} must contain a JSON object.")
    return value, digest


def load_json(path: Path, label: str) -> dict:
    value, _ = _load_json_snapshot(path, label)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: dict) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_declared_scope(cohort: object, providers: object, capabilities: object) -> None:
    """Apply the same PA-10 admission policy to rollout and prepared evidence."""
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"reference", "enforced", "max_users"}
        or not text_ref(cohort.get("reference"))
        or cohort.get("enforced") is not True
        or not isinstance(cohort.get("max_users"), int)
        or isinstance(cohort.get("max_users"), bool)
        or not 1 <= cohort["max_users"] <= 25
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging cohort must bind a reference, enforcement expectation and 1-25 user limit."
        )

    if (
        not isinstance(providers, list)
        or any(type(item) is not str or item not in ALLOWED_ACTION_PROVIDERS for item in providers)
        or len(providers) != len(set(providers))
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging action_providers are invalid."
        )
    if not PA10_REQUIRED_ACTION_PROVIDERS.issubset(providers):
        raise StagingReleaseFreezeError(
            "PA-10 full controlled staging requires Google and Microsoft provider availability."
        )

    if (
        not isinstance(capabilities, dict)
        or set(capabilities) != RUNTIME_CAPABILITY_KEYS
        or any(not isinstance(value, bool) for value in capabilities.values())
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging capabilities must exactly declare every runtime-manifest capability as a boolean."
        )
    missing = sorted(key for key in PA10_REQUIRED_TRUE if capabilities.get(key) is not True)
    if missing:
        raise StagingReleaseFreezeError(
            "PA-10 staging rollout is missing required enabled capabilities: "
            + ",".join(missing)
        )
    unexpected = sorted(key for key in PA10_REQUIRED_FALSE if capabilities.get(key) is not False)
    if unexpected:
        raise StagingReleaseFreezeError(
            "PA-10 staging rollout enables unrelated high-authority capabilities: "
            + ",".join(unexpected)
        )

def validate_rollout(rollout: dict) -> None:
    required = {
        "schema_version",
        "release_id",
        "environment",
        "cohort",
        "action_providers",
        "capabilities",
        "rollback",
        "monitoring",
        "incident",
    }
    if set(rollout) != required:
        raise StagingReleaseFreezeError(
            "PA-10 staging rollout must use the exact reviewed schema."
        )
    if type(rollout.get("schema_version")) is not int or rollout["schema_version"] != SCHEMA_VERSION:
        raise StagingReleaseFreezeError(
            "PA-10 staging rollout has an unexpected schema_version."
        )
    if not text_ref(rollout.get("release_id"), maximum=120):
        raise StagingReleaseFreezeError("PA-10 staging rollout release_id is required.")

    environment = rollout.get("environment")
    if not text_ref(environment, maximum=64):
        raise StagingReleaseFreezeError("PA-10 staging rollout environment is required.")
    if str(environment).strip().lower() in PRODUCTION_ENVIRONMENTS:
        raise StagingReleaseFreezeError(
            "PA-10 release freeze is staging-only and rejects production."
        )
    if environment != "staging":
        raise StagingReleaseFreezeError(
            "PA-10 release freeze requires the exact staging environment."
        )

    _validate_declared_scope(
        rollout.get("cohort"), rollout.get("action_providers"), rollout.get("capabilities"),
    )

    rollback = rollout.get("rollback")
    if not isinstance(rollback, dict) or set(rollback) != set(EXPECTED_ROLLBACK):
        raise StagingReleaseFreezeError(
            "PA-10 staging rollback section must declare the exact required kill switches."
        )
    for key, expected in EXPECTED_ROLLBACK.items():
        if rollback.get(key) != expected:
            raise StagingReleaseFreezeError(
                f"PA-10 staging rollback {key} must equal {expected!r}."
            )

    monitoring = rollout.get("monitoring")
    if (
        not isinstance(monitoring, dict)
        or set(monitoring) != REQUIRED_MONITORING
        or any(not text_ref(monitoring.get(key)) for key in REQUIRED_MONITORING)
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging monitoring must bind all required dashboard/alert references."
        )

    incident = rollout.get("incident")
    if (
        not isinstance(incident, dict)
        or set(incident) != {"oncall_reference", "change_reference"}
        or not text_ref(incident.get("oncall_reference"))
        or not text_ref(incident.get("change_reference"))
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging incident ownership/change references are required."
        )


def validate_provider_policy(policy: dict, release_id: str) -> None:
    if not text_ref(policy.get("release_id"), maximum=120):
        raise StagingReleaseFreezeError(
            "Reviewed provider-policy plan must bind release_id."
        )
    if policy.get("release_id") != release_id:
        raise StagingReleaseFreezeError(
            "Provider-policy release_id does not match the staging rollout."
        )


def prepare_state(
    *,
    rollout_path: Path,
    provider_policy_path: Path,
    expected_source_revision: str,
    expected_build_digest: str,
    expected_model_provider: str,
    expected_model_id: str,
    expected_task_queue: str,
    build_reference: str,
    deployment_reference: str,
    synthetic_account_reference: str,
) -> dict:
    rollout, rollout_digest = _load_json_snapshot(rollout_path, "PA-10 staging rollout")
    validate_rollout(rollout)
    policy, policy_digest = _load_json_snapshot(provider_policy_path, "provider-policy plan")
    validate_provider_policy(policy, rollout["release_id"])
    if not valid_sha(expected_source_revision):
        raise StagingReleaseFreezeError(
            "Expected source revision must be a full lowercase Git SHA-1."
        )
    for label, value in (
        ("build reference", build_reference),
        ("deployment reference", deployment_reference),
        ("synthetic account reference", synthetic_account_reference),
    ):
        if not text_ref(value):
            raise StagingReleaseFreezeError(f"{label.capitalize()} is required.")

    state = {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "status": "prepared",
        "release_id": rollout["release_id"],
        "expected_source_revision": expected_source_revision,
        "expected_build_digest": expected_build_digest,
        "expected_schema_revision": EXPECTED_SCHEMA_REVISION,
        "expected_model_provider": expected_model_provider,
        "expected_model_id": expected_model_id,
        "expected_task_queue": expected_task_queue,
        "expected_environment": rollout["environment"],
        "build_reference": build_reference.strip(),
        "deployment_reference": deployment_reference.strip(),
        "synthetic_account_reference": synthetic_account_reference.strip(),
        "rollout_manifest_sha256": rollout_digest,
        "provider_policy_sha256": policy_digest,
        "declared_capabilities": rollout["capabilities"],
        "declared_action_providers": rollout["action_providers"],
        "declared_cohort": rollout["cohort"],
        "prepared_at": utcnow_iso(),
    }
    validate_prepared_state(state)
    return state


PREPARED_STATE_KEYS = frozenset({
    "schema_version", "evidence_kind", "status", "release_id", "expected_source_revision",
    "expected_environment", "build_reference", "deployment_reference", "synthetic_account_reference",
    "rollout_manifest_sha256", "provider_policy_sha256", "declared_capabilities",
    "declared_action_providers", "declared_cohort", "prepared_at",
    "expected_build_digest", "expected_schema_revision", "expected_model_provider",
    "expected_model_id", "expected_task_queue",
})
RUNTIME_MANIFEST_KEYS = frozenset({
    "schema_version", "source_revision", "environment", "capabilities", "reviewed_skills",
    "action_providers", "cohort", "canonical_only_capabilities",
    "build_digest", "schema_revision", "model_provider", "model_id", "task_queue",
    "runtime_identity_sha256", "worker_fleet_ready", "blocked_worker_count",
    "worker_inventory", "worker_inventory_sha256",
})


def validate_prepared_state(state: object) -> None:
    """Reject invalid or out-of-policy prepared evidence before authenticated IO."""
    if (
        not isinstance(state, dict)
        or set(state) != PREPARED_STATE_KEYS
        or type(state.get("schema_version")) is not int
        or state["schema_version"] != SCHEMA_VERSION
        or state["evidence_kind"] != EVIDENCE_KIND
        or state["status"] != "prepared"
        or state["expected_environment"] != "staging"
        or not valid_sha(state["expected_source_revision"])
        or not text_ref(state["release_id"], maximum=120)
    ):
        raise StagingReleaseFreezeError("Release-freeze state is invalid.")
    for name in ("build_reference", "deployment_reference", "synthetic_account_reference"):
        if not text_ref(state[name]):
            raise StagingReleaseFreezeError(f"Release-freeze state {name} is invalid.")
    if (
        state["expected_schema_revision"] != EXPECTED_SCHEMA_REVISION
        or state["expected_model_provider"] != "deepseek"
        or not text_ref(state["expected_model_id"], maximum=120)
        or state["expected_model_id"] != state["expected_model_id"].strip()
        or not text_ref(state["expected_task_queue"], maximum=160)
        or state["expected_task_queue"] != state["expected_task_queue"].strip()
    ):
        raise StagingReleaseFreezeError("Release-freeze model, queue or schema identity is invalid.")
    for name in ("rollout_manifest_sha256", "provider_policy_sha256", "expected_build_digest"):
        digest = state[name]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise StagingReleaseFreezeError(f"Release-freeze state {name} is invalid.")
    try:
        prepared_at = parse_time(state["prepared_at"], "prepared_at")
    except (StagingReleaseEvidenceError, OverflowError, ValueError):
        raise StagingReleaseFreezeError("Release-freeze state prepared_at is invalid.") from None
    if prepared_at > datetime.now(timezone.utc):
        raise StagingReleaseFreezeError("Release-freeze state prepared_at is in the future.")
    _validate_declared_scope(
        state["declared_cohort"], state["declared_action_providers"], state["declared_capabilities"],
    )


def verify_runtime(state: dict, runtime: dict) -> dict:
    validate_prepared_state(state)
    if not isinstance(runtime, dict) or set(runtime) != RUNTIME_MANIFEST_KEYS:
        raise StagingReleaseFreezeError("Runtime manifest must contain exactly the v3 fields including reviewed_skills.")
    if type(runtime.get("schema_version")) is not int or runtime["schema_version"] != RUNTIME_SCHEMA_VERSION:
        raise StagingReleaseFreezeError(
            "Runtime manifest schema_version is unsupported."
        )
    if runtime.get("environment") != state.get("expected_environment"):
        raise StagingReleaseFreezeError(
            "Deployed runtime environment does not match the frozen staging candidate."
        )
    if str(runtime.get("environment") or "").lower() in PRODUCTION_ENVIRONMENTS:
        raise StagingReleaseFreezeError(
            "Controlled-staging freeze rejects a production runtime."
        )
    if runtime.get("source_revision") != state.get("expected_source_revision"):
        raise StagingReleaseFreezeError(
            "Deployed source revision does not match the frozen staging candidate."
        )
    if not valid_sha(runtime.get("source_revision")):
        raise StagingReleaseFreezeError(
            "Runtime manifest source_revision must be a full lowercase Git SHA-1."
        )

    capabilities = runtime.get("capabilities")
    if not api_runtime_capabilities_match_rollout(
        capabilities, state.get("declared_capabilities"),
    ):
        raise StagingReleaseFreezeError(
            "Deployed capability set does not exactly match the reviewed staging rollout."
        )
    if not isinstance(runtime.get("reviewed_skills"), dict):
        raise StagingReleaseFreezeError(
            "Runtime v3 reviewed_skills manifest must be an object."
        )
    providers = runtime.get("action_providers")
    if providers != state.get("declared_action_providers"):
        raise StagingReleaseFreezeError(
            "Deployed action-provider set does not exactly match the reviewed staging rollout."
        )

    cohort = runtime.get("cohort")
    declared_cohort = state.get("declared_cohort")
    if not isinstance(cohort, dict) or set(cohort) != {"enforced", "configured_members", "max_users"}:
        raise StagingReleaseFreezeError("Runtime cohort manifest has an unexpected schema.")
    if (
        declared_cohort.get("enforced") is not True
        or cohort.get("enforced") is not True
        or type(declared_cohort.get("max_users")) is not int
        or not 1 <= declared_cohort["max_users"] <= 25
        or type(cohort.get("max_users")) is not int
        or cohort.get("max_users") != declared_cohort.get("max_users")
        or not isinstance(cohort.get("configured_members"), int)
        or isinstance(cohort.get("configured_members"), bool)
        or cohort.get("configured_members") < 0
        or cohort.get("configured_members") > cohort.get("max_users")
    ):
        raise StagingReleaseFreezeError(
            "Deployed cohort controls do not match the reviewed staging rollout."
        )
    if declared_cohort.get("enforced") is True and cohort.get("configured_members") < 1:
        raise StagingReleaseFreezeError(
            "Cohort-enforced staging must contain at least one configured synthetic member."
        )

    # Scope checks above keep the existing precise failure diagnostics.
    # Only then validate the complete API and worker identity commitment.
    for key in ("build_digest", "schema_revision", "model_provider", "model_id", "task_queue"):
        if runtime.get(key) != state["expected_" + key]:
            raise StagingReleaseFreezeError(f"Deployed {key} does not match the frozen identity.")
    canonical_only = runtime.get("canonical_only_capabilities")
    if not isinstance(canonical_only, dict) or set(canonical_only) != {"suggestion_model_relevance"} or canonical_only["suggestion_model_relevance"] is not False:
        raise StagingReleaseFreezeError("Unreviewed canonical-only runtime authority.")
    fleet_keys = {"runtime_identity_sha256", "worker_fleet_ready", "blocked_worker_count", "worker_inventory", "worker_inventory_sha256"}
    identity = {key: value for key, value in runtime.items() if key not in fleet_keys}
    if canonical_sha256(identity) != runtime.get("runtime_identity_sha256"):
        raise StagingReleaseFreezeError("Runtime identity digest does not match the observed fields.")
    workers = runtime.get("worker_inventory")
    expected_worker = {key: runtime[key] for key in WORKER_IDENTITY_KEYS}
    if (runtime.get("worker_fleet_ready") is not True
            or type(runtime.get("blocked_worker_count")) is not int
            or runtime["blocked_worker_count"] != 0
            or not isinstance(workers, list) or not workers
            or any(not isinstance(worker, dict) or worker != expected_worker for worker in workers)
            or canonical_sha256(workers) != runtime.get("worker_inventory_sha256")):
        raise StagingReleaseFreezeError("Worker fleet does not prove matching healthy runtime identity.")

    verified_at = utcnow_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "status": "frozen",
        "release": {
            "release_id": state["release_id"],
            "source_revision": state["expected_source_revision"],
            "environment": state["expected_environment"],
            "build_reference": state["build_reference"],
            "deployment_reference": state["deployment_reference"],
            "rollout_manifest_sha256": state["rollout_manifest_sha256"],
            "provider_policy_sha256": state["provider_policy_sha256"],
            **{key: runtime[key] for key in ("build_digest", "schema_revision", "model_provider", "model_id", "task_queue", "runtime_identity_sha256")},
        },
        "synthetic_account_reference": state["synthetic_account_reference"],
        "capabilities": capabilities,
        "action_providers": providers,
        "cohort": cohort,
        "runtime_manifest_sha256": canonical_sha256(runtime),
        "worker_inventory_sha256": runtime["worker_inventory_sha256"],
        "reviewed_skills_sha256": canonical_sha256(runtime["reviewed_skills"]),
        "prepared_at": state["prepared_at"],
        "verified_at": verified_at,
    }


def json_object(response: httpx.Response, label: str, *, expected_status: int = 200) -> dict:
    if response.status_code != expected_status:
        raise StagingReleaseFreezeError(
            f"{label} returned HTTP {response.status_code}; expected {expected_status}."
        )
    if response.headers.get("content-encoding", "identity").lower().strip() != "identity":
        raise StagingReleaseFreezeError(f"{label} returned an unsupported content encoding.")
    raw = bytearray()
    try:
        for chunk in response.iter_bytes(chunk_size=65536):
            if len(raw) + len(chunk) > MAX_ROLLOUT_MANIFEST_BYTES:
                raise StagingReleaseFreezeError(f"{label} exceeds the evidence byte bound.")
            raw.extend(chunk)
        value = parse_evidence_json(bytes(raw))
    except (StagingReleaseEvidenceError, httpx.HTTPError) as error:
        raise StagingReleaseFreezeError(f"{label} did not return valid evidence JSON: {type(error).__name__}.") from None
    if not isinstance(value, dict):
        raise StagingReleaseFreezeError(f"{label} returned an unexpected shape.")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare and verify the exact non-production PA-10 controlled-staging release. "
            "The tool binds the reviewed rollout/provider policy before deployment and then "
            "proves the deployed runtime manifest exactly matches that frozen candidate."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--rollout", type=Path, required=True)
    prepare.add_argument("--provider-policy-plan", type=Path, required=True)
    prepare.add_argument("--expected-source-revision", required=True)
    prepare.add_argument("--expected-build-digest", required=True)
    prepare.add_argument("--expected-model-provider", required=True)
    prepare.add_argument("--expected-model-id", required=True)
    prepare.add_argument("--expected-task-queue", required=True)
    prepare.add_argument("--build-reference", required=True)
    prepare.add_argument("--deployment-reference", required=True)
    prepare.add_argument("--synthetic-account-reference", required=True)
    prepare.add_argument("--state", type=Path, required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--state", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        require_guard()
        if args.command == "prepare":
            state = prepare_state(
                rollout_path=args.rollout,
                provider_policy_path=args.provider_policy_plan,
                expected_source_revision=args.expected_source_revision,
                expected_build_digest=args.expected_build_digest,
                expected_model_provider=args.expected_model_provider,
                expected_model_id=args.expected_model_id,
                expected_task_queue=args.expected_task_queue,
                build_reference=args.build_reference,
                deployment_reference=args.deployment_reference,
                synthetic_account_reference=args.synthetic_account_reference,
            )
            write_private_json(args.state, state)
            print(json.dumps({
                "status": "prepared",
                "state": str(args.state),
                "release_id": state["release_id"],
                "source_revision": state["expected_source_revision"],
                "next": (
                    "Deploy exactly this candidate to the reviewed non-production environment, "
                    "then run verify against the authenticated staging runtime manifest."
                ),
            }, indent=2))
            return

        state = load_json(args.state, "release-freeze state")
        validate_prepared_state(state)
        base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
        token = env("SHUDDHO_STAGING_TOKEN_A")
        with httpx.Client(
            base_url=base_url,
            timeout=20,
            follow_redirects=False,
            # Never inherit proxy or alternate CA roots when sending a staging bearer token.
            trust_env=False,
            headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
        ) as client:
            with client.stream("GET", "/api/v1/runtime-manifest/v3") as response:
                runtime = json_object(response, "runtime manifest")
        evidence = verify_runtime(state, runtime)
        write_private_json(args.output, evidence)
        print(json.dumps({
            "status": evidence["status"],
            "output": str(args.output),
            "release": evidence["release"],
            "runtime_manifest_sha256": evidence["runtime_manifest_sha256"],
        }, indent=2))
    except (OSError, httpx.HTTPError, StagingReleaseFreezeError, StagingReleaseEvidenceError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
