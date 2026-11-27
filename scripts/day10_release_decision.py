"""Fail-closed Day 10 evidence handoff. This tool NEVER activates a cohort.

Evidence is read-only and must be independently produced and reviewed; a JSON
receipt is not proof that a live operation occurred or that its author is D.
"""
from __future__ import annotations

import argparse
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
from scripts.release_contract import pilot_canonical_only_capabilities_disabled  # noqa: E402
from scripts.ruke_pilot_eval import (  # noqa: E402
    BUILD_DIGEST, OPERATED, REQUIRED_DAY9_CI, RUBRIC, canonical_sha256, operated_trace_ok,
    validate_candidate_readbacks,
    _read_json_and_sha256 as read_bounded_json_with_sha,
    immutable_write, reviewer_identity, sha256 as sha256_bounded,
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
    "attempt_started_at", "attempt_finished_at",
)


def read_json_with_sha(path: Path | None) -> tuple[dict | None, str | None]:
    """Bind the release-decision evidence and its receipt to one bounded read."""
    if path is None:
        return None, None
    try:
        value, digest = read_bounded_json_with_sha(path)
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value, digest
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read {path.name}: {type(exc).__name__}") from None


def read_json(path: Path | None) -> dict | None:
    return read_json_with_sha(path)[0]


def sha256(path: Path) -> str:
    """Compatibility helper: reject linked/oversized evidence on read."""
    return sha256_bounded(path)


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
            or not isinstance(output_hash, str) or not DIGEST.fullmatch(output_hash)
            or not ordered_times(row, "attempt_started_at", "attempt_finished_at")):
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
    # The Day 9 export must preserve all three original pseudonymous role
    # claims so an independent Day 10 decision cannot accept an anonymous or
    # self-aliased custodian merely because its access booleans look good.
    custody_identities = [
        reviewer_identity(custody.get(role))
        for role in ("custodian_id", "developer_id", "corpus_author_id")
    ]
    if None in custody_identities or len(set(custody_identities)) != 3:
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
    # D may review if independent; the developer and corpus author may not.
    excluded = set(custody_identities[1:])
    if None in identities or len(identities) != 2 or not identities.isdisjoint(excluded):
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
        reviewer_votes = {}
        review_times = {}
        for rubric in rubrics:
            if (not isinstance(rubric, dict)
                    or set(rubric) != {
                        "reviewer_id", "scores", "source_supported",
                        "output_sha256", "reviewed_at", "evidence_note_sha256",
                    }):
                return False
            reviewer = reviewer_identity(rubric.get("reviewer_id"))
            dimensions = rubric.get("scores")
            supported = rubric.get("source_supported")
            reviewed_at = timestamp(rubric.get("reviewed_at"))
            note_hash = rubric.get("evidence_note_sha256")
            if (reviewer not in identities or reviewer in rubric_totals
                    or not isinstance(dimensions, dict) or set(dimensions) != set(RUBRIC)
                    or any(type(score) is not int or not 0 <= score <= 2 for score in dimensions.values())
                    or type(supported) is not bool
                    or rubric.get("output_sha256") != row["output_sha256"]
                    or reviewed_at is None
                    or reviewed_at <= timestamp(row["attempt_finished_at"])
                    or not isinstance(note_hash, str)
                    or DIGEST.fullmatch(note_hash) is None):
                return False
            rubric_totals[reviewer] = sum(dimensions.values())
            reviewer_votes[reviewer] = (tuple(dimensions[part] for part in RUBRIC), supported)
            review_times[reviewer] = reviewed_at
            if row["accepted"] and (rubric_totals[reviewer] < 7
                                    or min(dimensions.values()) == 0
                                    or not supported):
                return False
        if set(rubric_totals) != identities:
            return False
        if [rubric_totals[reviewer_identity(reviewer)] for reviewer in reviewers] != scores:
            return False
        # Both original blind votes and the final independently adjudicated
        # rubric are necessary. A matching pair must not manufacture a third
        # adjudicator; disagreeing votes require a distinct third identity and
        # a digest of the private rationale retained outside these reports.
        final = row.get("final_rubric")
        if (not isinstance(final, dict)
                or set(final) != {
                    "scores", "source_supported", "adjudicator_id",
                    "evidence_note_sha256", "output_sha256", "adjudicated_at",
                }):
            return False
        final_scores = final["scores"]
        if (not isinstance(final_scores, dict) or set(final_scores) != set(RUBRIC)
                or any(type(score) is not int or not 0 <= score <= 2
                       for score in final_scores.values())
                or type(final["source_supported"]) is not bool
                or final["output_sha256"] != row["output_sha256"]):
            return False
        if len(set(reviewer_votes.values())) > 1:
            adjudicator = reviewer_identity(final["adjudicator_id"])
            digest = final["evidence_note_sha256"]
            adjudicated_at = timestamp(final["adjudicated_at"])
            if (adjudicator is None or adjudicator in identities or adjudicator in excluded
                    or not isinstance(digest, str) or DIGEST.fullmatch(digest) is None
                    or adjudicated_at is None
                    or any(adjudicated_at <= observed for observed in review_times.values())):
                return False
        else:
            unanimous = next(iter(reviewer_votes.values()))
            if (final["adjudicator_id"] is not None
                    or final["evidence_note_sha256"] is not None
                    or final["adjudicated_at"] is not None
                    or (tuple(final_scores[part] for part in RUBRIC),
                        final["source_supported"]) != unanimous):
                return False
        if row["accepted"] and (
                sum(final_scores.values()) < 7
                or min(final_scores.values()) == 0
                or final["source_supported"] is not True):
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

