from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx


SCHEMA_VERSION = 1
EVIDENCE_KIND = "pa10_staging_release_freeze"
PRODUCTION_ENVIRONMENTS = {"prod", "production"}
ALLOWED_ACTION_PROVIDERS = {"google", "microsoft", "linkedin"}

RUNTIME_CAPABILITY_KEYS = frozenset({
    "coworker",
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
    "action_selection",
    "action_proposals",
    "negotiation_proposal_promotion",
    "agent_linkedin_proposals",
    "browser_push",
})

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
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
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


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StagingReleaseFreezeError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise StagingReleaseFreezeError(f"{label} must contain a JSON object.")
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
    if rollout.get("schema_version") != SCHEMA_VERSION:
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

    cohort = rollout.get("cohort")
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"reference", "enforced", "max_users"}
        or not text_ref(cohort.get("reference"))
        or not isinstance(cohort.get("enforced"), bool)
        or not isinstance(cohort.get("max_users"), int)
        or isinstance(cohort.get("max_users"), bool)
        or not 1 <= cohort["max_users"] <= 25
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging cohort must bind a reference, enforcement expectation and 1-25 user limit."
        )

    providers = rollout.get("action_providers")
    if (
        not isinstance(providers, list)
        or len(providers) != len(set(providers))
        or any(item not in ALLOWED_ACTION_PROVIDERS for item in providers)
    ):
        raise StagingReleaseFreezeError(
            "PA-10 staging action_providers are invalid."
        )
    if not PA10_REQUIRED_ACTION_PROVIDERS.issubset(providers):
        raise StagingReleaseFreezeError(
            "PA-10 full controlled staging requires Google and Microsoft provider availability."
        )

    capabilities = rollout.get("capabilities")
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
    build_reference: str,
    deployment_reference: str,
    synthetic_account_reference: str,
) -> dict:
    rollout = load_json(rollout_path, "PA-10 staging rollout")
    validate_rollout(rollout)
    policy = load_json(provider_policy_path, "provider-policy plan")
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

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "status": "prepared",
        "release_id": rollout["release_id"],
        "expected_source_revision": expected_source_revision,
        "expected_environment": rollout["environment"],
        "build_reference": build_reference.strip(),
        "deployment_reference": deployment_reference.strip(),
        "synthetic_account_reference": synthetic_account_reference.strip(),
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "provider_policy_sha256": sha256_file(provider_policy_path),
        "declared_capabilities": rollout["capabilities"],
        "declared_action_providers": rollout["action_providers"],
        "declared_cohort": rollout["cohort"],
        "prepared_at": utcnow_iso(),
    }


def verify_runtime(state: dict, runtime: dict) -> dict:
    if state.get("schema_version") != SCHEMA_VERSION or state.get("status") != "prepared":
        raise StagingReleaseFreezeError("Release-freeze state is invalid.")
    if runtime.get("schema_version") != 1:
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
    if capabilities != state.get("declared_capabilities"):
        raise StagingReleaseFreezeError(
            "Deployed capability set does not exactly match the reviewed staging rollout."
        )
    providers = runtime.get("action_providers")
    if providers != state.get("declared_action_providers"):
        raise StagingReleaseFreezeError(
            "Deployed action-provider set does not exactly match the reviewed staging rollout."
        )

    cohort = runtime.get("cohort")
    declared_cohort = state.get("declared_cohort")
    if not isinstance(cohort, dict) or not isinstance(declared_cohort, dict):
        raise StagingReleaseFreezeError("Runtime cohort manifest is missing.")
    if (
        cohort.get("enforced") is not declared_cohort.get("enforced")
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
        },
        "synthetic_account_reference": state["synthetic_account_reference"],
        "capabilities": capabilities,
        "action_providers": providers,
        "cohort": cohort,
        "runtime_manifest_sha256": canonical_sha256(runtime),
        "prepared_at": state["prepared_at"],
        "verified_at": verified_at,
    }


def json_object(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise StagingReleaseFreezeError(
            f"{label} returned HTTP {response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise StagingReleaseFreezeError(f"{label} did not return JSON.") from None
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
                build_reference=args.build_reference,
                deployment_reference=args.deployment_reference,
                synthetic_account_reference=args.synthetic_account_reference,
            )
            args.state.write_text(
                json.dumps(state, indent=2) + "\n",
                encoding="utf-8",
            )
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
        base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
        token = env("SHUDDHO_STAGING_TOKEN_A")
        with httpx.Client(
            base_url=base_url,
            timeout=20,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            runtime = json_object(
                client.get("/api/v1/runtime-manifest"),
                "runtime manifest",
            )
        evidence = verify_runtime(state, runtime)
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": evidence["status"],
            "output": str(args.output),
            "release": evidence["release"],
            "runtime_manifest_sha256": evidence["runtime_manifest_sha256"],
        }, indent=2))
    except (OSError, httpx.HTTPError, StagingReleaseFreezeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
