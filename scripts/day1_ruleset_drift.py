"""Offline, fail-closed Day 1 main-ruleset drift diagnostics.

Consumes administrator-observed GitHub JSON readbacks; does NOT call GitHub,
write branch protection, mint credentials, or prove effective merge enforcement.
The existing main_protection_audit remains the release-governance authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re

REPOSITORY = "rumman52/Shuddho"
RULESET_ID = 27324410
ACTIONS_INTEGRATION_ID = 15368
# The three Day 1 checks are non-removable policy minima, even if someone
# edits the checked-in template. Additional reviewed checks remain enforced
# dynamically and must be pinned to the first-party GitHub Actions app.
MINIMUM_CHECKS = frozenset(("test-and-build", "coworker", "ci-merge-gate"))
POLICY_PATH = Path(__file__).resolve().parents[1] / "infra" / "github" / "main-ruleset.json"
MAX_READ_BYTES = 512_000
SHA1 = re.compile(r"[0-9a-f]{40}\Z")


class EvidenceError(ValueError):
    """Input is missing, malformed, or its reviewed policy was weakened."""


def _object(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise EvidenceError(f"{name} must be a JSON object")
    return value


def _typed_int(value: object, minimum: int = 1) -> bool:
    return type(value) is int and value >= minimum


def _rule(policy: dict, name: str) -> dict | None:
    rules = policy.get("rules")
    if not isinstance(rules, list):
        return None
    matches = [rule for rule in rules if isinstance(rule, dict) and rule.get("type") == name]
    if len(matches) != 1:
        return None
    return matches[0]


def _parameters(policy: dict, name: str) -> dict:
    rule = _rule(policy, name)
    params = rule.get("parameters") if rule else None
    return params if isinstance(params, dict) else {}


def _checks(params: dict, context: str) -> list:
    rows = params.get("required_status_checks")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("context") == context]


def _live_status_rows_are_unambiguous(params: dict) -> bool:
    """Every native status must have one unique, trusted first-party source."""
    rows = params.get("required_status_checks")
    if not isinstance(rows, list) or not rows:
        return False
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"context", "integration_id"}:
            return False
        context = row.get("context")
        if (
            not isinstance(context, str)
            or not context.strip()
            or context in observed
            or type(row.get("integration_id")) is not int
            or row["integration_id"] != ACTIONS_INTEGRATION_ID
        ):
            return False
        observed.add(context)
    return True


def validate_reviewed_policy(policy: object) -> dict:
    """Never let an altered/weak policy generate an apparently clean report."""
    p = _object(policy, "reviewed policy")
    if p.get("name") != "Shuddho main review and CI":
        raise EvidenceError("reviewed policy name is unexpected")
    if p.get("target") != "branch" or p.get("enforcement") != "active":
        raise EvidenceError("reviewed policy must target active branch protection")
    if p.get("bypass_actors") != []:
        raise EvidenceError("reviewed policy must forbid bypass actors")
    conditions = p.get("conditions")
    refs = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(refs, dict) or refs.get("include") != ["refs/heads/main"] or refs.get("exclude") != []:
        raise EvidenceError("reviewed policy must target only main without exclusions")
    for name in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
        if _rule(p, name) is None:
            raise EvidenceError(f"reviewed policy missing unique {name} rule")
    rev = _parameters(p, "pull_request")
    if not _typed_int(rev.get("required_approving_review_count")) or any(
        rev.get(flag) is not True
        for flag in ("dismiss_stale_reviews_on_push", "require_last_push_approval", "required_review_thread_resolution")
    ):
        raise EvidenceError("reviewed policy requires independent current-head approvals")
    status = _parameters(p, "required_status_checks")
    if status.get("strict_required_status_checks_policy") is not True or status.get("do_not_enforce_on_create") is not False:
        raise EvidenceError("reviewed policy requires strict checks on created branches")
    _reviewed_check_contexts(status)
    return p


def _reviewed_check_contexts(status: dict) -> tuple[str, ...]:
    """Require every reviewed status context, not just a hardcoded subset."""
    checks = status.get("required_status_checks")
    if not isinstance(checks, list) or not checks:
        raise EvidenceError("reviewed policy requires first-party status checks")
    contexts: list[str] = []
    for check in checks:
        if (
            not isinstance(check, dict)
            or set(check) != {"context", "integration_id"}
            or not isinstance(check.get("context"), str)
            or not check["context"].strip()
            or type(check.get("integration_id")) is not int
            or check["integration_id"] != ACTIONS_INTEGRATION_ID
        ):
            raise EvidenceError("reviewed policy contains malformed or untrusted status check")
        contexts.append(check["context"])
    if len(set(contexts)) != len(contexts):
        raise EvidenceError("reviewed policy contains duplicate status checks")
    if not MINIMUM_CHECKS.issubset(contexts):
        raise EvidenceError("reviewed policy is missing mandatory first-party checks")
    return tuple(contexts)


def analyze(branch: object, live_ruleset: object, policy: object, *, expected_main_sha: str, expected_ruleset_id: int = RULESET_ID) -> dict:
    """Produce only public gap codes and a source-bound, non-qualifying result."""
    reviewed = validate_reviewed_policy(policy)
    b = _object(branch, "main branch readback")
    r = _object(live_ruleset, "ruleset readback")
    if not isinstance(expected_main_sha, str) or SHA1.fullmatch(expected_main_sha) is None:
        raise EvidenceError("expected main SHA must be one full lowercase 40-character commit hash")
    if not _typed_int(expected_ruleset_id):
        raise EvidenceError("expected ruleset ID is invalid")
    gaps: list[str] = []

    def require(ok: bool, code: str) -> None:
        if not ok:
            gaps.append(code)

    observed_sha = b.get("commit", {}).get("sha") if isinstance(b.get("commit"), dict) else None
    require(b.get("name") == "main", "branch.name")
    require(b.get("protected") is True, "branch.protection")
    require(observed_sha == expected_main_sha, "branch.commit_sha")
    require(r.get("id") == expected_ruleset_id and type(r.get("id")) is int, "ruleset.identity")
    require(r.get("name") == reviewed["name"], "ruleset.name")
    require(r.get("target") == "branch" and r.get("enforcement") == "active", "ruleset.enforcement")
    conditions = r.get("conditions")
    refs = conditions.get("ref_name") if isinstance(conditions, dict) else None
    includes = refs.get("include") if isinstance(refs, dict) else None
    excludes = refs.get("exclude") if isinstance(refs, dict) else None
    require(isinstance(includes, list) and any(x in ("~DEFAULT_BRANCH", "refs/heads/main") for x in includes), "ruleset.main_scope")
    require(excludes == [], "ruleset.no_exclusions")
    require(r.get("bypass_actors") == [], "ruleset.bypass_actors_verified_empty")
    rules = r.get("rules")
    require(isinstance(rules, list), "ruleset.rules_present")
    if isinstance(rules, list):
        for name in ("deletion", "non_fast_forward", "pull_request", "required_status_checks"):
            require(_rule(r, name) is not None, f"ruleset.unique_{name}")
    reviews = _parameters(r, "pull_request")
    expected_reviews = _parameters(reviewed, "pull_request")
    require(
        _typed_int(reviews.get("required_approving_review_count"))
        and reviews["required_approving_review_count"] >= expected_reviews["required_approving_review_count"],
        "reviews.independent_approval_count",
    )
    for flag in ("dismiss_stale_reviews_on_push", "require_last_push_approval", "required_review_thread_resolution"):
        require(reviews.get(flag) is True, f"reviews.{flag}")
    check_params = _parameters(r, "required_status_checks")
    require(check_params.get("strict_required_status_checks_policy") is True, "checks.strict_current_head")
    require(check_params.get("do_not_enforce_on_create") is False, "checks.enforce_on_create")
    # Also validate every row, including non-mandatory statuses. Otherwise a
    # malformed or untrusted extra row can hide behind three correct checks.
    require(_live_status_rows_are_unambiguous(check_params), "checks.unambiguous_first_party_rows")
    # Track every check pinned by the current reviewed template, including
    # later additions such as Coworker (PR #754).
    for context in _reviewed_check_contexts(_parameters(reviewed, "required_status_checks")):
        rows = _checks(check_params, context)
        require(
            len(rows) == 1 and type(rows[0].get("integration_id")) is int
            and rows[0]["integration_id"] == ACTIONS_INTEGRATION_ID,
            f"checks.first_party_{context}",
        )
    return {
        "schema_version": 1,
        "repository": REPOSITORY,
        "expected_main_sha": expected_main_sha,
        "observed_main_sha": observed_sha if isinstance(observed_sha, str) and SHA1.fullmatch(observed_sha) else None,
        "ruleset_id": expected_ruleset_id,
        "status": "blocked_configuration" if gaps else "configuration_candidate",
        "drift": gaps,
        "qualified": False,
        "merge_enforcement_verified": False,
        "independent_review_verified": False,
        "required_next": "independent administrator review, native negative/positive merge controls, and exact-head CI",
        "evidence_limit": "offline JSON snapshots only; not authenticated live enforcement proof",
    }


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject ambiguous JSON at every nested object level."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("JSON input contains duplicate keys")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(_value: str) -> None:
    raise EvidenceError("JSON input contains non-finite numeric constants")


def _reject_nonfinite_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise EvidenceError("JSON input contains a non-finite numeric value")
    return number


def _read_json(path: Path) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_READ_BYTES:
        raise EvidenceError("a JSON input is missing, symlinked, or exceeds the size ceiling")
    raw = path.read_bytes()
    if len(raw) > MAX_READ_BYTES:
        raise EvidenceError("JSON input exceeds the size ceiling")
    try:
        data = json.loads(
            raw, object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_reject_nonfinite_json_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("invalid JSON input") from exc
    return _object(data, "JSON input"), hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch-json", type=Path, required=True)
    parser.add_argument("--ruleset-json", type=Path, required=True)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--ruleset-id", type=int, default=RULESET_ID)
    parser.add_argument("--policy-json", type=Path, default=POLICY_PATH)
    parser.add_argument("--output", type=Path, help="optional NEW private report file; never overwrite")
    args = parser.parse_args(argv)
    try:
        branch, branch_digest = _read_json(args.branch_json)
        ruleset, ruleset_digest = _read_json(args.ruleset_json)
        policy, policy_digest = _read_json(args.policy_json)
        report = analyze(branch, ruleset, policy, expected_main_sha=args.expected_main_sha, expected_ruleset_id=args.ruleset_id)
        # Bind the diagnostic to the exact captured input bytes. Hashes are
        # reproducibility references, not proof of administrator identity.
        report["branch_readback_sha256"] = branch_digest
        report["ruleset_readback_sha256"] = ruleset_digest
        report["reviewed_policy_sha256"] = policy_digest
        rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(args.output, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(rendered)
        print(rendered, end="")
        return 0 if not report["drift"] else 1
    except (EvidenceError, OSError) as exc:
        print(json.dumps({"status": "blocked_input", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
