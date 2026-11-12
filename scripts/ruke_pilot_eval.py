"""Day 9 operator-controlled pilot qualification. No inference, sending or deployment.

This module validates evidence; it cannot prove human independence or run a
staging fault by reading an operator-authored JSON file. The canonical cohort
release gate remains authoritative and is never bypassed by this report.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

from scripts.pilot_workflow_eval import load_suite

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests/fixtures/ruke_pilot_tasks.jsonl"
MATRIX = {(workflow, language): 10 for workflow in ("research_brief", "project_report_email") for language in ("bn", "en")}
RUBRIC = ("factual_source_fidelity", "constraint_compliance", "completeness_usefulness", "language_quality")
MAX_BYTES = 4_000_000
SHA = re.compile(r"^[0-9a-f]{64}$")
REV = re.compile(r"^[0-9a-f]{40}$")
# These are requirements, not simulated success records.
OPERATED = {
    1: ("private_upload_retrieval", ("postgres", "object_storage")),
    2: ("foreign_access_denial", ("postgres", "object_storage")),
    3: ("source_removed_mid_generation", ("postgres", "temporal", "object_storage")),
    4: ("pdf_prompt_injection", ("object_storage",)),
    5: ("prior_conversation_choice", ("postgres",)),
    6: ("stale_conversation_brief_conflict", ("postgres",)),
    7: ("identical_replay_one_outbox", ("postgres", "temporal")),
    8: ("changed_brief_source_conflict", ("postgres", "temporal")),
    9: ("unselected_memory_absent", ("postgres",)),
    10: ("corrected_expired_foreign_memory_pin", ("postgres",)),
    11: ("worker_interruption_reconcile", ("postgres", "temporal")),
    12: ("cancel_during_inference", ("postgres", "temporal")),
    13: ("steer_during_inference", ("postgres", "temporal")),
    14: ("browser_reconnect_persisted_run", ("postgres", "temporal")),
    15: ("provider_timeout_rate_limit_missing_usage", ("postgres", "temporal")),
    16: ("missing_unreadable_object", ("postgres", "object_storage")),
    17: ("duplicate_occurrence_one_run", ("postgres", "temporal")),
    18: ("pause_expiry_deleted_source", ("postgres", "temporal")),
    19: ("quiet_hours_missed_occurrence", ("postgres", "temporal")),
    20: ("rollback_database_restore", ("postgres", "temporal", "object_storage")),
}


class EvidenceError(ValueError):
    """Malformed, missing, or non-qualifying evaluation input."""


def sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise EvidenceError("missing, linked, or oversized evidence file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs_unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceError("duplicate JSON key")
        value[key] = item
    return value


def read_json(path: Path):
    sha256(path)
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs_unique)


def read_jsonl(path: Path) -> list[dict]:
    sha256(path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line, object_pairs_hook=pairs_unique)
            if not isinstance(obj, dict):
                raise EvidenceError("JSONL rows must be objects")
            rows.append(obj)
    return rows


def registry_cases(path: Path = REGISTRY) -> list[dict]:
    rows = read_jsonl(path)
    if len(rows) != 40 or Counter((r.get("workflow"), r.get("language")) for r in rows) != MATRIX:
        raise EvidenceError("development registry must contain 40 tasks, 10 per cell")
    suite = load_suite()
    expected = {c["id"]: c for c in suite["cases"] if c["split"] == "development"}
    if len({r.get("case_id") for r in rows}) != 40 or set(r["case_id"] for r in rows) != set(expected):
        raise EvidenceError("development registry ID mismatch")
    for row in rows:
        case = expected[row["case_id"]]
        if set(row) != {"case_id", "split", "workflow", "language", "source_id",
                        "citation_id", "source_revision", "source_sha256",
                        "instruction", "max_output_bytes"}:
            raise EvidenceError("development task registry schema drift")
        if (row["instruction"] != case["instruction"]
                or row["source_sha256"] != case["_source"]["sha256"]
                or row["max_output_bytes"] != case["max_output_bytes"]):
            raise EvidenceError("development prompt/source binding changed")
        for field in ("workflow", "language", "source_id", "citation_id"):
            if row.get(field) != case[field]:
                raise EvidenceError("development registry source binding mismatch")
        if row.get("source_revision") != suite["manifest"]["source_revision"]:
            raise EvidenceError("development source revision mismatch")
        if row.get("split") != "development" or "expected_facts" in row:
            raise EvidenceError("development registry cannot distribute holdout or answer keys")
    return rows


def outside_repo(path: Path, repo_root: Path = ROOT) -> None:
    """Prevent accidentally writing independent evidence into developer checkout."""
    resolved = path.resolve(strict=False)
    if path.is_symlink() or resolved.is_relative_to(repo_root.resolve()):
        raise EvidenceError("heldout/evidence must be a separate, non-symlinked external file")
    # Parent symlinks can otherwise redirect an apparently external path.
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise EvidenceError("symlinked custody path is prohibited")


def external_heldout(path: Path, *, corpus_sha256: str, repo_root: Path = ROOT) -> list[dict]:
    """Validate external corpus structure, NOT custody/independence."""
    outside_repo(path, repo_root)
    if sha256(path) != corpus_sha256 or not SHA.fullmatch(corpus_sha256):
        raise EvidenceError("external heldout hash mismatch")
    rows = read_jsonl(path)
    if len(rows) != 40 or Counter((r.get("workflow"), r.get("language")) for r in rows) != MATRIX:
        raise EvidenceError("heldout matrix requires 10 per workflow/language")
    ids = [r.get("case_id") for r in rows]
    if len(set(ids)) != 40 or not all(isinstance(x, str) and x for x in ids):
        raise EvidenceError("heldout IDs must be distinct")
    if any("expected_facts" in r or "reference_outputs" in r for r in rows):
        raise EvidenceError("generation-facing heldout must not expose answer keys")
    for row in rows:
        if (not isinstance(row.get("instruction"), str) or not row["instruction"].strip()
                or len(row["instruction"]) > 4000
                or not isinstance(row.get("source_id"), str) or not row["source_id"].strip()
                or not isinstance(row.get("citation_id"), str) or not row["citation_id"].strip()
                or not SHA.fullmatch(row.get("source_sha256", ""))
                or type(row.get("max_output_bytes")) is not int
                or not 1 <= row["max_output_bytes"] <= 24000):
            raise EvidenceError("heldout task missing bounded instruction/source contract")
    return rows


def validate_manifest(manifest: dict, corpus: Path) -> list[dict]:
    """Manifest is a recorded identity, never proof of independent custody."""
    if not isinstance(manifest, dict):
        raise EvidenceError("run manifest must be an object")
    if manifest.get("schema_version") != 1 or manifest.get("split") != "holdout":
        raise EvidenceError("invalid run manifest")
    if not REV.fullmatch(manifest.get("candidate_revision", "")):
        raise EvidenceError("unbound candidate revision")
    if not SHA.fullmatch(manifest.get("corpus_sha256", "")):
        raise EvidenceError("missing frozen corpus digest")
    for key in ("candidate_product_version", "candidate_model", "prompt_version", "tool_version",
                "source_set_sha256", "run_started_at"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise EvidenceError("missing frozen generation identity: " + key)
    if not SHA.fullmatch(manifest["source_set_sha256"]):
        raise EvidenceError("invalid source-set digest")
    limit = manifest.get("time_limit_seconds")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 3600:
        raise EvidenceError("invalid comparable time limit")
    return external_heldout(corpus, corpus_sha256=manifest["corpus_sha256"])


def _unique_rows(rows: list[dict], key: str, allowed: set[str], count: int) -> dict:
    if not isinstance(rows, list) or len(rows) != count:
        raise EvidenceError("wrong number of " + key + " rows")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or row.get(key) not in allowed or row[key] in indexed:
            raise EvidenceError("missing, duplicate or unknown " + key)
        indexed[row[key]] = row
    return indexed


def score_reviews(cases: list[dict], reviews: list[dict], adjudications: list[dict], deterministic: list[dict]) -> dict:
    ids = {c["case_id"] for c in cases}
    checks = _unique_rows(deterministic, "case_id", ids, 40)
    for case_id, check in checks.items():
        if type(check.get("passed")) is not bool or type(check.get("security_passed")) is not bool:
            raise EvidenceError("deterministic/security result missing for " + case_id)
        if not SHA.fullmatch(check.get("output_sha256", "")):
            raise EvidenceError("output identity missing for " + case_id)
    if len(reviews) != 80:
        raise EvidenceError("exactly two independent scores per task required")
    by_id = defaultdict(dict)
    for row in reviews:
        if not isinstance(row, dict) or row.get("case_id") not in ids:
            raise EvidenceError("unknown reviewer task")
        reviewer = row.get("reviewer_id")
        if not isinstance(reviewer, str) or not reviewer.strip() or reviewer in by_id[row["case_id"]]:
            raise EvidenceError("reviewers must be independent per task")
        scores = row.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(RUBRIC) or any(type(scores[d]) is not int or scores[d] not in (0, 1, 2) for d in RUBRIC):
            raise EvidenceError("reviewer scores must be four integers in 0..2")
        if type(row.get("source_supported")) is not bool or not isinstance(row.get("evidence_note"), str) or not row["evidence_note"].strip():
            raise EvidenceError("source evidence and written reviewer rationale required")
        by_id[row["case_id"]][reviewer] = row
    if any(len(v) != 2 for v in by_id.values()) or len(by_id) != 40:
        raise EvidenceError("two independent reviewers per task required")
    reviewer_set = {r for scores in by_id.values() for r in scores}
    if len(reviewer_set) != 2:
        raise EvidenceError("two fixed independent reviewers required throughout")
    pending = {cid for cid, r in by_id.items() if len({(tuple(x["scores"][d] for d in RUBRIC), x["source_supported"]) for x in r.values()}) > 1}
    resolved = _unique_rows(adjudications, "case_id", pending, len(pending))
    for cid, row in resolved.items():
        if row.get("adjudicator_id") in reviewer_set or not isinstance(row.get("evidence_note"), str) or not row["evidence_note"].strip():
            raise EvidenceError("separate adjudicator and rationale required")
        if type(row.get("source_supported")) is not bool or not isinstance(row.get("scores"), dict) or set(row["scores"]) != set(RUBRIC):
            raise EvidenceError("bad adjudication")
        if any(type(row["scores"][d]) is not int or row["scores"][d] not in (0, 1, 2) for d in RUBRIC):
            raise EvidenceError("bad adjudication scores")
    per_cell = defaultdict(lambda: {"total": 0, "accepted": 0})
    results = []
    for case in cases:
        cid = case["case_id"]
        chosen = resolved.get(cid) or next(iter(by_id[cid].values()))
        ratings = chosen["scores"]
        deterministic_ok = checks[cid]["passed"] and checks[cid]["security_passed"]
        accepted = deterministic_ok and chosen["source_supported"] and sum(ratings.values()) >= 7 and min(ratings.values()) > 0
        cell = case["workflow"] + "/" + case["language"]
        per_cell[cell]["total"] += 1
        per_cell[cell]["accepted"] += int(accepted)
        results.append({"case_id": cid, "cell": cell, "score": sum(ratings.values()), "accepted": accepted,
                        "deterministic_pass": deterministic_ok, "source_supported": chosen["source_supported"]})
    accepted = sum(r["accepted"] for r in results)
    gate = accepted >= 36 and all(x["total"] == 10 and x["accepted"] >= 9 for x in per_cell.values())
    return {"accepted": accepted, "total": 40, "by_cell": dict(sorted(per_cell.items())),
            "outcome_gate_pass": gate, "disagreements_adjudicated": len(pending),
            "reviewer_count": len(reviewer_set), "results": results}


def verify_operations(rows: list[dict], candidate_revision: str) -> dict:
    ids = {str(i) for i in OPERATED}
    normalized = [{**r, "row": str(r.get("row"))} for r in rows]
    indexed = _unique_rows(normalized, "row", ids, 20)
    failed = []
    for raw_id, row in indexed.items():
        index = int(raw_id)
        name, needed = OPERATED[index]
        if row.get("scenario") != name or row.get("candidate_revision") != candidate_revision:
            raise EvidenceError("operated scenario/revision mismatch")
        if row.get("status") != "pass" or row.get("execution") != "operated":
            failed.append(index)
        if row.get("unauthorized_access") is not False or row.get("unauthorized_mutation") is not False:
            failed.append(index)
        if not SHA.fullmatch(row.get("trace_sha256", "")) or not isinstance(row.get("observed_at"), str) or not row["observed_at"].strip():
            failed.append(index)
        boundaries = row.get("boundaries")
        if not isinstance(boundaries, dict):
            failed.append(index)
            continue
        for target in needed:
            evidence = boundaries.get(target)
            if not isinstance(evidence, dict) or evidence.get("mode") != "real" or not isinstance(evidence.get("instance"), str) or not evidence["instance"].strip() or not SHA.fullmatch(evidence.get("trace_sha256", "")):
                failed.append(index)
    failed = sorted(set(failed))
    return {"total": 20, "passed": 20 - len(failed), "failed_rows": failed, "fault_gate_pass": not failed,
            "evidence_level": "operator_submitted_operated_traces_not_independently_attested"}


def position_map(case_id: str, corpus_sha256: str) -> dict:
    bit = int(hashlib.sha256((corpus_sha256 + ":" + case_id).encode()).hexdigest(), 16) & 1
    return {"AB": ("candidate", "competitor") if bit == 0 else ("competitor", "candidate"),
            "BA": ("competitor", "candidate") if bit == 0 else ("candidate", "competitor")}


def compare(cases: list[dict], manifest: dict, competitor: dict | None, rows: list[dict] | None) -> dict:
    if competitor is None or rows is None:
        return {"complete": False, "comparison_gap": "competitor access or blinded judgment evidence missing", "wins": None, "ties": None, "losses": None}
    for field in ("product", "product_version", "model", "run_started_at"):
        if not isinstance(competitor.get(field), str) or not competitor[field].strip():
            raise EvidenceError("competitor identity incomplete: " + field)
    if competitor.get("source_set_sha256") != manifest["source_set_sha256"] or competitor.get("time_limit_seconds") != manifest["time_limit_seconds"]:
        raise EvidenceError("competitor sources/time ceiling not comparable")
    if len(rows) != 160:
        raise EvidenceError("two reviewers and both swapped positions required for 40 tasks")
    ids = {c["case_id"] for c in cases}
    judgments = defaultdict(dict)
    for r in rows:
        cid, reviewer, order = r.get("case_id"), r.get("reviewer_id"), r.get("position")
        if cid not in ids or not isinstance(reviewer, str) or not reviewer.strip() or order not in ("AB", "BA"):
            raise EvidenceError("invalid blinded judgment identity")
        if r.get("preference") not in ("A", "B", "tie") or not isinstance(r.get("evidence_note"), str) or not r["evidence_note"].strip():
            raise EvidenceError("blinded judgment needs preference and evidence")
        key = (reviewer, order)
        if key in judgments[cid]:
            raise EvidenceError("duplicate blinded judgment")
        judgments[cid][key] = r
    reviewers = {key[0] for v in judgments.values() for key in v}
    if len(reviewers) != 2 or any(set(items) != {(reviewer, order) for reviewer in reviewers for order in ("AB", "BA")} for items in judgments.values()):
        raise EvidenceError("balanced blind positioning/reviewers incomplete")
    votes = Counter()
    inconsistent = []
    for cid, values in judgments.items():
        mapping = position_map(cid, manifest["corpus_sha256"])
        choices = []
        for (_, order), row in values.items():
            pref = row["preference"]
            choice = "tie" if pref == "tie" else mapping[order][0 if pref == "A" else 1]
            choices.append(choice)
        if len(set(choices)) != 1:
            inconsistent.append(cid)
        else:
            votes[choices[0]] += 1
    return {"complete": len(inconsistent) == 0, "reviewer_count": len(reviewers),
            "position_swap_inconsistent_cases": sorted(inconsistent), "wins": votes["candidate"],
            "ties": votes["tie"], "losses": votes["competitor"],
            "candidate_product_version": manifest["candidate_product_version"],
            "competitor_product_version": competitor["product_version"],
            "time_limit_seconds": manifest["time_limit_seconds"],
            "source_set_sha256": manifest["source_set_sha256"]}


def prepare_blind(cases: list[dict], manifest: dict, candidate: list[dict], competitor: list[dict]) -> list[dict]:
    ids = {c["case_id"] for c in cases}
    a = _unique_rows(candidate, "case_id", ids, 40)
    b = _unique_rows(competitor, "case_id", ids, 40)
    result = []
    for case in cases:
        cid = case["case_id"]
        for position, (left, right) in position_map(cid, manifest["corpus_sha256"]).items():
            values = {"candidate": a[cid]["output"], "competitor": b[cid]["output"]}
            result.append({"case_id": cid, "position": position, "response_a": values[left],
                           "response_b": values[right]})
    return result


def immutable_write(path: Path, obj: object) -> str:
    """O_EXCL preserves first-run evidence; reruns require a NEW named path."""
    content = (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as fp:
        fp.write(content)
        fp.flush()
        os.fsync(fp.fileno())
    return hashlib.sha256(content).hexdigest()


def preflight() -> dict:
    commands = [
        [sys.executable, "-m", "scripts.release_contract_check"],
        [sys.executable, "-m", "pytest", "-q", "tests/test_ruke_pilot_eval.py", "tests/test_pilot_workflow_eval.py", "tests/test_release_contract.py"],
    ]
    checks = []
    for command in commands:
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=600, check=False)
        checks.append({"command": command, "exit_code": proc.returncode, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-2000:]})
    return {"candidate_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True).stdout.strip(),
            "checks": checks, "passed": all(x["exit_code"] == 0 for x in checks)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate-registry", "preflight", "prepare-blind", "evaluate"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--heldout", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--competitor-outputs", type=Path)
    parser.add_argument("--evidence", type=Path, help="JSON with reviews, deterministic, operations, adjudications, comparison")
    parser.add_argument("--report", type=Path, help="New output file; overwrite is forbidden")
    parser.add_argument("--regression-rerun", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "validate-registry":
            obj = {"development_registry": len(registry_cases()), "heldout_executed": False}
        elif args.action == "preflight":
            obj = preflight()
        else:
            if not args.manifest or not args.heldout:
                raise EvidenceError("external frozen manifest and heldout required")
            outside_repo(args.manifest)
            if args.report:
                outside_repo(args.report)
            if args.evidence:
                outside_repo(args.evidence)
            if args.candidate:
                outside_repo(args.candidate)
            if args.competitor_outputs:
                outside_repo(args.competitor_outputs)
            manifest = read_json(args.manifest)
            cases = validate_manifest(manifest, args.heldout)
            if args.action == "prepare-blind":
                if not args.candidate or not args.competitor_outputs:
                    raise EvidenceError("both real output files required for blind packet")
                obj = prepare_blind(cases, manifest, read_jsonl(args.candidate), read_jsonl(args.competitor_outputs))
            else:
                if not args.evidence:
                    raise EvidenceError("external independently scored evidence required")
                evidence = read_json(args.evidence)
                scores = score_reviews(cases, evidence["reviews"], evidence.get("adjudications", []), evidence["deterministic"])
                faults = verify_operations(evidence["operations"], manifest["candidate_revision"])
                comparative = compare(cases, manifest, evidence.get("competitor"), evidence.get("comparisons"))
                custody = evidence.get("custody", {})
                # A checked-in self-assertion is not a proof. Preserve the external
                # custodian's status; independent attestation is reviewed out-of-band.
                isolated = (custody.get("independent_operator_review") == "verified"
                            and custody.get("developer_negative_read_test") == "denied"
                            and custody.get("replacement_of_exposed_cases") is True
                            and custody.get("custodian") not in (None, "", "developer")
                            and custody.get("receipt_sha256") is not None
                            and isinstance(custody.get("receipt_sha256"), str)
                            and SHA.fullmatch(custody["receipt_sha256"]) is not None)
                source_gate = evidence.get("required_repository_checks") == "passed" and evidence.get("canonical_release_contract") == "passed"
                high_severity = evidence.get("unresolved_high_severity_failures", None)
                if not isinstance(high_severity, list):
                    raise EvidenceError("high-severity findings inventory required")
                eligible = bool(scores["outcome_gate_pass"] and faults["fault_gate_pass"] and comparative["complete"]
                                and isolated and source_gate and not high_severity)
                obj = {"schema_version": 1, "result_kind": "regression_validation" if args.regression_rerun else "independent_first_run_submission",
                       "candidate_revision": manifest["candidate_revision"], "manifest_sha256": sha256(args.manifest),
                       "corpus_sha256": manifest["corpus_sha256"], "input_evidence_sha256": sha256(args.evidence),
                       "generated_at": datetime.now(timezone.utc).isoformat(), "outcomes": scores,
                       "operations": faults, "comparison": comparative, "custody_claim_submitted": bool(isolated),
                       "custody_independently_verified_by_this_program": False,
                       "repository_checks_reported_pass": source_gate, "unresolved_high_severity_failures": high_severity,
                       "operator_evidence_gate": eligible,
                       "release_authorization": False,
                       "limitations": ["External human custody, reviewer independence, source comparability and operated traces are not cryptographically or independently verified by this CLI.",
                                       "Canonical cohort_release_gate.py and human release authority are still mandatory.",
                                       "This report never authorizes activation."]}
        if args.report:
            digest = immutable_write(args.report, obj)
            print(json.dumps({"report": str(args.report), "sha256": digest, "eligible": obj.get("operator_evidence_gate", False)}))
        else:
            print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
        if args.action == "evaluate":
            return 0 if obj["operator_evidence_gate"] else 1
        if args.action == "preflight":
            return 0 if obj["passed"] else 1
        return 0
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "qualified": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
