"""Fail-closed CW-02 transaction fault evidence manifest validator.

This checks claimed evidence structure only. Actual staging/process failure
injection and independent verification are separate release requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

SCENARIOS = (
    "model_429", "model_500", "model_timeout", "provider_401",
    "provider_403", "provider_429", "provider_500", "malformed_response",
    "database_disconnect", "s3_disconnect", "temporal_outage",
    "worker_crash", "api_crash", "duplicate_message",
    "lost_provider_response", "approval_after_expiration",
)

# Each matrix row describes one reviewed fault injection, not a generic
# "some mutation happened" record. Counts are provider dispatch attempts and
# independently observed applied mutations for that case's approved identity.
# Variable-boundary faults admit only explicitly listed counter pairs.
SCENARIO_CONTRACTS = {
    "model_429": {"allowed_counts": ("0:0",), "outcomes_by_counts": {"0:0": ("failed", "blocked")}},
    "model_500": {"allowed_counts": ("0:0",), "outcomes_by_counts": {"0:0": ("failed", "blocked")}},
    "model_timeout": {"allowed_counts": ("0:0",), "outcomes_by_counts": {"0:0": ("failed", "blocked")}},
    "provider_401": {"allowed_counts": ("1:0",), "outcomes_by_counts": {"1:0": ("failed", "rejected")}},
    "provider_403": {"allowed_counts": ("1:0",), "outcomes_by_counts": {"1:0": ("failed", "rejected")}},
    "provider_429": {"allowed_counts": ("1:0",), "outcomes_by_counts": {"1:0": ("failed", "rejected")}},
    "provider_500": {
        "allowed_counts": ("1:0", "1:1"),
        "outcomes_by_counts": {"1:0": ("failed",), "1:1": ("uncertain",)},
    },
    "malformed_response": {
        "allowed_counts": ("1:0", "1:1"),
        "outcomes_by_counts": {"1:0": ("failed",), "1:1": ("uncertain",)},
    },
    "database_disconnect": {
        "allowed_counts": ("0:0", "1:0", "1:1"),
        "outcomes_by_counts": {
            "0:0": ("failed", "blocked", "uncertain", "recovered"),
            "1:0": ("failed", "uncertain"),
            "1:1": ("uncertain", "recovered", "confirmed"),
        },
    },
    "s3_disconnect": {
        "allowed_counts": ("0:0", "1:0", "1:1"),
        "outcomes_by_counts": {
            "0:0": ("failed", "blocked", "recovered"),
            "1:0": ("failed", "blocked", "uncertain"),
            # The artifact failure may fail/block the overall task, but it must
            # never trigger a second external mutation. "confirmed" is not a
            # successful task result while the required artifact is unavailable.
            "1:1": ("failed", "blocked", "uncertain", "recovered"),
        },
    },
    "temporal_outage": {"allowed_counts": ("1:1",), "outcomes_by_counts": {"1:1": ("recovered", "confirmed")}},
    "worker_crash": {
        "allowed_counts": ("0:0", "1:1"),
        "outcomes_by_counts": {
            "0:0": ("uncertain", "blocked"),
            "1:1": ("uncertain", "recovered", "confirmed"),
        },
    },
    "api_crash": {"allowed_counts": ("0:0",), "outcomes_by_counts": {"0:0": ("recovered",)}},
    "duplicate_message": {"allowed_counts": ("0:0",), "outcomes_by_counts": {"0:0": ("recovered",)}},
    "lost_provider_response": {"allowed_counts": ("1:1",), "outcomes_by_counts": {"1:1": ("uncertain",)}},
    "approval_after_expiration": {"allowed_counts": ("0:0",), "outcomes_by_counts": {"0:0": ("rejected", "blocked")}},
}
NO_APPLIED_MUTATION = frozenset(
    name for name, contract in SCENARIO_CONTRACTS.items()
    if all(pair.split(":")[1] == "0" for pair in contract["allowed_counts"])
)
NO_DISPATCH = frozenset(
    name for name, contract in SCENARIO_CONTRACTS.items()
    if all(pair.split(":")[0] == "0" for pair in contract["allowed_counts"])
)
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


def _timestamp_valid(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return stamp.tzinfo is not None and stamp.utcoffset() is not None


def _validate_scenario_contract(name: str, attempts: int, applied: int, outcome: str) -> list[str]:
    contract = SCENARIO_CONTRACTS[name]
    pair = f"{attempts}:{applied}"
    problems = []
    if pair not in contract["allowed_counts"]:
        problems.append(
            f"{name}: mutation counts {pair} violate the scenario contract; "
            f"expected one of {', '.join(contract['allowed_counts'])}"
        )
        return problems
    allowed_outcomes = contract["outcomes_by_counts"][pair]
    if outcome not in allowed_outcomes:
        problems.append(
            f"{name}: outcome {outcome!r} conflicts with mutation counts {pair}; "
            f"expected one of {', '.join(allowed_outcomes)}"
        )
    return problems


def verify_evidence_files(document: dict, directory: Path) -> list[str]:
    """Integrity checks only: independent staging/provenance audit is still required."""
    problems = []
    base = directory.resolve()
    if not base.is_dir():
        return ["evidence directory does not exist"]
    for entry in document.get("scenarios", []):
        if not isinstance(entry, dict) or entry.get("id") not in SCENARIOS:
            continue
        name = entry["id"]
        if entry.get("evidence_file") != f"{name}.json":
            continue
        path = base / f"{name}.json"
        if path.is_symlink() or not path.is_file() or path.resolve().parent != base:
            problems.append(f"{name}: evidence file missing or unsafe")
            continue
        try:
            if path.stat().st_size > MAX_EVIDENCE_BYTES:
                problems.append(f"{name}: evidence file too large")
                continue
            raw = path.read_bytes()
            if len(raw) > MAX_EVIDENCE_BYTES:
                problems.append(f"{name}: evidence file too large")
                continue
            if hashlib.sha256(raw).hexdigest() != entry.get("evidence_sha256"):
                problems.append(f"{name}: evidence hash mismatch")
                continue
            record = json.loads(raw)
        except (OSError, ValueError, UnicodeError):
            problems.append(f"{name}: unreadable evidence JSON")
            continue
        if not isinstance(record, dict):
            problems.append(f"{name}: evidence record must be an object")
            continue
        expected = {
            "scenario_id": name,
            "source_revision": document.get("source_revision"),
            "rollout_id": document.get("rollout_id"),
            "test_run_id": entry.get("test_run_id"),
            "observed_at": entry.get("observed_at"),
            "attempted_mutations": entry.get("attempted_mutations"),
            "applied_mutations": entry.get("applied_mutations"),
            "outcome": entry.get("outcome"),
        }
        if any(record.get(key) != value for key, value in expected.items()):
            problems.append(f"{name}: evidence identity/counter mismatch")
        if record.get("provider_observation_source") not in ("provider_sandbox", "provider_audit"):
            problems.append(f"{name}: provider-side observer source required")
        reference = record.get("provider_observation_reference")
        if not isinstance(reference, str) or not reference.strip():
            problems.append(f"{name}: provider-side observation reference required")
    return problems


def qualify(document: dict, *, expected_revision: str, expected_rollout: str) -> list[str]:
    """Return qualification rejection reasons; never assume success."""
    problems: list[str] = []
    if document.get("schema_version") != 1:
        problems.append("schema_version must equal 1")
    if not expected_revision or document.get("source_revision") != expected_revision:
        problems.append("source_revision mismatch")
    if not expected_rollout or document.get("rollout_id") != expected_rollout:
        problems.append("rollout_id mismatch")
    entries = document.get("scenarios")
    if not isinstance(entries, list):
        return problems + ["scenarios must be a list"]
    seen: set[str] = set()
    run_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append("scenario entry is not an object")
            continue
        name = entry.get("id")
        if not isinstance(name, str) or name not in SCENARIOS:
            problems.append(f"unrecognized scenario: {name!r}")
            continue
        if name in seen:
            problems.append(f"duplicate scenario: {name}")
        seen.add(name)
        if entry.get("result") != "passed":
            problems.append(f"{name}: result is not passed")
        if entry.get("environment") != "staging":
            problems.append(f"{name}: staging environment evidence required")
        for field in ("test_run_id", "evidence_sha256", "operator", "observed_at"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{name}: missing {field}")
        run_id = entry.get("test_run_id")
        if isinstance(run_id, str) and run_id.strip():
            if run_id in run_ids:
                problems.append(f"{name}: duplicate test_run_id")
            run_ids.add(run_id)
        if not _timestamp_valid(entry.get("observed_at")):
            problems.append(f"{name}: observed_at must include a timezone")
        if entry.get("evidence_file") != f"{name}.json":
            problems.append(f"{name}: evidence_file must be {name}.json")
        digest = entry.get("evidence_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            problems.append(f"{name}: evidence_sha256 must be lowercase SHA-256")
        attempts = entry.get("attempted_mutations")
        applied = entry.get("applied_mutations")
        if type(attempts) is not int or type(applied) is not int or attempts < 0 or applied < 0 or applied > 1:
            problems.append(f"{name}: invalid mutation counters")
        elif applied > attempts:
            problems.append(f"{name}: applied mutations exceed attempts")
        if name in NO_APPLIED_MUTATION and applied != 0:
            problems.append(f"{name}: expected zero applied provider mutations")
        if name in NO_DISPATCH and attempts != 0:
            problems.append(f"{name}: expected zero provider dispatch attempts")
        if name == "lost_provider_response" and (attempts != 1 or applied != 1):
            problems.append(f"{name}: must demonstrate one submission and one provider mutation")
        if entry.get("outcome") not in ("rejected", "failed", "uncertain", "confirmed", "recovered", "blocked"):
            problems.append(f"{name}: missing explicit outcome")
        elif type(attempts) is int and type(applied) is int:
            problems.extend(_validate_scenario_contract(name, attempts, applied, entry["outcome"]))
    for name in SCENARIOS:
        if name not in seen:
            problems.append(f"missing scenario: {name}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--rollout-id", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="Directory containing one checksummed staging evidence JSON per scenario")
    args = parser.parse_args()
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("evidence must be a JSON object")
        problems = qualify(document, expected_revision=args.source_revision, expected_rollout=args.rollout_id)
        problems.extend(verify_evidence_files(document, args.evidence_dir))
    except (OSError, ValueError) as error:
        problems = [str(error)]
    if problems:
        for problem in problems:
            print(f"NOT QUALIFIED: {problem}")
        return 1
    print("CW-02 evidence structure/hashes pass; independent staging provenance/recovery NOT certified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
