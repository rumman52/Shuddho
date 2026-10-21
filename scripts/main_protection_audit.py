"""Read-only V-01 configuration audit for Shuddho's default branch.

This is defense in depth, NOT a native merge-permission control and NOT
proof that required reviewers / checks cannot be bypassed. A repository
administrator must additionally perform negative and positive merge tests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CHECKS = frozenset({"test-and-build", "coworker", "ci-merge-gate"})


class GovernanceAuditError(ValueError):
    """Governance configuration missing, inconsistent or not inspectable."""


def _active_main_ruleset(rule: dict) -> bool:
    if not isinstance(rule, dict):
        return False
    if rule.get("target") != "branch" or rule.get("enforcement") != "active":
        return False
    conditions = rule.get("conditions")
    if not isinstance(conditions, dict):
        return False
    refs = conditions.get("ref_name")
    if not isinstance(refs, dict):
        return False
    includes, excludes = refs.get("include"), refs.get("exclude")
    if not isinstance(includes, list) or not isinstance(excludes, list):
        return False
    # Explicit main/default-branch targeting only; unreviewed glob semantics
    # are not accepted as sufficient evidence for production qualification.
    if not any(x in ("refs/heads/main", "~DEFAULT_BRANCH") for x in includes):
        return False
    if any(x in ("refs/heads/main", "~DEFAULT_BRANCH") for x in excludes):
        return False
    # Normal development accounts must not have a bypass on this rule.
    if rule.get("bypass_actors") != []:
        return False
    return True


def _has_required_rules(rule: dict) -> bool:
    rules = rule.get("rules")
    if not isinstance(rules, list):
        return False
    present = {entry.get("type") for entry in rules if isinstance(entry, dict)}
    if not {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}.issubset(present):
        return False

    reviews = [
        entry.get("parameters")
        for entry in rules
        if isinstance(entry, dict) and entry.get("type") == "pull_request"
    ]
    checks = [
        entry.get("parameters")
        for entry in rules
        if isinstance(entry, dict) and entry.get("type") == "required_status_checks"
    ]

    def valid_reviews(p):
        return (
            isinstance(p, dict)
            and type(p.get("required_approving_review_count")) is int
            and p["required_approving_review_count"] >= 1
            and p.get("dismiss_stale_reviews_on_push") is True
            and p.get("require_last_push_approval") is True
            and p.get("required_review_thread_resolution") is True
        )

    def valid_checks(p):
        if not isinstance(p, dict) or p.get("strict_required_status_checks_policy") is not True:
            return False
        required = p.get("required_status_checks")
        if not isinstance(required, list):
            return False
        # GitHub's required-status names alone do not authenticate a check
        # publisher. Match the pinned first-party GitHub Actions app ID,
        # including every duplicate entry for a required context.
        for context in CHECKS:
            matches = [
                row for row in required
                if isinstance(row, dict) and row.get("context") == context
            ]
            if not matches or any(
                type(row.get("integration_id")) is not int
                or row["integration_id"] != 15368
                for row in matches
            ):
                return False
        return True

    return any(valid_reviews(p) for p in reviews) and any(valid_checks(p) for p in checks)


def audit_governance(branch: dict, rulesets: list[dict]) -> int:
    """Return matching active ruleset ID; no implication of tested enforcement."""
    if not isinstance(branch, dict) or branch.get("name") != "main" or branch.get("protected") is not True:
        raise GovernanceAuditError("main branch protection is not confirmed")
    if not isinstance(rulesets, list):
        raise GovernanceAuditError("ruleset listing is not available")
    for item in rulesets:
        if not _active_main_ruleset(item) or not _has_required_rules(item):
            continue
        ruleset_id = item.get("id")
        if type(ruleset_id) is int and ruleset_id > 0:
            return ruleset_id
    raise GovernanceAuditError("no enforceable main ruleset matching the V-01 minimum policy")


def _get_json(url: str, token: str):
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shuddho-v01-main-governance-audit",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, ValueError, OSError) as exc:
        code = getattr(exc, "code", "unavailable")
        raise GovernanceAuditError(f"GitHub governance data unavailable (status={code})") from exc


def inspect_repository(repository: str, token: str) -> int:
    if (
        not isinstance(repository, str)
        or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None
        or any(part in {".", ".."} for part in repository.split("/"))
        or not isinstance(token, str)
        or not token
    ):
        raise GovernanceAuditError("invalid repository or missing GitHub token")

    root = f"https://api.github.com/repos/{repository}"
    branch = _get_json(root + "/branches/main", token)
    items = _get_json(root + "/rulesets?includes_parents=true&per_page=100", token)
    if not isinstance(items, list) or len(items) >= 100:
        raise GovernanceAuditError("ruleset listing invalid or possibly truncated")
    details = []
    for item in items:
        if not isinstance(item, dict):
            raise GovernanceAuditError("malformed ruleset listing")
        if item.get("target") != "branch" or item.get("enforcement") != "active":
            continue
        rid = item.get("id")
        if type(rid) is not int or rid < 1:
            raise GovernanceAuditError("invalid active ruleset identifier")
        details.append(_get_json(root + f"/rulesets/{rid}", token))
    return audit_governance(branch, details)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    try:
        matching_rule = inspect_repository(args.repository, os.environ.get("GITHUB_TOKEN", ""))
    except GovernanceAuditError as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        parser.exit(1, "V-01 governance configuration audit failed; main is not release-qualified.\n")
    print(json.dumps({
        "status": "configuration_candidate",
        "ruleset_id": matching_rule,
        "qualified": False,
        "required_next": "Owner-admin negative-control and positive-control native merge tests",
    }))


if __name__ == "__main__":
    main()
