from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
EVIDENCE_KIND = "pa10_controlled_staging_bundle"
PRODUCTION_ENVIRONMENTS = {"prod", "production"}

REQUIRED_SCENARIOS = (
    "scheduled_reminder",
    "daily_coworker",
    "weekly_coworker",
    "meeting_coworker",
    "email_coworker",
    "deadline_coworker",
    "goal_driven_proactivity",
    "managed_recovery",
    "revocation",
    "duplicate_event",
    "approval_boundary",
    "prompt_injection",
    "browser_push",
    "multilingual_human_review",
    "task_economics",
)
PROVIDER_SCENARIOS = {"meeting_coworker", "email_coworker"}
REQUIRED_READ_PROVIDERS = {"google", "microsoft"}


class Pa10EvidenceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Pa10EvidenceError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise Pa10EvidenceError(f"{label} must contain a JSON object.")
    return value


def valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise Pa10EvidenceError(f"{label} must contain a timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Pa10EvidenceError(f"{label} has an invalid timestamp.") from None
    if parsed.tzinfo is None:
        raise Pa10EvidenceError(f"{label} timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc)


def release_identity(
    manifest: dict,
    *,
    rollout_path: Path,
    provider_policy_path: Path,
) -> dict:
    release = manifest.get("release")
    if not isinstance(release, dict):
        raise Pa10EvidenceError("Scenario manifest release identity is required.")
    release_id = release.get("release_id")
    source_revision = release.get("source_revision")
    environment = release.get("environment")
    deployment_reference = release.get("deployment_reference")
    if not isinstance(release_id, str) or not release_id.strip():
        raise Pa10EvidenceError("Scenario manifest release_id is required.")
    if not valid_sha(source_revision):
        raise Pa10EvidenceError(
            "Scenario manifest source_revision must be a full lowercase Git SHA-1."
        )
    if not isinstance(environment, str) or not environment.strip():
        raise Pa10EvidenceError("Scenario manifest environment is required.")
    if environment.strip().lower() in PRODUCTION_ENVIRONMENTS:
        raise Pa10EvidenceError(
            "PA-10 controlled-staging evidence must identify a non-production environment."
        )
    if (
        not isinstance(deployment_reference, str)
        or not deployment_reference.strip()
        or len(deployment_reference) > 500
    ):
        raise Pa10EvidenceError(
            "Scenario manifest deployment_reference must be non-empty and at most 500 characters."
        )

    rollout = load_json(rollout_path, "reviewed rollout manifest")
    policy = load_json(provider_policy_path, "reviewed provider-policy plan")
    if rollout.get("release_id") != release_id:
        raise Pa10EvidenceError(
            "Reviewed rollout release_id does not match the scenario manifest."
        )
    if not isinstance(policy, dict):
        raise Pa10EvidenceError("Reviewed provider-policy plan is invalid.")

    rollout_hash = sha256_file(rollout_path)
    policy_hash = sha256_file(provider_policy_path)
    declared_rollout_hash = release.get("rollout_manifest_sha256")
    declared_policy_hash = release.get("provider_policy_sha256")
    if declared_rollout_hash != rollout_hash:
        raise Pa10EvidenceError(
            "Scenario manifest rollout_manifest_sha256 does not match the reviewed rollout."
        )
    if declared_policy_hash != policy_hash:
        raise Pa10EvidenceError(
            "Scenario manifest provider_policy_sha256 does not match the reviewed provider policy."
        )

    return {
        "release_id": release_id.strip(),
        "source_revision": source_revision,
        "environment": environment.strip(),
        "deployment_reference": deployment_reference.strip(),
        "rollout_manifest_sha256": rollout_hash,
        "provider_policy_sha256": policy_hash,
    }


def compare_release(candidate: dict, expected: dict, label: str) -> None:
    for key, value in expected.items():
        if candidate.get(key) != value:
            raise Pa10EvidenceError(
                f"{label} release identity does not match {key}."
            )


def validate_release_freeze(
    freeze_path: Path,
    expected_release: dict,
) -> dict:
    freeze = load_json(freeze_path, "PA-10 staging release freeze")
    if freeze.get("schema_version") != 1:
        raise Pa10EvidenceError(
            "PA-10 staging release freeze has an unexpected schema_version."
        )
    if freeze.get("evidence_kind") != "pa10_staging_release_freeze":
        raise Pa10EvidenceError(
            "PA-10 staging release freeze has an unexpected evidence_kind."
        )
    if freeze.get("status") != "frozen":
        raise Pa10EvidenceError(
            "PA-10 staging release freeze is not frozen."
        )
    release = freeze.get("release")
    if not isinstance(release, dict):
        raise Pa10EvidenceError(
            "PA-10 staging release freeze release identity is required."
        )
    compare_release(
        release,
        expected_release,
        "PA-10 staging release freeze",
    )
    build_reference = release.get("build_reference")
    if not isinstance(build_reference, str) or not build_reference.strip():
        raise Pa10EvidenceError(
            "PA-10 staging release freeze build_reference is required."
        )
    if not valid_hash(freeze.get("runtime_manifest_sha256")):
        raise Pa10EvidenceError(
            "PA-10 staging release freeze runtime_manifest_sha256 is invalid."
        )
    prepared_at = parse_timestamp(
        freeze.get("prepared_at"),
        "PA-10 staging release freeze prepared_at",
    )
    verified_at = parse_timestamp(
        freeze.get("verified_at"),
        "PA-10 staging release freeze verified_at",
    )
    if verified_at < prepared_at:
        raise Pa10EvidenceError(
            "PA-10 staging release freeze verified_at precedes prepared_at."
        )
    return {
        "path": str(freeze_path),
        "sha256": sha256_file(freeze_path),
        "runtime_manifest_sha256": freeze["runtime_manifest_sha256"],
        "build_reference": build_reference.strip(),
        "prepared_at": prepared_at.isoformat(),
        "verified_at": verified_at.isoformat(),
    }


def verify_evidence_file(item: dict, expected_release: dict, label: str) -> dict:
    path_value = item.get("path")
    expected_hash = item.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        raise Pa10EvidenceError(f"{label} evidence path is required.")
    if not valid_hash(expected_hash):
        raise Pa10EvidenceError(f"{label} evidence sha256 is invalid.")
    path = Path(path_value)
    if not path.is_file():
        raise Pa10EvidenceError(f"{label} evidence file does not exist: {path}.")
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise Pa10EvidenceError(
            f"{label} evidence hash does not match file {path}."
        )

    if path.suffix.lower() == ".json":
        value = load_json(path, f"{label} JSON evidence")
        embedded_release = value.get("release")
        if embedded_release is not None:
            if not isinstance(embedded_release, dict):
                raise Pa10EvidenceError(
                    f"{label} JSON evidence release identity has an unexpected shape."
                )
            compare_release(
                embedded_release,
                expected_release,
                f"{label} JSON evidence",
            )
        if value.get("status") == "failed":
            raise Pa10EvidenceError(
                f"{label} JSON evidence records a failed result."
            )

    return {"path": str(path), "sha256": actual_hash}


def validate_scenario(item: dict, expected_release: dict) -> dict:
    scenario_id = item.get("id")
    if not isinstance(scenario_id, str) or scenario_id not in REQUIRED_SCENARIOS:
        raise Pa10EvidenceError(f"Unsupported PA-10 scenario id: {scenario_id!r}.")
    if item.get("status") != "passed":
        raise Pa10EvidenceError(
            f"PA-10 scenario {scenario_id} is not passed."
        )
    scenario_release = item.get("release")
    if not isinstance(scenario_release, dict):
        raise Pa10EvidenceError(
            f"PA-10 scenario {scenario_id} has no release identity."
        )
    compare_release(
        scenario_release,
        expected_release,
        f"PA-10 scenario {scenario_id}",
    )
    verified_at = parse_timestamp(
        item.get("verified_at"),
        f"PA-10 scenario {scenario_id}",
    )

    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise Pa10EvidenceError(
            f"PA-10 scenario {scenario_id} requires at least one evidence file."
        )
    verified_files = [
        verify_evidence_file(
            evidence_item,
            expected_release,
            f"PA-10 scenario {scenario_id}",
        )
        for evidence_item in evidence
        if isinstance(evidence_item, dict)
    ]
    if len(verified_files) != len(evidence):
        raise Pa10EvidenceError(
            f"PA-10 scenario {scenario_id} has an invalid evidence entry."
        )

    references = item.get("references")
    if (
        not isinstance(references, list)
        or not references
        or any(not isinstance(value, str) or not value.strip() for value in references)
    ):
        raise Pa10EvidenceError(
            f"PA-10 scenario {scenario_id} requires at least one durable evidence reference."
        )

    if scenario_id in PROVIDER_SCENARIOS:
        providers = item.get("providers")
        if (
            not isinstance(providers, list)
            or set(providers) != REQUIRED_READ_PROVIDERS
            or len(providers) != len(set(providers))
        ):
            raise Pa10EvidenceError(
                f"PA-10 scenario {scenario_id} must prove both Google and Microsoft provider flows."
            )

    if scenario_id == "scheduled_reminder":
        if item.get("agent_run_count") != 0:
            raise Pa10EvidenceError("Scheduled reminder evidence must prove zero Agent runs.")
        if item.get("notification_count") != 1:
            raise Pa10EvidenceError("Scheduled reminder evidence must prove exactly one notification.")
        if item.get("notification_kind") != "automation_reminder":
            raise Pa10EvidenceError("Scheduled reminder evidence must identify automation_reminder delivery.")

    if scenario_id == "browser_push":
        confirmation = item.get("device_confirmation_reference")
        if not isinstance(confirmation, str) or not confirmation.strip():
            raise Pa10EvidenceError(
                "Browser Push scenario requires a real device-display confirmation reference."
            )

    if scenario_id == "multilingual_human_review":
        languages = item.get("languages")
        reviewers = item.get("human_reviewers")
        if (
            not isinstance(languages, list)
            or not {"en", "bn"}.issubset(set(languages))
            or not isinstance(reviewers, int)
            or isinstance(reviewers, bool)
            or reviewers < 1
        ):
            raise Pa10EvidenceError(
                "Multilingual human review requires at least one human reviewer and both en and bn samples."
            )

    if scenario_id == "task_economics":
        sample_count = item.get("completed_useful_task_samples")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count < 1
        ):
            raise Pa10EvidenceError(
                "Task economics requires at least one measured completed useful proactive-task sample."
            )

    return {
        "id": scenario_id,
        "status": "passed",
        "verified_at": verified_at.isoformat(),
        "evidence": verified_files,
        "references": [value.strip() for value in references],
    }


def compile_bundle(
    *,
    manifest_path: Path,
    rollout_path: Path,
    provider_policy_path: Path,
    release_freeze_path: Path,
) -> dict:
    manifest = load_json(manifest_path, "PA-10 scenario manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise Pa10EvidenceError("PA-10 scenario manifest has an unexpected schema_version.")

    release = release_identity(
        manifest,
        rollout_path=rollout_path,
        provider_policy_path=provider_policy_path,
    )
    freeze = validate_release_freeze(release_freeze_path, release)
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        raise Pa10EvidenceError("PA-10 scenario manifest scenarios must be a list.")

    ids = [
        item.get("id")
        for item in scenarios
        if isinstance(item, dict)
    ]
    if len(ids) != len(scenarios):
        raise Pa10EvidenceError("PA-10 scenario manifest contains a non-object scenario.")
    if len(ids) != len(set(ids)):
        raise Pa10EvidenceError("PA-10 scenario manifest contains duplicate scenario ids.")
    missing = sorted(set(REQUIRED_SCENARIOS) - set(ids))
    extra = sorted(set(ids) - set(REQUIRED_SCENARIOS))
    if missing or extra:
        raise Pa10EvidenceError(
            "PA-10 scenario set is incomplete"
            + (f"; missing={','.join(missing)}" if missing else "")
            + (f"; extra={','.join(extra)}" if extra else "")
            + "."
        )

    verified = [validate_scenario(item, release) for item in scenarios]
    latest = max(
        parse_timestamp(item["verified_at"], f"PA-10 scenario {item['id']}")
        for item in verified
    )
    ordered = sorted(verified, key=lambda item: REQUIRED_SCENARIOS.index(item["id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "status": "passed",
        "release": release,
        "verified_at": latest.isoformat(),
        "scenario_count": len(ordered),
        "release_freeze": freeze,
        "scenarios": ordered,
        "staging_records": {
            "automations": {
                "status": "passed",
                "evidence": (
                    "PA-10 controlled-staging bundle verified all required automation, "
                    "provider, recovery, security, human multilingual review and task-economics scenarios."
                ),
                "verified_at": latest.isoformat(),
            },
            "browser_push": {
                "status": "passed",
                "evidence": (
                    "PA-10 Browser Push scenario is included in the release-bound bundle "
                    "with a real device-display confirmation reference."
                ),
                "verified_at": latest.isoformat(),
            },
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile PA-10 controlled-staging scenario evidence into one release-bound "
            "fail-closed bundle. This tool validates evidence identity and hashes; it does "
            "not manufacture live provider, device, human-review or economics evidence."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--provider-policy-plan", type=Path, required=True)
    parser.add_argument("--release-freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        bundle = compile_bundle(
            manifest_path=args.manifest,
            rollout_path=args.rollout,
            provider_policy_path=args.provider_policy_plan,
            release_freeze_path=args.release_freeze,
        )
    except Pa10EvidenceError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    args.output.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": bundle["status"],
                "output": str(args.output),
                "release": bundle["release"],
                "scenario_count": bundle["scenario_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
