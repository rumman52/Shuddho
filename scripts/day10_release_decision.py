"""Fail-closed Day 10 evidence handoff. This tool NEVER activates a cohort.

Evidence is read-only and must be independently produced and reviewed; a JSON
receipt is not proof that a live operation occurred or that its author is D.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    # Support the documented `python scripts/day10_release_decision.py` entrypoint.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cohort_release_gate import evaluate_release  # noqa: E402
from scripts.ruke_pilot_eval import (  # noqa: E402
    BUILD_DIGEST, OPERATED, REQUIRED_DAY9_CI, RUBRIC, operated_trace_ok,
    read_json as read_bounded_json, reviewer_identity,
)
from scripts.staging_release_freeze import (  # noqa: E402
    EXPECTED_ROLLBACK,
    PA10_REQUIRED_FALSE,
    PA10_REQUIRED_TRUE,
    RUNTIME_CAPABILITY_KEYS,
    api_runtime_capabilities_match_rollout,
)

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
CELLS = {(workflow, language) for workflow in ("research_brief", "project_report_email") for language in ("bn", "en")}
PROOFS = ("rollback", "cancellation", "paused_schedule", "owner_isolation")
ATTEMPT_FIELDS = (
    "run_id", "output_sha256", "attempt_status", "evidence_kind",
    "output_present", "failure_code", "failure_trace_sha256",
)


def read_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        value = read_bounded_json(path)
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read {path.name}: {type(exc).__name__}") from None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        stamp = stamp.astimezone(timezone.utc)
        return stamp if stamp <= datetime.now(timezone.utc) else None
    except (ValueError, OverflowError):
        return None


def time_ok(value: object) -> bool:
    return timestamp(value) is not None


def ordered_times(row: dict, *keys: str, strict_after: frozenset[int] = frozenset()) -> bool:
    stamps = [timestamp(row.get(key)) for key in keys]
    if any(stamp is None for stamp in stamps):
        return False
    for index, (left, right) in enumerate(zip(stamps, stamps[1:])):
        if index in strict_after:
            if left >= right:
                return False
        elif left > right:
            return False
    return True


def nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def bound(row: object, release: str, revision: str, digest: str) -> bool:
    return (isinstance(row, dict) and row.get("release_id") == release
            and row.get("source_revision") == revision
            and row.get("rollout_manifest_sha256") == digest)


def proof_ok(row: object, release: str, revision: str, digest: str) -> bool:
    return (bound(row, release, revision, digest) and row.get("status") == "passed"
            and isinstance(row.get("evidence_ref"), str) and bool(row["evidence_ref"].strip())
            and time_ok(row.get("verified_at")))


def first_attempt_identity_ok(row: object) -> bool:
    """Validate the claim's type and lineage, not the private source bytes."""
    if not isinstance(row, dict):
        return False
    run_id = row.get("run_id")
    output_hash = row.get("output_sha256")
    if (not isinstance(run_id, str) or not run_id.strip()
            or run_id != run_id.strip() or len(run_id) > 128
            or not isinstance(output_hash, str) or not DIGEST.fullmatch(output_hash)):
        return False
    status = row.get("attempt_status")
    if status == "succeeded":
        return (row.get("evidence_kind") == "draft_output"
                and row.get("output_present") is True
                and row.get("failure_code") is None
                and row.get("failure_trace_sha256") is None)
    if status in ("failed", "timed_out"):
        code = row.get("failure_code")
        trace = row.get("failure_trace_sha256")
        return (row.get("evidence_kind") == "failure_record"
                and row.get("output_present") is False
                and isinstance(code, str)
                and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) is not None
                and isinstance(trace, str) and DIGEST.fullmatch(trace) is not None)
    return False


