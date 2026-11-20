"""Administrator-only, fail-closed reconciliation of the EXISTING main ruleset.

Dry-run is the default. This never creates a replacement ruleset, deletes a rule,
changes deployment state, or declares release qualification. Operated negative
and positive merge controls and independent review remain separate requirements.

The existing creation-only operator deliberately refuses to update a weak
ruleset. This command handles that one explicit Day 1 gap without weakening it.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re

from scripts.apply_main_ruleset import (
    API_ROOT,
    EXPECTED_REPOSITORY,
    POLICY_PATH,
    ApplyMainRulesetError,
    _is_compliant_existing,
    _list_main_target_rulesets,
    _request_json,
    _validate_candidate,
    _verify_applied_state,
)

RULESET_ID = 27324410
EXPECTED_RULESET_NAME = "Shuddho main review and CI"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
REVIEW_KEYS = frozenset({
    "required_approving_review_count",
    "dismiss_stale_reviews_on_push",
    "required_reviewers",
    "require_code_owner_review",
    "require_last_push_approval",
    "required_review_thread_resolution",
    "require_extra_approval_for_unattributed_changes",
    "allowed_merge_methods",
})
MERGE_METHODS = frozenset({"merge", "squash", "rebase"})


def ruleset_fingerprint(ruleset: dict) -> str:
    """Bind only the security-relevant server readback, not volatile dates."""
    fields = (
        "id", "name", "source", "source_type", "target",
        "enforcement", "conditions", "bypass_actors", "rules",
    )
    data = {name: ruleset.get(name) for name in fields}
    serialized = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _read_unique_existing(root: str, token: str, expected_main_sha: str) -> dict:
    branch = _request_json("GET", root + "/branches/main", token)
    if (
        not isinstance(branch, dict)
        or branch.get("name") != "main"
        or branch.get("protected") is not True
        or not isinstance(branch.get("commit"), dict)
        or branch["commit"].get("sha") != expected_main_sha
    ):
        raise ApplyMainRulesetError("main SHA or protected-branch state changed; restart review")
    listed = _request_json(
        "GET", root + "/rulesets?includes_parents=true&per_page=100", token,
    )
    matching = _list_main_target_rulesets(root, token, listed)
    if len(matching) != 1:
        raise ApplyMainRulesetError("effective main rulesets are missing or ambiguous")
    existing = matching[0]
    if (
        type(existing.get("id")) is not int
        or existing["id"] != RULESET_ID
        or existing.get("name") != EXPECTED_RULESET_NAME
        or existing.get("source_type") != "Repository"
        or existing.get("source") != EXPECTED_REPOSITORY
        or existing.get("target") != "branch"
        or existing.get("enforcement") != "active"
        or existing.get("bypass_actors") != []
    ):
        raise ApplyMainRulesetError("expected repository-owned, no-bypass ruleset not proven")
    conditions = existing.get("conditions")
    refs = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if (
        not isinstance(refs, dict)
        or refs.get("include") not in (
            ["refs/heads/main"], ["~DEFAULT_BRANCH"],
        )
        or refs.get("exclude") != []
        or set(conditions) != {"ref_name"}
    ):
        raise ApplyMainRulesetError("existing ruleset main scope is not exact")
    return existing


def _safe_target(existing: dict, reviewed: dict) -> dict:
    """Never discard existing unrelated or stronger policy silently."""
    existing_rules = existing.get("rules")
    candidate_rules = reviewed.get("rules")
    if not isinstance(existing_rules, list) or not isinstance(candidate_rules, list):
        raise ApplyMainRulesetError("existing rules are not inspectable")
    by_type: dict[str, dict] = {}
    candidate_types = {row["type"] for row in candidate_rules}
    for rule in existing_rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("type"), str):
            raise ApplyMainRulesetError("existing rule entry is malformed")
        kind = rule["type"]
        if kind in by_type or kind not in candidate_types:
            raise ApplyMainRulesetError(
                "unknown, duplicated, or additional existing rule requires manual reconciliation"
            )
        by_type[kind] = rule
    if not {"deletion", "non_fast_forward", "pull_request"}.issubset(by_type):
        raise ApplyMainRulesetError("existing deletion, history or PR safeguards missing")
    for kind in ("deletion", "non_fast_forward"):
        if set(by_type[kind]) != {"type"}:
            raise ApplyMainRulesetError("existing non-mutating rule has unexpected settings")
    review = by_type["pull_request"].get("parameters")
    if not isinstance(review, dict) or set(review) - REVIEW_KEYS:
        raise ApplyMainRulesetError("unrecognized review constraints require manual reconciliation")
    count = review.get("required_approving_review_count")
    if type(count) is not int or count < 0 or count > 1:
        raise ApplyMainRulesetError("existing stricter/invalid review count cannot be overwritten")
    if (
        review.get("require_code_owner_review") is True
        or review.get("require_extra_approval_for_unattributed_changes") is True
        or review.get("required_reviewers", []) != []
    ):
        raise ApplyMainRulesetError("stronger reviewer constraints require manual reconciliation")
    methods = review.get("allowed_merge_methods")
    if methods is not None and (
        not isinstance(methods, list)
        or not methods
        or any(not isinstance(value, str) or value not in MERGE_METHODS for value in methods)
        or len(methods) != len(set(methods))
    ):
        raise ApplyMainRulesetError("existing merge-method restrictions are ambiguous")
    if "required_status_checks" in by_type:
        checks_params = by_type["required_status_checks"].get("parameters")
        if not isinstance(checks_params, dict) or (
            set(checks_params)
            - {"strict_required_status_checks_policy", "do_not_enforce_on_create", "required_status_checks"}
        ):
            raise ApplyMainRulesetError("unknown status-check constraints require manual reconciliation")
        rows = checks_params.get("required_status_checks", [])
        target_rows = next(
            x["parameters"]["required_status_checks"]
            for x in candidate_rules if x["type"] == "required_status_checks"
        )
        allowed = {row["context"] for row in target_rows}
        if not isinstance(rows, list):
            raise ApplyMainRulesetError("additional required status checks must be preserved manually")
        observed_contexts: set[str] = set()
        for row in rows:
            if (
                not isinstance(row, dict)
                or set(row) - {"context", "integration_id"}
                or not isinstance(row.get("context"), str)
                or row["context"] not in allowed
                or row["context"] in observed_contexts
            ):
                # Preserve unknown or duplicate native controls for an
                # administrator to review instead of silently replacing them.
                raise ApplyMainRulesetError(
                    "additional required status checks must be preserved manually"
                )
            observed_contexts.add(row["context"])
    target = deepcopy(reviewed)
    if methods is not None:
        next_review = next(
            x["parameters"] for x in target["rules"] if x["type"] == "pull_request"
        )
        next_review["allowed_merge_methods"] = list(methods)
    return target


def reconcile_main_ruleset(
    repository: str,
    token: str,
    policy: object,
    *,
    expected_main_sha: str,
    apply: bool = False,
    expected_current_ruleset_sha256: str | None = None,
    confirm_repository: str | None = None,
    confirm_ruleset_id: int | None = None,
) -> dict:
    """Review or explicitly update one existing rule, never create a new one."""
    if repository != EXPECTED_REPOSITORY or not isinstance(token, str) or not token:
        raise ApplyMainRulesetError("repository or administrator credential is unavailable")
    if not isinstance(expected_main_sha, str) or not FULL_SHA.fullmatch(expected_main_sha):
        raise ApplyMainRulesetError("expected main SHA must be the exact 40-character revision")
    reviewed = _validate_candidate(policy)
    if apply and (
        confirm_repository != EXPECTED_REPOSITORY
        or type(confirm_ruleset_id) is not int or confirm_ruleset_id != RULESET_ID
        or not isinstance(expected_current_ruleset_sha256, str)
        or not DIGEST.fullmatch(expected_current_ruleset_sha256)
    ):
        raise ApplyMainRulesetError(
            "apply requires exact repository, ruleset ID and dry-run fingerprint confirmations"
        )
    root = f"{API_ROOT}/repos/{EXPECTED_REPOSITORY}"
    existing = _read_unique_existing(root, token, expected_main_sha)
    observed = ruleset_fingerprint(existing)
    if expected_current_ruleset_sha256 is not None and observed != expected_current_ruleset_sha256:
        raise ApplyMainRulesetError("ruleset configuration changed since dry-run; restart review")
    if _is_compliant_existing(existing):
        return {
            "status": "already_configured", "ruleset_id": RULESET_ID,
            "observed_sha256": observed, "qualified": False,
            "merge_enforcement_verified": False,
            "required_next": "independent negative/positive merge-control tests",
        }
    target = _safe_target(existing, reviewed)
    if not apply:
        return {
            "status": "dry_run", "repository": repository,
            "ruleset_id": RULESET_ID,
            "main_sha": expected_main_sha,
            "observed_sha256": observed,
            "would_update_existing": True, "would_create": False,
            "required_checks": [
                row["context"] for entry in target["rules"]
                if entry["type"] == "required_status_checks"
                for row in entry["parameters"]["required_status_checks"]
            ],
            "qualified": False, "merge_enforcement_verified": False,
            "required_next": (
                "independent admin review; apply only with exact SHA, "
                "observed fingerprint and explicit confirmations"
            ),
        }
    # Refetch immediately before the single PUT. No create/overwrite retry and
    # no unreviewed rule replacements if another operator has changed settings.
    latest = _read_unique_existing(root, token, expected_main_sha)
    if ruleset_fingerprint(latest) != observed:
        raise ApplyMainRulesetError("ruleset changed just before PUT; no write attempted")
    endpoint = root + f"/rulesets/{RULESET_ID}"
    try:
        response = _request_json("PUT", endpoint, token, target)
        if not isinstance(response, dict) or response.get("id") != RULESET_ID:
            raise ApplyMainRulesetError("PUT response did not identify the existing ruleset")
    except ApplyMainRulesetError as error:
        # A lost response can follow a committed PUT. Never blindly repeat it.
        try:
            readback = _verify_applied_state(
                root, token, expected_id=RULESET_ID, expected_name=EXPECTED_RULESET_NAME,
            )
        except ApplyMainRulesetError as verify_error:
            raise ApplyMainRulesetError(
                "PUT outcome uncertain and read-back did not prove success; "
                "do not retry, inspect Settings > Rules directly"
            ) from error
        return {
            "status": "put_outcome_uncertain_but_verified",
            "ruleset_id": readback["id"], "qualified": False,
            "merge_enforcement_verified": False,
            "required_next": "independent negative/positive merge-control tests",
        }
    try:
        readback = _verify_applied_state(
            root, token, expected_id=RULESET_ID, expected_name=EXPECTED_RULESET_NAME,
        )
    except ApplyMainRulesetError as error:
        raise ApplyMainRulesetError(
            "PUT returned but authoritative read-back failed; do not repeat the write"
        ) from error
    return {
        "status": "configuration_updated_readback_verified",
        "ruleset_id": readback["id"],
        "observed_sha256": ruleset_fingerprint(readback),
        "qualified": False, "merge_enforcement_verified": False,
        "required_next": "independent negative/positive merge-control tests",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=EXPECTED_REPOSITORY)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-current-ruleset-sha256")
    parser.add_argument("--confirm-repository")
    parser.add_argument("--confirm-ruleset-id", type=int)
    args = parser.parse_args(argv)
    try:
        policy = json.loads(Path(POLICY_PATH).read_text(encoding="utf-8"))
        result = reconcile_main_ruleset(
            args.repository, os.environ.get("GITHUB_TOKEN", ""), policy,
            expected_main_sha=args.expected_main_sha,
            apply=args.apply,
            expected_current_ruleset_sha256=args.expected_current_ruleset_sha256,
            confirm_repository=args.confirm_repository,
            confirm_ruleset_id=args.confirm_ruleset_id,
        )
    except (ApplyMainRulesetError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
