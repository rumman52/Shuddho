from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.cohort_release_gate import (
    declared_action_providers,
    evaluate_release,
    load_rollout,
)
from scripts.cohort_release_ledger import (
    ReleaseLedgerError,
    file_sha256,
    load_json_object,
    require_exact_attested_event,
    verified_release_entries,
)
from scripts.release_contract import (
    normalize_capabilities,
    required_activation_requirements,
)
from scripts.staging_gate import load_evidence


class ReleaseActivationBundleError(RuntimeError):
    pass


def load_activation_manifest(path: Path) -> dict[str, Path]:
    value = load_json_object(path, "activation manifest")
    result: dict[str, Path] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ReleaseActivationBundleError(
                "Activation manifest keys must be non-empty strings."
            )
        if not isinstance(raw, str) or not raw.strip():
            raise ReleaseActivationBundleError(
                f"Activation manifest path for {key!r} is invalid."
            )
        result[key] = Path(raw)
    return result


def _runtime_capabilities(activation: dict) -> dict | None:
    runtime = activation.get("runtime")
    if not isinstance(runtime, dict):
        return None
    capabilities = runtime.get("capabilities")
    return capabilities if isinstance(capabilities, dict) else None


def verify_activation_bundle(
    *,
    rollout_path: Path,
    staging_evidence_path: Path,
    quality_evidence_path: Path | None = None,
    model_evidence_path: Path | None = None,
    ledger_path: Path,
    activation_paths: dict[str, Path],
    current_stage: str,
    max_cohort_users: int = 25,
) -> dict:
    if not current_stage.strip() or len(current_stage) > 100:
        raise ReleaseActivationBundleError(
            "current_stage must be a non-empty string of at most 100 characters."
        )
    rollout = load_rollout(rollout_path)
    evidence = load_evidence(staging_evidence_path)
    quality_evidence = (
        load_evidence(quality_evidence_path)
        if quality_evidence_path is not None
        else None
    )
    model_evidence = (
        load_evidence(model_evidence_path)
        if model_evidence_path is not None
        else None
    )
    decision = evaluate_release(
        evidence,
        rollout,
        max_cohort_users=max_cohort_users,
        quality_evidence=quality_evidence,
        model_evidence=model_evidence,
        rollout_sha256=file_sha256(rollout_path),
    )
    if decision["decision"] != "GO_CONTROLLED_COHORT":
        failures = [
            *decision["staging"]["missing"],
            *decision["rollout_failures"],
        ]
        raise ReleaseActivationBundleError(
            "Final controlled-cohort gate is not GO: "
            + ", ".join(sorted(set(failures)))
        )

    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ReleaseActivationBundleError(
            "Reviewed rollout has no valid release_id."
        )
    capabilities = rollout.get("capabilities")
    if not isinstance(capabilities, dict):
        raise ReleaseActivationBundleError(
            "Reviewed rollout has no valid capabilities map."
        )
    providers = declared_action_providers(rollout)
    requirements = required_activation_requirements(
        capabilities,
        providers,
    )
    required_keys = {item.key for item in requirements}
    supplied_keys = set(activation_paths)
    if supplied_keys != required_keys:
        missing = sorted(required_keys - supplied_keys)
        extra = sorted(supplied_keys - required_keys)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("unexpected=" + ",".join(extra))
        raise ReleaseActivationBundleError(
            "Activation manifest does not exactly match reviewed rollout: "
            + "; ".join(details)
        )

    try:
        entries, ledger_state = verified_release_entries(
            ledger_path,
            release_id,
        )
    except ReleaseLedgerError as error:
        raise ReleaseActivationBundleError(str(error)) from None

    if not entries or not any(
        item.get("current_stage") == current_stage
        or item.get("next_stage") == current_stage
        for item in entries
    ):
        raise ReleaseActivationBundleError(
            "Release ledger has not reached current_stage."
        )

    rollout_sha = file_sha256(rollout_path)
    normalized_rollout = normalize_capabilities(capabilities)
    activation_results: dict[str, dict] = {}
    for requirement in requirements:
        path = activation_paths[requirement.key]
        activation = load_json_object(
            path,
            f"{requirement.key} activation",
        )
        if activation.get("schema_version") != 1:
            raise ReleaseActivationBundleError(
                f"{requirement.key} activation must use schema_version=1."
            )
        if activation.get("status") != requirement.status:
            raise ReleaseActivationBundleError(
                f"{requirement.key} activation has not passed."
            )
        if activation.get("release_id") != release_id:
            raise ReleaseActivationBundleError(
                f"{requirement.key} activation release_id does not match."
            )
        if (
            requirement.key != "microsoft_actions"
            and activation.get("current_stage") != current_stage
        ):
            raise ReleaseActivationBundleError(
                f"{requirement.key} activation current_stage does not match."
            )

        hashes = activation.get("artifact_sha256")
        if not isinstance(hashes, dict):
            raise ReleaseActivationBundleError(
                f"{requirement.key} activation has no artifact hashes."
            )
        if requirement.binds_rollout_manifest:
            if hashes.get("rollout_manifest") != rollout_sha:
                raise ReleaseActivationBundleError(
                    f"{requirement.key} activation does not bind this rollout manifest."
                )
        else:
            runtime_capabilities = _runtime_capabilities(activation)
            if runtime_capabilities is not None:
                if normalize_capabilities(runtime_capabilities) != normalized_rollout:
                    raise ReleaseActivationBundleError(
                        f"{requirement.key} activation runtime does not match reviewed capabilities."
                    )

        activation_sha = file_sha256(path)
        try:
            ledger_entry = require_exact_attested_event(
                entries,
                schema_version=requirement.ledger_schema_version,
                event_type=requirement.ledger_event_type,
                current_stage=current_stage,
                next_stage=None,
                artifact_key=requirement.ledger_artifact_key,
                artifact_sha256=activation_sha,
                label=f"{requirement.key} activation bundle attestation",
            )
        except ReleaseLedgerError as error:
            raise ReleaseActivationBundleError(str(error)) from None

        activation_results[requirement.key] = {
            "status": requirement.status,
            "artifact_sha256": activation_sha,
            "ledger_sequence": ledger_entry["sequence"],
            "ledger_entry_hash": ledger_entry["entry_hash"],
        }

    return {
        "schema_version": 1,
        "status": "release_activation_bundle_verified",
        "release_id": release_id,
        "current_stage": current_stage,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "rollout_manifest_sha256": rollout_sha,
        "staging_evidence_sha256": file_sha256(staging_evidence_path),
        **({
            "quality_evidence_sha256": file_sha256(quality_evidence_path),
        } if quality_evidence_path is not None else {}),
        **({
            "model_evidence_sha256": file_sha256(model_evidence_path),
        } if model_evidence_path is not None else {}),
        "required_activation_keys": [
            item.key for item in requirements
        ],
        "activations": activation_results,
        "ledger": {
            "entries": ledger_state["entries"],
            "head_entry_hash": ledger_state["head_entry_hash"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that every activation required by one reviewed Shuddho "
            "controlled-cohort rollout is present and exactly ledger-attested."
        )
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--staging-evidence", type=Path, required=True)
    parser.add_argument("--quality-eval", type=Path, required=True)
    parser.add_argument("--model-eval", type=Path, required=True)
    parser.add_argument("--release-ledger", type=Path, required=True)
    parser.add_argument("--activations", type=Path, required=True)
    parser.add_argument("--current-stage", required=True)
    parser.add_argument("--max-cohort-users", type=int, default=25)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.max_cohort_users < 1:
        raise SystemExit("--max-cohort-users must be positive")

    try:
        result = verify_activation_bundle(
            rollout_path=args.rollout,
            staging_evidence_path=args.staging_evidence,
            quality_evidence_path=args.quality_eval,
            model_evidence_path=args.model_eval,
            ledger_path=args.release_ledger,
            activation_paths=load_activation_manifest(args.activations),
            current_stage=args.current_stage,
            max_cohort_users=args.max_cohort_users,
        )
    except (ReleaseActivationBundleError, ReleaseLedgerError, ValueError) as error:
        raise SystemExit(str(error)) from None

    encoded = json.dumps(result, indent=2)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