def holdout_ok(value: object, release: str, revision: str, digest: str) -> bool:
    if not bound(value, release, revision, digest) or value.get("custody_established") is not True:
        return False
    custody = value.get("custody_receipt")
    if (not proof_ok(custody, release, revision, digest)
            or custody.get("independent_d_controls_access") is not True
            or custody.get("developer_negative_read_denied") is not True):
        return False
    if (value.get("mode") != "independent_human_holdout"
            or value.get("generation_identity_verified") is not True
            or not isinstance(value.get("generation_identity_receipt_sha256"), str)
            or not DIGEST.fullmatch(value["generation_identity_receipt_sha256"])):
        return False
    reviewers = value.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) != 2:
        return False
    identities = {reviewer_identity(reviewer) for reviewer in reviewers}
    if None in identities or len(identities) != 2:
        return False
    rows = value.get("cases")
    if not isinstance(rows, list) or len(rows) != 40:
        return False
    ids, run_ids, counts, accepted = set(), set(), Counter(), Counter()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            return False
        ids.add(row["id"])
        if not first_attempt_identity_ok(row) or row["run_id"] in run_ids:
            return False
        run_ids.add(row["run_id"])
        if (row["attempt_status"] != "succeeded"
                and (row.get("accepted") is not False or row.get("deterministic_pass") is not False)):
            return False
        cell = (row.get("workflow"), row.get("language"))
        if cell not in CELLS or type(row.get("accepted")) is not bool:
            return False
        # Security is an absolute NO-GO across all 40 cases, even when an
        # unsafe case is already rejected on human-acceptance quality.
        # Missing, false, or non-boolean results are not positive evidence.
        if row.get("security_passed") is not True:
            return False
        # Preserve both original 4-dimension rubrics. Rejected cases may score zero;
        # every accepted case requires both reviewers >=7/8 with no zero dimension.
        scores = row.get("reviewer_scores")
        rubrics = row.get("reviewer_rubrics")
        if (not isinstance(scores, list) or len(scores) != 2
                or any(type(score) is not int or not 0 <= score <= 8 for score in scores)
                or not isinstance(rubrics, list) or len(rubrics) != 2):
            return False
        rubric_totals = {}
        for rubric in rubrics:
            if not isinstance(rubric, dict):
                return False
            reviewer = reviewer_identity(rubric.get("reviewer_id"))
            dimensions = rubric.get("scores")
            if (reviewer not in identities or reviewer in rubric_totals
                    or not isinstance(dimensions, dict) or set(dimensions) != set(RUBRIC)
                    or any(type(score) is not int or not 0 <= score <= 2 for score in dimensions.values())):
                return False
            rubric_totals[reviewer] = sum(dimensions.values())
            if row["accepted"] and (rubric_totals[reviewer] < 7 or min(dimensions.values()) == 0):
                return False
        if set(rubric_totals) != identities:
            return False
        if [rubric_totals[reviewer_identity(reviewer)] for reviewer in reviewers] != scores:
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
        flags = value.get("capability_flags_after_rollback")
        evidence_refs = (
            "api_readback_evidence_ref",
            "worker_readback_evidence_ref",
            "worker_stop_evidence_ref",
            "safe_state_procedure_ref",
            "safe_state_deployment_reference",
            "safe_state_evidence_ref",
            "restored_data_probe_ref",
        )
        return (
            isinstance(switches, list)
            and all(isinstance(item, str) for item in switches)
            and len(switches) == len(set(switches))
            and set(EXPECTED_ROLLBACK.values()).issubset(set(switches))
            and isinstance(flags, dict)
            and set(flags) == RUNTIME_CAPABILITY_KEYS
            and all(type(enabled) is bool for enabled in flags.values())
            and all(
                flags[key] is False
                for key in PA10_REQUIRED_TRUE | PA10_REQUIRED_FALSE
            )
            and all(value.get(key) is True for key in (
                "new_admissions_stopped",
                "api_reload_verified",
                "worker_reload_verified",
                "outstanding_work_fenced",
                "ledger_consistency_verified",
                "worker_stop_observed",
                "restoration_verified",
                "restored_data_retrievable",
            ))
            and all(nonempty_text(value.get(key)) for key in evidence_refs)
            and isinstance(value.get("safe_state_source_revision"), str)
            and bool(SHA.fullmatch(value["safe_state_source_revision"]))
            and ordered_times(
                value,
                "rollback_started_at",
                "worker_stopped_at",
                "safe_state_restored_at",
                "verified_at",
                strict_after=frozenset({0, 1}),
            )
        )
    if kind == "cancellation":
        return (
            nonempty_text(value.get("cancelled_run_id"))
            and value.get("inference_active_at_cancel") is True
            and value.get("terminal_state") == "cancelled"
            and value.get("late_result_observed") is True
            and value.get("terminal_state_after_late_result") == "cancelled"
            and type(value.get("late_side_effects")) is int
            and value["late_side_effects"] == 0
            and ordered_times(
                value,
                "inference_started_at",
                "cancelled_at",
                "late_result_observed_at",
                "verified_at",
                strict_after=frozenset({0, 1}),
            )
        )
    if kind == "paused_schedule":
        return (
            nonempty_text(value.get("schedule_id"))
            and type(value.get("executions_while_paused")) is int
            and value["executions_while_paused"] == 0
            and type(value.get("admitted_executions_while_paused")) is int
            and value["admitted_executions_while_paused"] == 0
            and ordered_times(
                value,
                "paused_at",
                "next_due_at",
                "observed_after_due_at",
                "verified_at",
                strict_after=frozenset({1}),
            )
        )
    if kind == "owner_isolation":
        denied = value.get("denied_resource_types")
        required_resources = {"documents", "memory", "artifacts", "activity"}
        return (
            nonempty_text(value.get("owner_a_ref"))
            and nonempty_text(value.get("owner_b_ref"))
            and value["owner_a_ref"] != value["owner_b_ref"]
            and value.get("synthetic_owners_verified") is True
            and value.get("cross_owner_denied") is True
            and value.get("both_directions_verified") is True
            and isinstance(denied, list)
            and all(isinstance(item, str) for item in denied)
            and len(denied) == len(set(denied))
            and required_resources.issubset(set(denied))
        )
    return False

