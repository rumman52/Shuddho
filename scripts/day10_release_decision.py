"""Fail-closed Day 10 evidence handoff. This tool NEVER activates a cohort.

Evidence is read-only and must be independently produced and reviewed; a JSON
receipt is not proof that a live operation occurred or that its author is D.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts.cohort_release_gate import evaluate_release

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
CELLS = {(workflow, language) for workflow in ("research_brief", "project_report_email") for language in ("bn", "en")}
PROOFS = ("rollback", "cancellation", "paused_schedule", "owner_isolation")


def read_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read {path.name}: {type(exc).__name__}") from None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def time_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.tzinfo is not None and stamp.astimezone(timezone.utc) <= datetime.now(timezone.utc)
    except ValueError:
        return False


def bound(row: object, release: str, revision: str, digest: str) -> bool:
    return (isinstance(row, dict) and row.get("release_id") == release
            and row.get("source_revision") == revision
            and row.get("rollout_manifest_sha256") == digest)


def proof_ok(row: object, release: str, revision: str, digest: str) -> bool:
    return (bound(row, release, revision, digest) and row.get("status") == "passed"
            and isinstance(row.get("evidence_ref"), str) and bool(row["evidence_ref"].strip())
            and time_ok(row.get("verified_at")))


def holdout_ok(value: object, release: str, revision: str, digest: str) -> bool:
    if not bound(value, release, revision, digest) or value.get("custody_established") is not True:
        return False
    custody = value.get("custody_receipt")
    if (not proof_ok(custody, release, revision, digest)
            or custody.get("independent_d_controls_access") is not True
            or custody.get("developer_negative_read_denied") is not True):
        return False
    if value.get("mode") != "independent_human_holdout" or value.get("generation_identity_verified") is not True:
        return False
    reviewers = value.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) != 2 or any(not isinstance(r, str) or not r.strip() for r in reviewers) or reviewers[0] == reviewers[1]:
        return False
    rows = value.get("cases")
    if not isinstance(rows, list) or len(rows) != 40:
        return False
    ids, counts, accepted = set(), Counter(), Counter()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            return False
        ids.add(row["id"])
        cell = (row.get("workflow"), row.get("language"))
        if cell not in CELLS or type(row.get("accepted")) is not bool:
            return False
        # Two-reviewer 8-point rubric, no zero scores; each accepted case >=7/8.
        scores = row.get("reviewer_scores")
        if not isinstance(scores, list) or len(scores) != 2 or any(type(s) is not int or not 1 <= s <= 8 for s in scores):
            return False
        if row["accepted"] and min(scores) < 7:
            return False
        counts[cell] += 1
        accepted[cell] += int(row["accepted"])
    return all(counts[cell] == 10 and accepted[cell] >= 9 for cell in CELLS) and sum(accepted.values()) >= 36


def operated_proof_ok(kind: str, value: object, release: str, revision: str, digest: str) -> bool:
    if not proof_ok(value, release, revision, digest):
        return False
    if kind == "rollback":
        switches = value.get("kill_switches_verified")
        return (isinstance(switches, list)
                and all(isinstance(item, str) for item in switches)
                and {"SHUDDHO_COWORKER_ENABLED=false", "SHUDDHO_AGENT_RUNTIME_ENABLED=false"}.issubset(set(switches))
                and value.get("worker_stop_observed") is True
                and value.get("restoration_verified") is True)
    if kind == "cancellation":
        return (isinstance(value.get("cancelled_run_id"), str) and bool(value["cancelled_run_id"].strip())
                and type(value.get("late_side_effects")) is int and value["late_side_effects"] == 0)
    if kind == "paused_schedule":
        return (isinstance(value.get("schedule_id"), str) and bool(value["schedule_id"].strip())
                and type(value.get("executions_while_paused")) is int and value["executions_while_paused"] == 0)
    if kind == "owner_isolation":
        return (isinstance(value.get("owner_a_ref"), str) and bool(value["owner_a_ref"].strip())
                and isinstance(value.get("owner_b_ref"), str) and bool(value["owner_b_ref"].strip())
                and value["owner_a_ref"] != value["owner_b_ref"]
                and value.get("cross_owner_denied") is True)
    return False


def recovery_ok(value: object, release: str, revision: str, digest: str) -> bool:
    if not bound(value, release, revision, digest):
        return False
    rows = value.get("scenarios")
    if not isinstance(rows, list) or len(rows) != 20:
        return False
    ids, refs = set(), set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            return False
        ids.add(row["id"])
        if not proof_ok(row, release, revision, digest) or row["evidence_ref"] in refs:
            return False
        refs.add(row["evidence_ref"])
    return True


def golden_ok(value: object, release: str, revision: str, digest: str) -> bool:
    return (proof_ok(value, release, revision, digest)
            and value.get("scenario") == "integrated_multi_turn"
            and isinstance(value.get("run_id"), str) and bool(value["run_id"].strip())
            and type(value.get("turns")) is int and value["turns"] >= 2
            and value.get("cancellation_checked") is True
            and value.get("owner_isolation_checked") is True)


def decide(rollout: dict, rollout_hash: str, *, revision: str, artifacts: dict[str, dict | None]) -> dict:
    """Use the canonical cohort gate unchanged; add stricter Day-10 exact-release proofs."""
    release = rollout.get("release_id")
    blockers: list[str] = []
    if not isinstance(release, str) or not release.strip() or not SHA.fullmatch(revision) or not DIGEST.fullmatch(rollout_hash):
        return {"decision": "SOURCE_ONLY", "canonical_decision": "NO-GO", "blockers": ["invalid_release_identity"]}
    def need(name: str, ok: bool) -> None:
        if not ok:
            blockers.append(name)

    cohort = rollout.get("cohort")
    cohort_limit = cohort.get("max_users") if isinstance(cohort, dict) else None
    need("pilot_cohort_5_to_10", type(cohort_limit) is int and 5 <= cohort_limit <= 10)
    api = artifacts.get("api")
    capabilities = rollout.get("capabilities")
    need("api_runtime_manifest_v2_exact_sha_and_flags", (
        isinstance(api, dict) and api.get("schema_version") == 2
        and api.get("source_revision") == revision
        and api.get("environment") == rollout.get("environment")
        and isinstance(api.get("capabilities"), dict)
        and isinstance(capabilities, dict)
        and all(type(v) is bool for v in api["capabilities"].values())
        and all(api["capabilities"].get(k) is v for k, v in capabilities.items())
        and not any(v is True for k, v in api["capabilities"].items() if k not in capabilities)
        and isinstance(api.get("reviewed_skills"), dict)
        and api.get("action_providers") == rollout.get("action_providers", [])
        and isinstance(api.get("cohort"), dict)
        and api["cohort"].get("enforced") is True
        and type(api["cohort"].get("max_users")) is int
        and api["cohort"]["max_users"] == cohort_limit
        and type(api["cohort"].get("configured_members")) is int
        and 0 <= api["cohort"]["configured_members"] <= cohort_limit
    ))
    schema = artifacts.get("schema")
    need("database_schema_api_worker_exact", proof_ok(schema, release, revision, rollout_hash)
         and isinstance(schema.get("migration_revision"), str) and bool(schema["migration_revision"].strip())
         and schema.get("api_revision") == schema["migration_revision"]
         and schema.get("worker_revision") == schema["migration_revision"])
    worker = artifacts.get("worker")
    need("worker_exact_sha_and_deployment_receipt", proof_ok(worker, release, revision, rollout_hash)
         and isinstance(worker.get("deployment_reference"), str) and bool(worker["deployment_reference"].strip()))
    ci = artifacts.get("ci")
    need("final_head_ci", bound(ci, release, revision, rollout_hash)
         and ci.get("status") == "passed"
         and isinstance(ci.get("workflow_run_url"), str) and ci["workflow_run_url"].startswith("https://github.com/")
         and isinstance(ci.get("required_checks"), dict)
         and all(ci["required_checks"].get(key) == "success" for key in
                 ("test-and-build", "frontend", "coworker", "governance-audit", "ci-merge-gate")))
    for key in PROOFS:
        need("operated_" + key, operated_proof_ok(key, artifacts.get(key), release, revision, rollout_hash))
    golden = artifacts.get("golden")
    need("final_sha_integrated_golden", golden_ok(golden, release, revision, rollout_hash))
    model = artifacts.get("model")
    need("final_golden_provider_matches_live_gates", golden_ok(golden, release, revision, rollout_hash)
         and isinstance(model, dict) and isinstance(model.get("provider_model"), str)
         and golden.get("provider_model") == model["provider_model"])
    first_run = artifacts.get("day9_first_run")
    need("preserved_day9_first_run", isinstance(first_run, dict)
         and first_run.get("release_id") == release
         and isinstance(first_run.get("source_revision"), str) and bool(SHA.fullmatch(first_run["source_revision"]))
         and isinstance(first_run.get("rollout_manifest_sha256"), str)
         and bool(DIGEST.fullmatch(first_run["rollout_manifest_sha256"]))
         and first_run.get("run_kind") == "first_run"
         and isinstance(first_run.get("run_id"), str) and bool(first_run["run_id"].strip())
         and isinstance(first_run.get("scores"), dict) and bool(first_run["scores"]))
    need("separate_final_rerun", golden_ok(golden, release, revision, rollout_hash)
         and isinstance(first_run, dict) and first_run.get("run_id") != golden.get("run_id"))
    need("independent_day9_holdout_36_of_40", holdout_ok(artifacts.get("holdout"), release, revision, rollout_hash))
    need("twenty_operated_recovery_scenarios", recovery_ok(artifacts.get("recovery"), release, revision, rollout_hash))
    canonical = {"decision": "NO-GO"}
    if all(artifacts.get(k) is not None for k in ("staging", "quality", "model")):
        try:
            canonical = evaluate_release(
                artifacts["staging"], rollout, max_cohort_users=10,
                quality_evidence=artifacts["quality"], model_evidence=artifacts["model"],
                artifact_quality_evidence=artifacts.get("artifact_quality"),
                rollout_sha256=rollout_hash,
            )
        except (ValueError, TypeError, KeyError) as exc:
            blockers.append("canonical_gate_invalid_input:" + type(exc).__name__)
    if canonical.get("decision") != "GO_CONTROLLED_COHORT":
        blockers.append("canonical_GO_CONTROLLED_COHORT")
    for key in ("model", "quality"):
        item = artifacts.get(key)
        need(key + "_exact_sha_and_provider", bound(item, release, revision, rollout_hash)
             and isinstance(item.get("provider_model"), str) and bool(item["provider_model"].strip())
             and isinstance(artifacts.get("model"), dict) and item.get("provider_model") == artifacts["model"].get("provider_model"))
    # Human authorization is not a deploy API call; the operator must verify its authenticity.
    approval = artifacts.get("approval")
    approved = (bound(approval, release, revision, rollout_hash)
                and approval.get("explicit_separate_authorization") is True
                and isinstance(approval.get("reference"), str) and bool(approval["reference"].strip())
                and isinstance(approval.get("founder"), str) and bool(approval["founder"].strip())
                and isinstance(approval.get("owner_c"), str) and bool(approval["owner_c"].strip())
                and type(approval.get("max_users")) is int
                and 5 <= approval["max_users"] <= 10
                and approval["max_users"] == cohort_limit)
    if not approved:
        blockers.append("separate_founder_and_C_pilot_authorization")
    blockers = sorted(set(blockers))
    return {
        "schema_version": 1,
        "release_id": release,
        "source_revision": revision,
        "rollout_manifest_sha256": rollout_hash,
        "scorecard": {
            "day9_first_run_scores": first_run.get("scores") if isinstance(first_run, dict) else None,
            "day9_first_run_run_id": first_run.get("run_id") if isinstance(first_run, dict) else None,
            "final_golden_run_id": golden.get("run_id") if isinstance(golden, dict) else None,
            "heldout_human_accepted": sum(bool(c.get("accepted")) for c in artifacts["holdout"]["cases"]) if holdout_ok(artifacts.get("holdout"), release, revision, rollout_hash) else None,
            "recovery_passed": 20 if recovery_ok(artifacts.get("recovery"), release, revision, rollout_hash) else None,
        },
        "canonical_decision": canonical.get("decision"),
        "decision": ("READY_FOR_OWNER_CONTROLLED_PILOT" if not blockers else
                     "STAGING_ONLY" if blockers == ["separate_founder_and_C_pilot_authorization"] else "SOURCE_ONLY"),
        "pilot_activated": False,
        "blockers": blockers,
        "known_limitations": ["Receipt files are not independently authenticated by this CLI.",
                              "No production or pilot traffic is switched by this CLI."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    for name in ("api", "worker", "schema", "ci", *PROOFS, "golden", "day9_first_run", "holdout", "recovery",
                 "staging", "quality", "model", "artifact_quality", "approval"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        rollout = read_json(args.rollout)
        artifacts = {name: read_json(getattr(args, name)) for name in ("api", "worker", "schema", "ci", *PROOFS,
            "golden", "day9_first_run", "holdout", "recovery", "staging", "quality", "model", "artifact_quality", "approval")}
        result = decide(rollout, sha256(args.rollout), revision=args.source_revision, artifacts=artifacts)
    except (OSError, ValueError) as exc:
        result = {"decision": "SOURCE_ONLY", "canonical_decision": "NO-GO", "pilot_activated": False,
                  "blockers": [str(exc)]}
    if args.day9_first_run and "scorecard" in result:
        result["scorecard"]["day9_first_run_artifact_sha256"] = sha256(args.day9_first_run)
    encoded = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT" else 1


if __name__ == "__main__":
    raise SystemExit(main())