def recovery_ok(
    value: object, release: str, revision: str, digest: str, *,
    manifest_sha256: str | None = None, run_started_at: str | None = None,
) -> bool:
    """Verify precisely the recovery receipt shape emitted by the Day 9 evaluator.

    The separate Day 9 report must still be independently authenticated by
    the operator; matching claimed JSON and hashes does not prove a live fault.
    """
    if not bound(value, release, revision, digest):
        return False
    frozen_start = timestamp(run_started_at) if run_started_at is not None else None
    if run_started_at is not None and frozen_start is None:
        return False
    reported_manifest = value.get("manifest_sha256")
    if (not isinstance(reported_manifest, str)
            or DIGEST.fullmatch(reported_manifest) is None
            or (manifest_sha256 is not None and reported_manifest != manifest_sha256)):
        return False
    rows = value.get("scenarios")
    # Key the scenario ID to its canonical Day 9 sequence, not to any
    # arbitrary unique string that an edited Day 10 report can invent.
    remaining = {
        scenario: (f"day9-scenario-{index:02d}", boundaries)
        for index, (scenario, boundaries) in OPERATED.items()
    }
    if not isinstance(rows, list) or len(rows) != len(remaining):
        return False
    ids, refs = set(), set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or row["id"] in ids):
            return False
        ids.add(row["id"])
        scenario = row.get("scenario")
        if not isinstance(scenario, str) or scenario not in remaining:
            return False
        expected_id, boundaries = remaining.pop(scenario)
        trace_digest = row.get("trace_sha256")
        evidence_ref = row.get("evidence_ref")
        if (row["id"] != expected_id
                or row.get("manifest_sha256") != reported_manifest
                or not isinstance(trace_digest, str)
                or DIGEST.fullmatch(trace_digest) is None
                or evidence_ref != "sha256:" + trace_digest
                or evidence_ref in refs
                or not proof_ok(row, release, revision, digest)
                or not ordered_times(row, "observed_at", "verified_at")
                # Check chronological release provenance independently of
                # the two equal JSON copies that a caller might relabel.
                or (frozen_start is not None
                    and timestamp(row["observed_at"]) < frozen_start)
                or not operated_trace_ok(row, boundaries)):
            return False
        refs.add(evidence_ref)
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
            # A regression rerun or unversioned archival report is not
            # first-run evidence, even when its run_kind is relabeled.
            or first_run.get("run_kind") != "first_run"
            or first_run.get("result_kind") != "operator_submitted_first_run"
            or type(first_run.get("schema_version")) is not int
            or first_run["schema_version"] != 2
            or not nonempty_text(first_run.get("run_id"))):
        return False
    manifest_sha = first_run.get("manifest_sha256")
    run_started_at = timestamp(first_run.get("run_started_at"))
    if (not isinstance(manifest_sha, str) or not DIGEST.fullmatch(manifest_sha)
            or holdout.get("manifest_sha256") != manifest_sha
            or run_started_at is None):
        return False
    # The Day 9 evaluator embeds the original complete Day 10 holdout in
    # its write-once first-run report before exporting the separate file.
    # Matching scorecards alone cannot prove the D custody envelope wasn't
    # replaced after the holdout run.
    if (not isinstance(first_run.get("day10_holdout"), dict)
            or first_run["day10_holdout"] != holdout):
        return False
    custody = holdout.get("custody_receipt")
    custody_verified_at = (
        timestamp(custody.get("verified_at")) if isinstance(custody, dict) else None
    )
    # Custody cannot be established retrospectively at or after the frozen
    # start, even if the two editable JSON copies are changed consistently.
    if custody_verified_at is None or custody_verified_at >= run_started_at:
        return False
    # Day 9's write-once report independently retains the original custody
    # SHA and D's frozen corpus/answer/rubric access-audit digest claims.
    # Cross-bind them here: editing BOTH copies of the exported holdout
    # must not substitute a new receipt for the recorded first-run custody.
    custody_digest = first_run.get("custody_receipt_sha256")
    if (not isinstance(custody_digest, str)
            or DIGEST.fullmatch(custody_digest) is None
            or custody.get("evidence_ref") != "sha256:" + custody_digest):
        return False
    for field in ("custody_access_log_sha256", "custody_exposure_history_sha256"):
        digest = first_run.get(field)
        if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
            return False
    for original, frozen in (
        ("custody_frozen_inputs_sha256", "corpus_sha256"),
        ("custody_frozen_answers_sha256", "answer_key_sha256"),
        ("custody_rubric_sha256", "rubric_sha256"),
    ):
        original_digest, frozen_digest = first_run.get(original), first_run.get(frozen)
        if (not isinstance(original_digest, str)
                or DIGEST.fullmatch(original_digest) is None
                or not isinstance(frozen_digest, str)
                or DIGEST.fullmatch(frozen_digest) is None
                or original_digest != frozen_digest):
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
                or not isinstance(receipt.get("case_id"), str)
                or receipt["case_id"] not in first_by_id
                or receipt["case_id"] in receipts_by_id
                or not bound(receipt, release, revision, rollout_hash)
                or receipt.get("manifest_sha256") != manifest_sha
                or not first_attempt_identity_ok(receipt)
                or receipt["run_id"] in run_ids):
            return False
        if timestamp(receipt["attempt_started_at"]) < run_started_at:
            return False
        receipts_by_id[receipt["case_id"]] = receipt
        run_ids.add(receipt["run_id"])
    if set(receipts_by_id) != set(first_by_id):
        return False
    bound_fields = (
        "id", "workflow", "language", "accepted", "security_passed",
        "source_supported", "deterministic_pass", "reviewer_scores", "reviewer_rubrics",
        "final_rubric", *ATTEMPT_FIELDS,
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


def pilot_scope_sha256(rollout: dict) -> str | None:
    """Digest the exact frozen scope without expanding the canonical rollout schema."""
    cohort = rollout.get("cohort")
    capabilities = rollout.get("capabilities")
    providers = rollout.get("action_providers", [])
    operations = rollout.get("transaction_operations", [])
    if (rollout.get("environment") != "production"
            or not isinstance(cohort, dict) or not nonempty_text(cohort.get("reference"))
            or type(cohort.get("max_users")) is not int or not 5 <= cohort["max_users"] <= 10
            or not isinstance(capabilities, dict) or set(capabilities) != RUNTIME_CAPABILITY_KEYS
            or any(type(value) is not bool for value in capabilities.values())
            or not isinstance(providers, list) or not all(nonempty_text(item) for item in providers)
            or not isinstance(operations, list) or not all(nonempty_text(item) for item in operations)):
        return None
    try:
        return canonical_sha256({
            "environment": rollout["environment"],
            "cohort": {"reference": cohort["reference"], "max_users": cohort["max_users"]},
            "capabilities": capabilities,
            "action_providers": providers,
            "transaction_operations": operations,
        })
    except (TypeError, ValueError):
        return None


def approval_expiry(value: object, *, now: datetime) -> datetime | None:
    """An approval must have an explicit, timezone-aware future expiry."""
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        stamp = stamp.astimezone(timezone.utc)
        return stamp if stamp > now else None
    except (ValueError, OverflowError):
        return None


def pilot_authorization_terms(value: object, rollout: dict, *, now: datetime) -> tuple[str, int, datetime] | None:
    """Validate the exact scope, spend and expiry claim without authenticating signers."""
    if not isinstance(value, dict):
        return None
    scope_digest = pilot_scope_sha256(rollout)
    spend_limit = value.get("max_spend_microusd")
    expiry = approval_expiry(value.get("expires_at"), now=now)
    if (scope_digest is None or value.get("scope_sha256") != scope_digest
            or type(spend_limit) is not int or spend_limit < 0 or expiry is None):
        return None
    return scope_digest, spend_limit, expiry


def final_runtime_matches_frozen_day9(
    first: object, final: object, api: object, worker: object, schema: object,
    model: object, quality: object, capabilities: object,
    release: str, revision: str, rollout_hash: str,
) -> bool:
    """Reconcile separately observed final readbacks with the preserved candidate.

    This verifies exact identity and chronology claims, not their external
    provenance. Independent D/C must authenticate both sets of raw receipts.
    """
    if (not bound(first, release, revision, rollout_hash)
            or first.get("candidate_revision") != revision
            or not proof_ok(final, release, revision, rollout_hash)):
        return False
    generated = timestamp(first.get("generated_at"))
    started = timestamp(first.get("run_started_at"))
    verified = timestamp(final.get("verified_at"))
    reference = final["evidence_ref"]
    if (generated is None or started is None or verified is None
            or generated < started or verified <= generated
            or not reference.startswith("sha256:")
            or DIGEST.fullmatch(reference[7:]) is None):
        return False
    try:
        validate_candidate_readbacks(first, first.get("candidate_readbacks"))
        validate_candidate_readbacks(first, final.get("readbacks"))
        identity = first["candidate_identity"]
        # Existing live planner/quality collectors explicitly use DeepSeek.
        return (
            identity["provider_id"] == "deepseek"
            and identity["api_build_digest"] == api.get("build_digest")
            and identity["worker_build_digest"] == worker.get("build_digest")
            and identity["alembic_revision"] == schema.get("migration_revision")
            and canonical_sha256(identity["runtime_capabilities"]) == canonical_sha256(capabilities)
            and identity["model_id"] == model.get("provider_model") == quality.get("provider_model")
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def separate_pilot_authorization_ok(
    approval: object, rollback: object, ci: object, golden: object,
    release: str, revision: str, digest: str, cohort_limit: object, *,
    rollout: dict, final_readbacks: object,
) -> bool:
    """Check two distinct, dated *claimed* owner decisions, never signer authenticity.

    Each signoff is independently bound to the final release, 5-10 cohort cap,
    operated rollback owner, spending cap, frozen scope, expiry and its own private evidence reference.
    C/D must authenticate the actual signed records outside this CLI.
    """
    if (not proof_ok(approval, release, revision, digest)
            or approval.get("explicit_separate_authorization") is not True
            or not nonempty_text(approval.get("reference"))
            or type(cohort_limit) is not int or not 5 <= cohort_limit <= 10
            or type(approval.get("max_users")) is not int
            or approval["max_users"] != cohort_limit):
        return False

    now = datetime.now(timezone.utc)
    terms = pilot_authorization_terms(approval, rollout, now=now)
    if terms is None:
        return False

    founder_id = reviewer_identity(approval.get("founder"))
    owner_id = reviewer_identity(approval.get("owner_c"))
    if founder_id is None or owner_id is None or founder_id == owner_id:
        return False

    # A string in only the approval file cannot name the operated rollback
    # owner. Its identity must be reconciled against the original rollback
    # receipt; this still cannot prove who performed the real rollback.
    rollback_owner = approval.get("rollback_owner")
    if (reviewer_identity(rollback_owner) is None
            or not isinstance(rollback, dict)
            or rollback.get("rollback_owner") != rollback_owner):
        return False

    # Owner decisions must follow the exact-head CI, final golden and operated
    # rollback verification. Datetimes are compared as UTC instants, not text.
    release_proofs = (ci, golden, rollback, final_readbacks)
    timestamps = [
        timestamp(row.get("verified_at")) if isinstance(row, dict) else None
        for row in release_proofs
    ]
    outer_stamp = timestamp(approval.get("verified_at"))
    if outer_stamp is None or any(stamp is None for stamp in timestamps):
        return False
    minimum_signoff_at = max(timestamps)
    receipt_refs: set[str] = set()
    for role, identity in (("founder", founder_id), ("owner_c", owner_id)):
        receipt = approval.get(role + "_decision")
        if not proof_ok(receipt, release, revision, digest):
            return False
        reference = receipt.get("evidence_ref")
        signoff_at = timestamp(receipt.get("verified_at"))
        if (reviewer_identity(receipt.get("signer_id")) != identity
                or receipt.get("decision") != "approve_controlled_pilot"
                or type(receipt.get("max_users")) is not int
                or receipt["max_users"] != cohort_limit
                or pilot_authorization_terms(receipt, rollout, now=now) != terms
                or receipt.get("rollback_owner") != rollback_owner
                or not isinstance(reference, str)
                or not reference.startswith("sha256:")
                or DIGEST.fullmatch(reference[len("sha256:"):]) is None
                or reference in receipt_refs
                or signoff_at is None
                or signoff_at < minimum_signoff_at
                or signoff_at > outer_stamp):
            return False
        receipt_refs.add(reference)
    return True


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
        and pilot_canonical_only_capabilities_disabled(api.get("canonical_only_capabilities"))
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
         and pilot_canonical_only_capabilities_disabled(worker.get("canonical_only_capabilities"))
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
    final_readbacks = artifacts.get("final_runtime_readbacks")
    need("final_runtime_matches_frozen_day9_identity", final_runtime_matches_frozen_day9(
        first_run, final_readbacks, api, worker, schema, model, artifacts.get("quality"),
        capabilities, release, revision, rollout_hash,
    ))
    need("preserved_day9_first_run", first_run_matches_holdout(
        first_run, artifacts.get("holdout"), release, revision, rollout_hash,
    ))
    need("separate_final_rerun", golden_ok(golden, release, revision, rollout_hash)
         and isinstance(first_run, dict) and first_run.get("run_id") != golden.get("run_id"))
    need("independent_day9_holdout_36_of_40", holdout_ok(artifacts.get("holdout"), release, revision, rollout_hash))
    recovery = artifacts.get("recovery")
    # The Day 9 first-run report embeds this exact recovery artifact before
    # exporting the separate Day 10 file. Require that same original evidence,
    # not a replacement independently prepared after the qualification run.
    recovery_qualified = (
        isinstance(first_run, dict)
        and timestamp(first_run.get("run_started_at")) is not None
        and isinstance(first_run.get("day10_recovery"), dict)
        and first_run["day10_recovery"] == recovery
        and recovery_ok(
            recovery, release, revision, rollout_hash,
            manifest_sha256=first_run.get("manifest_sha256", ""),
            run_started_at=first_run["run_started_at"],
        )
    )
    need("twenty_operated_recovery_scenarios", recovery_qualified)
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
    # A shared summary receipt cannot substitute for two independent,
    # dated decisions; release authority still requires human authentication.
    approval = artifacts.get("approval")
    approved = separate_pilot_authorization_ok(
        approval, artifacts.get("rollback"), ci, golden,
        release, revision, rollout_hash, cohort_limit,
        rollout=rollout, final_readbacks=final_readbacks,
    )
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
            "recovery_passed": 20 if recovery_qualified else None,
        },
        "canonical_decision": canonical.get("decision"),
        "decision": ("READY_FOR_OWNER_CONTROLLED_PILOT" if not blockers else
                     "STAGING_ONLY" if blockers == ["separate_founder_and_C_pilot_authorization"] else "SOURCE_ONLY"),
        "pilot_activated": False,
        "pilot_authorization_claim": ({
            "scope_sha256": approval["scope_sha256"],
            "max_spend_microusd": approval["max_spend_microusd"],
            "expires_at": approval["expires_at"],
        } if approved else None),
        "blockers": blockers,
        "known_limitations": ["Receipt files are not independently authenticated by this CLI.",
                              "No production or pilot traffic is switched by this CLI."],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    for name in ("api", "worker", "schema", "ci", *PROOFS, "golden", "day9_first_run", "final_runtime_readbacks", "holdout", "recovery",
                 "staging", "quality", "model", "artifact_quality", "approval"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    day9_digest = None
    final_readbacks_digest = None
    try:
        rollout, rollout_digest = read_json_with_sha(args.rollout)
        artifacts = {}
        for name in ("api", "worker", "schema", "ci", *PROOFS, "golden",
                     "day9_first_run", "final_runtime_readbacks", "holdout", "recovery", "staging", "quality",
                     "model", "artifact_quality", "approval"):
            value, digest = read_json_with_sha(getattr(args, name))
            artifacts[name] = value
            if name == "day9_first_run":
                day9_digest = digest
            elif name == "final_runtime_readbacks":
                final_readbacks_digest = digest
        result = decide(rollout, rollout_digest, revision=args.source_revision, artifacts=artifacts)
    except (OSError, ValueError) as exc:
        result = {"decision": "SOURCE_ONLY", "canonical_decision": "NO-GO", "pilot_activated": False,
                  "blockers": [str(exc)]}
    if day9_digest is not None and "scorecard" in result:
        result["scorecard"]["day9_first_run_artifact_sha256"] = day9_digest
    if final_readbacks_digest is not None and "scorecard" in result:
        result["scorecard"]["final_runtime_readbacks_artifact_sha256"] = final_readbacks_digest
    encoded = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        try:
            # A second decision needs a new lineage/path, never a rewrite.
            immutable_write(args.output, result)
        except (OSError, ValueError) as exc:
            print(json.dumps({
                "decision": "SOURCE_ONLY", "canonical_decision": "NO-GO",
                "pilot_activated": False,
                "blockers": ["decision_artifact_write_failed:" + type(exc).__name__],
            }), file=sys.stderr)
            return 2
    print(encoded, end="")
    return 0 if result["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
