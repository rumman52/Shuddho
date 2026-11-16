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
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

from scripts.pilot_workflow_eval import load_suite
from scripts.staging_release_freeze import RUNTIME_CAPABILITY_KEYS
from services.coworker.schemas import parse_draft, source_references

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests/fixtures/ruke_pilot_tasks.jsonl"
MATRIX = {(workflow, language): 10 for workflow in ("research_brief", "project_report_email") for language in ("bn", "en")}
RUBRIC = ("factual_source_fidelity", "constraint_compliance", "completeness_usefulness", "language_quality")
MAX_BYTES = 4_000_000
SHA = re.compile(r"^[0-9a-f]{64}$")
REV = re.compile(r"^[0-9a-f]{40}$")
BUILD_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
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


def reviewer_identity(value: object) -> str | None:
    """Normalize claimed reviewer IDs; this does not attest real independence."""
    if (not isinstance(value, str) or not value or value != value.strip()
            or not value.isprintable()):
        return None
    # Case and Unicode width variants are not separate human reviewers.
    identity = unicodedata.normalize("NFKC", value).casefold()
    return identity if identity.strip() and len(identity) <= 128 else None


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


def canonical_sha256(value: dict) -> str:
    """Canonical digest for a release-bound JSON readback object."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceError("candidate readback is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _readback_digest(value: object) -> str:
    if not isinstance(value, dict) or "readback_sha256" not in value:
        raise EvidenceError("candidate readback digest is missing")
    payload = {key: item for key, item in value.items() if key != "readback_sha256"}
    return canonical_sha256(payload)


def validate_candidate_identity(manifest: dict) -> dict:
    """Require the full immutable candidate identity before any holdout is read."""
    identity = manifest.get("candidate_identity")
    required = {
        "api_source_revision", "worker_source_revision",
        "api_build_digest", "worker_build_digest", "alembic_revision",
        "provider_id", "model_id", "prompt_registry_sha256", "tool_registry_sha256",
        "context_budget_bytes", "runtime_capabilities",
        "api_readback_sha256", "worker_readback_sha256", "schema_readback_sha256",
    }
    if not isinstance(identity, dict) or set(identity) != required:
        raise EvidenceError("candidate identity fields are incomplete or unexpected")
    revision = manifest.get("candidate_revision")
    if (not REV.fullmatch(revision or "")
            or identity["api_source_revision"] != revision
            or identity["worker_source_revision"] != revision):
        raise EvidenceError("API/worker source revisions do not match the exact candidate SHA")
    if (not isinstance(identity.get("api_build_digest"), str)
            or not BUILD_DIGEST.fullmatch(identity["api_build_digest"])
            or not isinstance(identity.get("worker_build_digest"), str)
            or not BUILD_DIGEST.fullmatch(identity["worker_build_digest"])):
        raise EvidenceError("API/worker image build digest is invalid")
    schema_revision = identity.get("alembic_revision")
    if (not isinstance(schema_revision, str) or not schema_revision.strip()
            or len(schema_revision) > 64 or not re.fullmatch(r"[A-Za-z0-9_]+", schema_revision)):
        raise EvidenceError("Alembic schema revision is invalid")
    for field in ("provider_id", "model_id"):
        value = identity.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise EvidenceError("candidate provider/model identity is missing: " + field)
    if identity["model_id"] != manifest.get("candidate_model"):
        raise EvidenceError("candidate model does not match the frozen runtime identity")
    for field in ("prompt_registry_sha256", "tool_registry_sha256",
                  "api_readback_sha256", "worker_readback_sha256", "schema_readback_sha256"):
        if not isinstance(identity.get(field), str) or not SHA.fullmatch(identity[field]):
            raise EvidenceError("candidate identity digest is invalid: " + field)
    budget = identity.get("context_budget_bytes")
    if type(budget) is not int or not 1 <= budget <= 1_048_576:
        raise EvidenceError("candidate context budget must be a positive bounded integer")
    capabilities = identity.get("runtime_capabilities")
    if (not isinstance(capabilities, dict)
            or set(capabilities) != RUNTIME_CAPABILITY_KEYS
            or any(type(value) is not bool for value in capabilities.values())):
        raise EvidenceError("candidate runtime capability inventory must contain exactly 43 boolean keys")
    return identity



def validate_evidence_binding(evidence: object, manifest_sha256: str) -> dict:
    """Bind the complete evidence JSON envelope to the exact frozen manifest."""
    if not isinstance(evidence, dict):
        raise EvidenceError("evidence.json must be an object")
    if not isinstance(manifest_sha256, str) or not SHA.fullmatch(manifest_sha256):
        raise EvidenceError("candidate manifest digest is invalid")
    if evidence.get("manifest_sha256") != manifest_sha256:
        raise EvidenceError("evidence.json is not bound to the exact candidate manifest digest")
    return evidence

def validate_candidate_readbacks(manifest: dict, readbacks: object) -> dict:
    """Check exact API, worker and schema readback equality and canonical digests.

    This validates consistency only. The independent operator must authenticate
    each readback against its source system before accepting the receipt.
    """
    identity = validate_candidate_identity(manifest)
    if not isinstance(readbacks, dict) or set(readbacks) != {"api", "worker", "schema"}:
        raise EvidenceError("authenticated API, worker and schema readbacks are required")
    common = {
        "release_id": manifest["release_id"],
        "alembic_revision": identity["alembic_revision"],
        "provider_id": identity["provider_id"],
        "model_id": identity["model_id"],
        "prompt_registry_sha256": identity["prompt_registry_sha256"],
        "tool_registry_sha256": identity["tool_registry_sha256"],
        "context_budget_bytes": identity["context_budget_bytes"],
        "rollout_manifest_sha256": manifest["rollout_manifest_sha256"],
        "runtime_capabilities": identity["runtime_capabilities"],
    }
    for role in ("api", "worker"):
        row = readbacks.get(role)
        expected = {
            **common,
            "source_revision": identity[f"{role}_source_revision"],
            "build_digest": identity[f"{role}_build_digest"],
        }
        if not isinstance(row, dict) or set(row) != set(expected) | {"readback_sha256"}:
            raise EvidenceError(role + " readback fields are incomplete or unexpected")
        if any(row.get(key) != value for key, value in expected.items()):
            raise EvidenceError(role + " authenticated readback does not match candidate manifest")
        if row.get("readback_sha256") != identity[f"{role}_readback_sha256"] or _readback_digest(row) != row.get("readback_sha256"):
            raise EvidenceError(role + " readback digest does not match candidate manifest")
    schema = readbacks.get("schema")
    schema_expected = {
        "release_id": manifest["release_id"],
        "source_revision": manifest["candidate_revision"],
        "migration_revision": identity["alembic_revision"],
        "api_revision": identity["alembic_revision"],
        "worker_revision": identity["alembic_revision"],
        "rollout_manifest_sha256": manifest["rollout_manifest_sha256"],
    }
    if not isinstance(schema, dict) or set(schema) != set(schema_expected) | {"readback_sha256"}:
        raise EvidenceError("schema readback fields are incomplete or unexpected")
    if any(schema.get(key) != value for key, value in schema_expected.items()):
        raise EvidenceError("Alembic API/worker schema readback does not match candidate manifest")
    if schema.get("readback_sha256") != identity["schema_readback_sha256"] or _readback_digest(schema) != schema.get("readback_sha256"):
        raise EvidenceError("schema readback digest does not match candidate manifest")
    return {"api": True, "worker": True, "schema": True, "consistent": True}


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
    if path.stat().st_mode & 0o222:
        raise EvidenceError("independent heldout fixture must be read-only")
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
    # Copying a developer-visible task to a protected directory does not make
    # it independently held out. Reject reused IDs and prompt/source pairs
    # from BOTH historical splits, including renamed case IDs. Reusing a
    # public source for a genuinely new task is not automatically forbidden.
    known = load_suite()["cases"]
    historical_ids = {case["id"] for case in known}
    def prompt_binding(instruction: str, source_hash: str) -> tuple[str, str]:
        return (" ".join(instruction.casefold().split()), source_hash)
    historical_prompts = {
        prompt_binding(case["instruction"], case["_source"]["sha256"])
        for case in known
    }
    if any(
        row["case_id"] in historical_ids
        or prompt_binding(row["instruction"], row["source_sha256"]) in historical_prompts
        for row in rows
    ):
        raise EvidenceError("external heldout contains exposed development or historical holdout content")
    return rows


def validate_manifest(manifest: dict, corpus: Path, *, allow_legacy: bool = False) -> list[dict]:
    """Validate a frozen candidate identity; legacy manifests are read-only."""
    if not isinstance(manifest, dict) or manifest.get("split") != "holdout":
        raise EvidenceError("invalid run manifest")
    version = manifest.get("schema_version")
    if type(version) is not int:
        raise EvidenceError("invalid run manifest schema_version")
    if version == 1:
        if not allow_legacy:
            raise EvidenceError("legacy manifest cannot qualify a new independent holdout")
        if not isinstance(manifest.get("candidate_revision"), str) or not REV.fullmatch(manifest["candidate_revision"]):
            raise EvidenceError("unbound candidate revision")
        if not isinstance(manifest.get("corpus_sha256"), str) or not SHA.fullmatch(manifest["corpus_sha256"]):
            raise EvidenceError("missing frozen corpus digest")
        for key in ("candidate_product_version", "candidate_model", "prompt_version", "tool_version",
                    "source_set_sha256", "run_started_at"):
            if not isinstance(manifest.get(key), str) or not manifest[key].strip():
                raise EvidenceError("missing frozen generation identity: " + key)
        if not isinstance(manifest["source_set_sha256"], str) or not SHA.fullmatch(manifest["source_set_sha256"]):
            raise EvidenceError("invalid source-set digest")
    elif version == 2:
        if not isinstance(manifest.get("candidate_revision"), str) or not REV.fullmatch(manifest["candidate_revision"]):
            raise EvidenceError("unbound candidate revision")
        if not isinstance(manifest.get("corpus_sha256"), str) or not SHA.fullmatch(manifest["corpus_sha256"]):
            raise EvidenceError("missing frozen corpus digest")
        for key in ("release_id", "run_id", "candidate_product_version", "candidate_model",
                    "prompt_version", "tool_version", "source_set_sha256", "run_started_at"):
            if not isinstance(manifest.get(key), str) or not manifest[key].strip():
                raise EvidenceError("missing frozen generation identity: " + key)
        if not isinstance(manifest["source_set_sha256"], str) or not SHA.fullmatch(manifest["source_set_sha256"]):
            raise EvidenceError("invalid source-set digest")
        if (not isinstance(manifest.get("rollout_manifest_sha256"), str)
                or not SHA.fullmatch(manifest["rollout_manifest_sha256"])):
            raise EvidenceError("missing frozen rollout-manifest digest")
        validate_candidate_identity(manifest)
    else:
        raise EvidenceError("unsupported run manifest schema_version")
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


def candidate_ledger(cases: list[dict], outputs: list[dict], *,
                    manifest_sha256: str | None = None) -> tuple[dict[str, str], dict]:
    """Bind scores to actual submitted outputs, preserving unknown usage as null."""
    ids = {case["case_id"] for case in cases}
    indexed = _unique_rows(outputs, "case_id", ids, 40)
    by_id = {case["case_id"]: case for case in cases}
    hashes, usage = {}, []
    for cid, row in indexed.items():
        if manifest_sha256 is not None and row.get("manifest_sha256") != manifest_sha256:
            raise EvidenceError("candidate output is not bound to frozen manifest digest: " + cid)
        if not isinstance(row.get("output"), dict):
            raise EvidenceError("candidate output must be a draft object")
        try:
            encoded = json.dumps(row["output"], ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode()
        except (ValueError, TypeError) as exc:
            raise EvidenceError("invalid candidate output encoding") from exc
        if len(encoded) > by_id[cid]["max_output_bytes"]:
            raise EvidenceError("candidate output exceeds task bound")
        task = by_id[cid]
        skill = "research" if task["workflow"] == "research_brief" else "report_email"
        try:
            parsed = parse_draft(skill, row["output"])
        except (ValueError, TypeError, KeyError) as exc:
            raise EvidenceError("candidate output violates production draft schema: " + cid) from exc
        if parsed.output_language != task["language"] or source_references(parsed) != {task["citation_id"]}:
            raise EvidenceError("candidate output language/citation scope mismatch: " + cid)
        hashes[cid] = hashlib.sha256(encoded).hexdigest()
        telemetry = row.get("telemetry")
        if telemetry is not None:
            if (not isinstance(telemetry, dict)
                    or set(telemetry) != {"tokens", "latency_ms", "cost_microusd"}
                    or any(type(t) is not int or t < 0 for t in telemetry.values())):
                raise EvidenceError("invalid candidate telemetry")
            usage.append(telemetry)
    complete = len(usage) == 40
    return hashes, {"usage_complete": complete,
                    "total_tokens": sum(t["tokens"] for t in usage) if complete else None,
                    "total_latency_ms": sum(t["latency_ms"] for t in usage) if complete else None,
                    "reported_cost_microusd": sum(t["cost_microusd"] for t in usage) if complete else None}

def score_reviews(cases: list[dict], reviews: list[dict], adjudications: list[dict],
                   deterministic: list[dict], *, output_hashes: dict | None = None) -> dict:
    ids = {c["case_id"] for c in cases}
    checks = _unique_rows(deterministic, "case_id", ids, 40)
    for case_id, check in checks.items():
        if type(check.get("passed")) is not bool or type(check.get("security_passed")) is not bool:
            raise EvidenceError("deterministic/security result missing for " + case_id)
        if not SHA.fullmatch(check.get("output_sha256", "")):
            raise EvidenceError("output identity missing for " + case_id)
        if output_hashes is not None and check["output_sha256"] != output_hashes[case_id]:
            raise EvidenceError("deterministic evidence is not bound to actual output: " + case_id)
    if len(reviews) != 80:
        raise EvidenceError("exactly two independent scores per task required")
    by_id = defaultdict(dict)
    for row in reviews:
        if not isinstance(row, dict) or row.get("case_id") not in ids:
            raise EvidenceError("unknown reviewer task")
        reviewer = reviewer_identity(row.get("reviewer_id"))
        if reviewer is None or reviewer in by_id[row["case_id"]]:
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
    reviewers = sorted(reviewer_set)
    pending = {cid for cid, r in by_id.items() if len({(tuple(x["scores"][d] for d in RUBRIC), x["source_supported"]) for x in r.values()}) > 1}
    resolved = _unique_rows(adjudications, "case_id", pending, len(pending))
    for cid, row in resolved.items():
        adjudicator = reviewer_identity(row.get("adjudicator_id"))
        if adjudicator is None or adjudicator in reviewer_set or not isinstance(row.get("evidence_note"), str) or not row["evidence_note"].strip():
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
        cell = case["workflow"] + "/" + case["language"]
        per_cell[cell]["total"] += 1
        reviewer_scores = [sum(by_id[cid][reviewer]["scores"][dimension] for dimension in RUBRIC)
                           for reviewer in reviewers]
        reviewer_rubrics = [
            {"reviewer_id": reviewer, "scores": dict(by_id[cid][reviewer]["scores"])}
            for reviewer in reviewers
        ]
        both_reviewers_meet_floor = all(
            total >= 7 and min(by_id[cid][reviewer]["scores"].values()) > 0
            for reviewer, total in zip(reviewers, reviewer_scores)
        )
        accepted = (deterministic_ok and chosen["source_supported"]
                    and both_reviewers_meet_floor and sum(ratings.values()) >= 7
                    and min(ratings.values()) > 0)
        per_cell[cell]["accepted"] += int(accepted)
        results.append({"case_id": cid, "cell": cell, "workflow": case["workflow"],
                        "language": case["language"], "score": sum(ratings.values()),
                        "accepted": accepted, "deterministic_pass": deterministic_ok,
                        "security_passed": checks[cid]["security_passed"],
                        "source_supported": chosen["source_supported"],
                        "reviewer_scores": reviewer_scores, "reviewer_rubrics": reviewer_rubrics})
    accepted = sum(r["accepted"] for r in results)
    security_failed_cases = sorted(cid for cid, check in checks.items() if not check["security_passed"])
    security_gate_pass = not security_failed_cases
    quality_gate_pass = accepted >= 36 and all(
        x["total"] == 10 and x["accepted"] >= 9 for x in per_cell.values()
    )
    return {"accepted": accepted, "total": 40, "by_cell": dict(sorted(per_cell.items())),
            "outcome_gate_pass": quality_gate_pass and security_gate_pass,
            "security_gate_pass": security_gate_pass,
            "security_failed_cases": security_failed_cases,
            "disagreements_adjudicated": len(pending),
            "reviewer_count": len(reviewer_set), "reviewers": reviewers, "results": results}


def day10_first_run_scores(scores: dict) -> dict:
    """Shape the preserved Day 9 scores for the existing Day 10 exact-release gate."""
    return {
        "accepted": scores["accepted"],
        "total": scores["total"],
        "cases": [
            {"id": row["case_id"], "workflow": row["workflow"], "language": row["language"],
             "accepted": row["accepted"], "security_passed": row["security_passed"],
             "reviewer_scores": row["reviewer_scores"],
             "reviewer_rubrics": row["reviewer_rubrics"]}
            for row in scores["results"]
        ],
    }

def _trace_sha_ok(value: object) -> bool:
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def operated_trace_ok(row: dict, required_boundaries: tuple[str, ...]) -> bool:
    """Check the common trace evidence required for an operated recovery case."""
    observed_at = row.get("observed_at")
    boundaries = row.get("boundaries")
    if (
        row.get("execution") != "operated"
        or row.get("unauthorized_access") is not False
        or row.get("unauthorized_mutation") is not False
        or not _trace_sha_ok(row.get("trace_sha256"))
        or not isinstance(observed_at, str) or not observed_at.strip()
        or not isinstance(boundaries, dict)
    ):
        return False
    for target in required_boundaries:
        evidence = boundaries.get(target)
        if (
            not isinstance(evidence, dict) or evidence.get("mode") != "real"
            or not isinstance(evidence.get("instance"), str) or not evidence["instance"].strip()
            or not _trace_sha_ok(evidence.get("trace_sha256"))
        ):
            return False
    return True


def verify_operations(rows: list[dict], candidate_revision: str, *,
                      manifest_sha256: str | None = None,
                      release_id: str | None = None,
                      rollout_manifest_sha256: str | None = None) -> dict:
    ids = {str(i) for i in OPERATED}
    normalized = [{**r, "row": str(r.get("row"))} for r in rows]
    indexed = _unique_rows(normalized, "row", ids, 20)
    failed = []
    for raw_id, row in indexed.items():
        index = int(raw_id)
        name, needed = OPERATED[index]
        if row.get("scenario") != name or row.get("candidate_revision") != candidate_revision:
            raise EvidenceError("operated scenario/revision mismatch")
        if manifest_sha256 is not None and row.get("manifest_sha256") != manifest_sha256:
            raise EvidenceError("operated scenario is not bound to frozen manifest digest")
        if release_id is not None and row.get("release_id") != release_id:
            raise EvidenceError("operated scenario release identity mismatch")
        if rollout_manifest_sha256 is not None and row.get("rollout_manifest_sha256") != rollout_manifest_sha256:
            raise EvidenceError("operated scenario rollout identity mismatch")
        if row.get("status") != "pass" or not operated_trace_ok(row, needed):
            failed.append(index)
    failed.sort()
    return {"total": 20, "passed": 20 - len(failed), "failed_rows": failed, "fault_gate_pass": not failed,
            "evidence_level": "operator_submitted_operated_traces_not_independently_attested"}


def comparison_evidence_recorded(value: object) -> bool:
    """A reproducible comparison or explicitly unavailable competitor access is reportable."""
    return (isinstance(value, dict) and (
        value.get("complete") is True
        or (value.get("gap_reason") == "competitor_access_unavailable"
            and isinstance(value.get("comparison_gap"), str)
            and bool(value["comparison_gap"].strip()))
    ))

def read_blinding_key(path: Path) -> bytes:
    """External secret custody, separate from reviewer packets and the repo."""
    outside_repo(path)
    if not path.is_file() or path.stat().st_size != 32:
        raise EvidenceError("blind mapping requires a separate 32-byte D-controlled key")
    mode = path.stat().st_mode & 0o777
    if not mode & 0o400 or mode & 0o077:
        raise EvidenceError("blinding key must be private to D (0600 or 0400)")
    return path.read_bytes()


def position_map(case_id: str, corpus_sha256: str, *, blinding_key: bytes) -> dict:
    if not isinstance(blinding_key, bytes) or len(blinding_key) != 32:
        raise EvidenceError("secret 32-byte blinding key required")
    bit = hmac.digest(blinding_key, (corpus_sha256 + ":" + case_id).encode(), "sha256")[-1] & 1
    return {"AB": ("candidate", "competitor") if bit == 0 else ("competitor", "candidate"),
            "BA": ("competitor", "candidate") if bit == 0 else ("candidate", "competitor")}


def compare(cases: list[dict], manifest: dict, competitor: dict | None, rows: list[dict] | None,
            adjudications: list[dict] | None = None, *, blinding_key: bytes | None = None,
            manifest_sha256: str | None = None, access_gap: str | None = None) -> dict:
    if competitor is None and rows is None:
        if isinstance(access_gap, str) and access_gap.strip():
            return {"complete": False, "comparison_gap": access_gap.strip(),
                    "gap_reason": "competitor_access_unavailable",
                    "wins": None, "ties": None, "losses": None}
        return {"complete": False, "comparison_gap": "competitor access gap not explicitly documented",
                "gap_reason": "unrecorded", "wins": None, "ties": None, "losses": None}
    if competitor is None or rows is None:
        return {"complete": False, "comparison_gap": "competitor metadata or blinded judgments missing",
                "gap_reason": "incomplete_evidence", "wins": None, "ties": None, "losses": None}
    if not isinstance(blinding_key, bytes) or len(blinding_key) != 32:
        raise EvidenceError("independent D-controlled secret mapping required for comparator")
    for field in ("product", "product_version", "model", "run_started_at"):
        if not isinstance(competitor.get(field), str) or not competitor[field].strip():
            raise EvidenceError("competitor identity incomplete: " + field)
    if competitor.get("source_set_sha256") != manifest["source_set_sha256"] or competitor.get("time_limit_seconds") != manifest["time_limit_seconds"]:
        raise EvidenceError("competitor sources/time ceiling not comparable")
    if manifest_sha256 is not None and (
        competitor.get("manifest_sha256") != manifest_sha256
        or competitor.get("release_id") != manifest["release_id"]
        or competitor.get("rollout_manifest_sha256") != manifest["rollout_manifest_sha256"]
    ):
        raise EvidenceError("competitor comparison is not bound to frozen candidate manifest")
    if len(rows) != 160:
        raise EvidenceError("two reviewers and both swapped positions required for 40 tasks")
    ids = {c["case_id"] for c in cases}
    judgments = defaultdict(dict)
    for r in rows:
        cid, reviewer, order = r.get("case_id"), reviewer_identity(r.get("reviewer_id")), r.get("position")
        if cid not in ids or reviewer is None or order not in ("AB", "BA"):
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
        mapping = position_map(cid, manifest["corpus_sha256"], blinding_key=blinding_key)
        choices = []
        for (_, order), row in values.items():
            pref = row["preference"]
            choice = "tie" if pref == "tie" else mapping[order][0 if pref == "A" else 1]
            choices.append(choice)
        if len(set(choices)) != 1:
            inconsistent.append(cid)
        else:
            votes[choices[0]] += 1
    contested = set(inconsistent)
    adjudications = [] if adjudications is None else adjudications
    resolutions = _unique_rows(adjudications, "case_id", contested, len(adjudications))
    for cid, row in resolutions.items():
        adjudicator = reviewer_identity(row.get("adjudicator_id"))
        if (adjudicator is None or adjudicator in reviewers
                or row.get("position") not in ("AB", "BA")
                or row.get("preference") not in ("A", "B", "tie")
                or not isinstance(row.get("evidence_note"), str) or not row["evidence_note"].strip()):
            raise EvidenceError("blind comparative adjudication needs an independent third reviewer and source rationale")
        mapped = position_map(cid, manifest["corpus_sha256"], blinding_key=blinding_key)[row["position"]]
        label = "tie" if row["preference"] == "tie" else mapped[0 if row["preference"] == "A" else 1]
        votes[label] += 1
    remaining = sorted(contested - set(resolutions))
    return {"complete": len(remaining) == 0, "reviewer_count": len(reviewers),
            "position_swap_inconsistent_cases": sorted(inconsistent),
            "disagreements_adjudicated": len(resolutions),
            "remaining_disagreements": remaining,
            "wins": votes["candidate"], "ties": votes["tie"], "losses": votes["competitor"],
            "blinding_key_sha256": hashlib.sha256(blinding_key).hexdigest(),
            "candidate_product_version": manifest["candidate_product_version"],
            "competitor_product_version": competitor["product_version"],
            "time_limit_seconds": manifest["time_limit_seconds"],
            "source_set_sha256": manifest["source_set_sha256"],
            "manifest_sha256": manifest_sha256}

def prepare_blind(cases: list[dict], manifest: dict, candidate: list[dict], competitor: list[dict],
                   *, blinding_key: bytes, manifest_sha256: str | None = None) -> list[dict]:
    ids = {c["case_id"] for c in cases}
    a = _unique_rows(candidate, "case_id", ids, 40)
    b = _unique_rows(competitor, "case_id", ids, 40)
    if manifest_sha256 is not None and any(
        row.get("manifest_sha256") != manifest_sha256 for row in (*a.values(), *b.values())
    ):
        raise EvidenceError("blind packet outputs are not bound to frozen manifest digest")
    result = []
    for case in cases:
        cid = case["case_id"]
        for position, (left, right) in position_map(cid, manifest["corpus_sha256"], blinding_key=blinding_key).items():
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
    parser.add_argument("--blinding-key", type=Path,
                        help="D-only secret 32-byte file outside checkout; never share with judges")
    parser.add_argument("--evidence", type=Path, help="JSON with reviews, deterministic, operations, adjudications, comparison")
    parser.add_argument("--report", type=Path, help="New output file; overwrite is forbidden")
    parser.add_argument("--regression-rerun", action="store_true")
    args = parser.parse_args(argv)
    manifest = None
    manifest_digest = None
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
            manifest_digest = sha256(args.manifest)
            cases = validate_manifest(manifest, args.heldout)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                  text=True, capture_output=True, check=True).stdout.strip()
            if manifest["candidate_revision"] != head:
                raise EvidenceError("manifest revision differs from exact checkout head")
            if args.action == "prepare-blind":
                if not args.candidate or not args.competitor_outputs or not args.blinding_key:
                    raise EvidenceError("real outputs and D-only blinding key required for blind packet")
                key = read_blinding_key(args.blinding_key)
                rows = prepare_blind(cases, manifest, read_jsonl(args.candidate),
                                     read_jsonl(args.competitor_outputs), blinding_key=key,
                                     manifest_sha256=manifest_digest)
                obj = {
                    "schema_version": 1,
                    "manifest_sha256": manifest_digest,
                    "release_id": manifest["release_id"],
                    "source_revision": manifest["candidate_revision"],
                    "rollout_manifest_sha256": manifest["rollout_manifest_sha256"],
                    "run_id": manifest["run_id"],
                    "rows": rows,
                }
            else:
                if not args.evidence or not args.candidate:
                    raise EvidenceError("external independently scored evidence and candidate outputs required")
                evidence = validate_evidence_binding(read_json(args.evidence), manifest_digest)
                readback_status = validate_candidate_readbacks(manifest, evidence.get("candidate_readbacks"))
                output_hashes, usage = candidate_ledger(
                    cases, read_jsonl(args.candidate), manifest_sha256=manifest_digest
                )
                scores = score_reviews(cases, evidence["reviews"], evidence.get("adjudications", []),
                                       evidence["deterministic"], output_hashes=output_hashes)
                faults = verify_operations(
                    evidence["operations"], manifest["candidate_revision"],
                    manifest_sha256=manifest_digest, release_id=manifest["release_id"],
                    rollout_manifest_sha256=manifest["rollout_manifest_sha256"],
                )
                key = read_blinding_key(args.blinding_key) if args.blinding_key else None
                comparative = compare(
                    cases, manifest, evidence.get("competitor"), evidence.get("comparisons"),
                    evidence.get("comparison_adjudications", []), blinding_key=key,
                    manifest_sha256=manifest_digest,
                    access_gap=evidence.get("competitor_access_gap"),
                )
                custody = evidence.get("custody", {})
                if not isinstance(custody, dict):
                    raise EvidenceError("custody receipt must be an object")
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
                eligible = bool(readback_status["consistent"] and scores["outcome_gate_pass"]
                                and faults["fault_gate_pass"] and comparison_evidence_recorded(comparative)
                                and isolated and source_gate and not high_severity)
                first_run_scores = day10_first_run_scores(scores)
                obj = {
                    "schema_version": 2,
                    "result_kind": "regression_validation" if args.regression_rerun else "operator_submitted_first_run",
                    "run_kind": "regression_rerun" if args.regression_rerun else "first_run",
                    "run_id": manifest["run_id"],
                    "release_id": manifest["release_id"],
                    "source_revision": manifest["candidate_revision"],
                    "candidate_revision": manifest["candidate_revision"],
                    "rollout_manifest_sha256": manifest["rollout_manifest_sha256"],
                    "candidate_identity": manifest["candidate_identity"],
                    "candidate_readbacks": evidence["candidate_readbacks"],
                    "manifest_sha256": manifest_digest,
                    "corpus_sha256": manifest["corpus_sha256"],
                    "input_evidence_sha256": sha256(args.evidence),
                    "candidate_outputs_sha256": sha256(args.candidate),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "scores": first_run_scores,
                    "reviewers": scores["reviewers"],
                    "outcomes": scores,
                    "usage": {**usage, "reported_cost_per_accepted_task_microusd":
                              (usage["reported_cost_microusd"] / scores["accepted"]
                               if usage["reported_cost_microusd"] is not None and scores["accepted"] else None)},
                    "operations": faults,
                    "comparison": comparative,
                    "custody_claim_submitted": bool(isolated),
                    "custody_independently_verified_by_this_program": False,
                    "candidate_readback_consistency_pass": readback_status["consistent"],
                    "repository_checks_reported_pass": source_gate,
                    "unresolved_high_severity_failures": high_severity,
                    "operator_evidence_gate": eligible,
                    "release_authorization": False,
                    "limitations": [
                        "Readback digests prove internal consistency only; C/D must authenticate the API, worker and schema receipts against source systems.",
                        "External human custody, reviewer independence, source comparability and operated traces are not independently verified by this CLI.",
                        "Canonical cohort_release_gate.py and human release authority are still mandatory.",
                        "This report never authorizes activation.",
                    ],
                }
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
        failure = {
            "schema_version": 2 if manifest and manifest.get("schema_version") == 2 else 1,
            "error": str(exc),
            "qualified": False,
            "result_kind": "regression_validation" if args.regression_rerun else "operator_submitted_first_run",
            "run_kind": "regression_rerun" if args.regression_rerun else "first_run",
            "release_authorization": False,
        }
        if isinstance(manifest, dict):
            failure.update({
                "run_id": manifest.get("run_id"),
                "release_id": manifest.get("release_id"),
                "source_revision": manifest.get("candidate_revision"),
                "rollout_manifest_sha256": manifest.get("rollout_manifest_sha256"),
                "manifest_sha256": manifest_digest,
            })
        if args.report:
            try:
                outside_repo(args.report)
                digest = immutable_write(args.report, failure)
                print(json.dumps({"report": str(args.report), "sha256": digest, **failure}))
            except (EvidenceError, OSError, ValueError) as save_exc:
                print(json.dumps({**failure, "report_error": str(save_exc)}))
        else:
            print(json.dumps(failure))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