def recovery_ok(value: object, release: str, revision: str, digest: str) -> bool:
    if not bound(value, release, revision, digest):
        return False
    rows = value.get("scenarios")
    remaining = dict(OPERATED.values())
    if not isinstance(rows, list) or len(rows) != len(remaining):
        return False
    ids, refs = set(), set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            return False
        ids.add(row["id"])
        if not proof_ok(row, release, revision, digest) or row["evidence_ref"] in refs:
            return False
        refs.add(row["evidence_ref"])
        scenario = row.get("scenario")
        if not isinstance(scenario, str) or scenario not in remaining:
            return False
        if not operated_trace_ok(row, remaining[scenario]) or not time_ok(row.get("observed_at")):
            return False
        del remaining[scenario]
    return not remaining


def golden_ok(value: object, release: str, revision: str, digest: str) -> bool:
    return (proof_ok(value, release, revision, digest)
            and value.get("scenario") == "integrated_multi_turn"
            and isinstance(value.get("run_id"), str) and bool(value["run_id"].strip())
            and type(value.get("turns")) is int and value["turns"] >= 2
            and value.get("cancellation_checked") is True
            and value.get("owner_isolation_checked") is True)




def first_run_matches_holdout(
    first_run: object, holdout: object, release: str, revision: str, rollout_hash: str,
) -> bool:
    """Bind preserved first-run scores to the SAME release, manifest, and 40 cases.

    The Day 9 evaluator emits two artifacts from one input: a full first-run
    report and its holdout receipt. The release gate must reject a historical
    or re-labeled report even when both artifacts separately look well-formed.
    A pre-fix report remains archival evidence, not qualifying evidence for
    the newly fixed release. Authentication of the original bytes remains
    an independent operator responsibility.
    """
    if (not bound(first_run, release, revision, rollout_hash)
            or not isinstance(holdout, dict)
            or first_run.get("run_kind") != "first_run"
            or not nonempty_text(first_run.get("run_id"))):
        return False
    manifest_sha = first_run.get("manifest_sha256")
    if (not isinstance(manifest_sha, str) or not DIGEST.fullmatch(manifest_sha)
            or holdout.get("manifest_sha256") != manifest_sha):
        return False
    scores = first_run.get("scores")
    if not isinstance(scores, dict) or type(scores.get("total")) is not int or scores["total"] != 40:
        return False
    originals = scores.get("cases")
    verified = holdout.get("cases")
    if not isinstance(originals, list) or not isinstance(verified, list) or len(originals) != 40 or len(verified) != 40:
        return False
    first_by_id: dict[str, dict] = {}
    holdout_by_id: dict[str, dict] = {}
    for rows, indexed in ((originals, first_by_id), (verified, holdout_by_id)):
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or not row["id"] or row["id"] in indexed
                    or (row.get("workflow"), row.get("language")) not in CELLS):
                return False
            indexed[row["id"]] = row
    if set(first_by_id) != set(holdout_by_id):
        return False
    # Day 9's original candidate ledger is the identity authority for every
    # scored attempt. Both Day 10 score and holdout artifacts must agree with it;
    # matching two editable scorecards alone cannot establish first-run lineage.
    receipts = first_run.get("case_run_receipts")
    candidate_digest = first_run.get("candidate_outputs_sha256")
    if (not isinstance(receipts, list) or len(receipts) != 40
            or not isinstance(candidate_digest, str) or not DIGEST.fullmatch(candidate_digest)):
        return False
    receipts_by_id: dict[str, dict] = {}
    run_ids: set[str] = set()
    for receipt in receipts:
        if (not isinstance(receipt, dict)
                or receipt.get("case_id") not in first_by_id
                or receipt["case_id"] in receipts_by_id
                or not bound(receipt, release, revision, rollout_hash)
                or receipt.get("manifest_sha256") != manifest_sha
                or not first_attempt_identity_ok(receipt)
                or receipt["run_id"] in run_ids):
            return False
        if (receipt["attempt_status"] != "succeeded"
                and not ordered_times(receipt, "attempt_started_at", "attempt_finished_at")):
            return False
        receipts_by_id[receipt["case_id"]] = receipt
        run_ids.add(receipt["run_id"])
    if set(receipts_by_id) != set(first_by_id):
        return False
    bound_fields = (
        "id", "workflow", "language", "accepted", "security_passed",
        "source_supported", "deterministic_pass", "reviewer_scores", "reviewer_rubrics",
        *ATTEMPT_FIELDS,
    )
    by_cell: Counter[str] = Counter()
    accepted: Counter[str] = Counter()
    for case_id, original in first_by_id.items():
        if any(original.get(field) != holdout_by_id[case_id].get(field) for field in bound_fields):
            return False
        if (not first_attempt_identity_ok(original)
                or any(original.get(field) != receipts_by_id[case_id].get(field)
                       for field in ATTEMPT_FIELDS)):
            return False
        if any(type(original.get(field)) is not bool for field in (
                "accepted", "security_passed", "source_supported", "deterministic_pass")):
            return False
        if original["accepted"] and not all(original[key] for key in (
                "security_passed", "source_supported", "deterministic_pass")):
            return False
        if original["attempt_status"] != "succeeded" and (
                original["accepted"] or original["deterministic_pass"]):
            return False
        cell = original["workflow"] + "/" + original["language"]
        by_cell[cell] += 1
        accepted[cell] += int(original["accepted"])
    expected_cells = {
        workflow + "/" + language: {
            "total": by_cell[workflow + "/" + language],
            "accepted": accepted[workflow + "/" + language],
        }
        for workflow, language in CELLS
    }
    expected_accepted = sum(accepted.values())
    return (all(by_cell[cell] == 10 for cell in expected_cells)
            and type(scores.get("accepted")) is int
            and scores["accepted"] == expected_accepted
            and scores.get("by_cell") == expected_cells)


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
        and isinstance(api.get("build_digest"), str)
        and BUILD_DIGEST.fullmatch(api["build_digest"]) is not None
        and api.get("environment") == rollout.get("environment")
        # Check all 43 frozen authority flags and the additional API-only
        # UI-derived field. Any unreviewed keys or unexpected drift fail closed.
        and api_runtime_capabilities_match_rollout(api.get("capabilities"), capabilities)
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
         and isinstance(worker.get("deployment_reference"), str) and bool(worker["deployment_reference"].strip())
         and worker.get("schema_version") == 2
         and worker.get("environment") == rollout.get("environment")
         and isinstance(worker.get("build_digest"), str)
         and BUILD_DIGEST.fullmatch(worker["build_digest"]) is not None
         and isinstance(worker.get("capabilities"), dict)
         and set(worker["capabilities"]) == RUNTIME_CAPABILITY_KEYS
         and all(type(enabled) is bool for enabled in worker["capabilities"].values())
         and worker["capabilities"] == capabilities
         and worker.get("action_providers") == rollout.get("action_providers", []))
    ci = artifacts.get("ci")
    need("final_head_ci", bound(ci, release, revision, rollout_hash)
         and ci.get("status") == "passed"
         and isinstance(ci.get("workflow_run_url"), str) and ci["workflow_run_url"].startswith("https://github.com/")
         and isinstance(ci.get("required_checks"), dict)
         and all(ci["required_checks"].get(key) == "success" for key in REQUIRED_DAY9_CI))
    for key in PROOFS:
        need("operated_" + key, operated_proof_ok(key, artifacts.get(key), release, revision, rollout_hash))
    golden = artifacts.get("golden")
    need("final_sha_integrated_golden", golden_ok(golden, release, revision, rollout_hash))
    model = artifacts.get("model")
    need("final_golden_provider_matches_live_gates", golden_ok(golden, release, revision, rollout_hash)
         and isinstance(model, dict) and isinstance(model.get("provider_model"), str)
         and golden.get("provider_model") == model["provider_model"])
    first_run = artifacts.get("day9_first_run")
    need("preserved_day9_first_run", first_run_matches_holdout(
        first_run, artifacts.get("holdout"), release, revision, rollout_hash,
    ))
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
    approvers = (
        {reviewer_identity(approval.get(role)) for role in ("founder", "owner_c")}
        if isinstance(approval, dict) else set()
    )
    approved = (bound(approval, release, revision, rollout_hash)
                and approval.get("explicit_separate_authorization") is True
                and isinstance(approval.get("reference"), str) and bool(approval["reference"].strip())
                and len(approvers) == 2 and None not in approvers
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
