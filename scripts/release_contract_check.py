from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.release_contract import (
    BASE_KILL_SWITCHES,
    OPTIONAL_CAPABILITIES,
    expected_rollout_capability_keys,
    expected_rollout_rollback_keys,
    expected_staging_evidence_keys,
)


class ReleaseContractCheckError(ValueError):
    pass


def load_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReleaseContractCheckError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ReleaseContractCheckError(f"{label} must contain a JSON object.")
    return value


def validate_staging_template(value: dict) -> list[str]:
    failures: list[str] = []
    expected = expected_staging_evidence_keys()
    actual = set(value)
    if actual != expected:
        failures.append("staging_keys")

    for key in sorted(actual & expected):
        record = value.get(key)
        if not isinstance(record, dict) or set(record) != {"status", "evidence"}:
            failures.append(f"staging_record_{key}")
            continue
        if record.get("status") != "pending" or record.get("evidence") != "":
            failures.append(f"staging_default_{key}")
    return failures


def validate_rollout_template(value: dict) -> list[str]:
    failures: list[str] = []
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, dict):
        failures.append("rollout_capabilities")
    else:
        expected_capabilities = expected_rollout_capability_keys()
        if set(capabilities) != expected_capabilities:
            failures.append("rollout_capability_keys")
        if any(not isinstance(item, bool) for item in capabilities.values()):
            failures.append("rollout_capability_types")
        for item in OPTIONAL_CAPABILITIES:
            if capabilities.get(item.capability) is not False:
                failures.append(f"rollout_optional_default_{item.capability}")

    rollback = value.get("rollback")
    if not isinstance(rollback, dict):
        failures.append("rollout_rollback")
    else:
        if set(rollback) != expected_rollout_rollback_keys():
            failures.append("rollout_rollback_keys")
        for key, expected in BASE_KILL_SWITCHES.items():
            if rollback.get(key) != expected:
                failures.append(f"rollout_{key}")
        for item in OPTIONAL_CAPABILITIES:
            if rollback.get(item.rollback_key) != item.kill_switch:
                failures.append(f"rollout_{item.rollback_key}")

    providers = value.get("action_providers")
    if providers != []:
        failures.append("rollout_action_providers_default")
    return sorted(set(failures))


def validate_templates(staging: dict, rollout: dict) -> list[str]:
    return sorted(set([
        *validate_staging_template(staging),
        *validate_rollout_template(rollout),
    ]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify checked-in controlled-release templates match the canonical "
            "Shuddho release contract."
        )
    )
    parser.add_argument(
        "--staging-template",
        type=Path,
        default=Path("docs/staging-evidence.template.json"),
    )
    parser.add_argument(
        "--rollout-template",
        type=Path,
        default=Path("docs/cohort-rollout.template.json"),
    )
    args = parser.parse_args()

    failures = validate_templates(
        load_json_object(args.staging_template, "staging evidence template"),
        load_json_object(args.rollout_template, "cohort rollout template"),
    )
    result = {
        "status": "passed" if not failures else "failed",
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(
            "Release contract template check failed: " + ", ".join(failures)
        )


if __name__ == "__main__":
    main()
