"""Safely apply the reviewed V-01 main ruleset with explicit admin intent.

This is an operator tool, not an automated CI mutation. Dry-run is the default.
A successful read-back confirms configuration only; an administrator must still
prove invalid merges are blocked with controlled negative and positive tests.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.main_protection_audit import (
    GovernanceAuditError,
    _active_main_ruleset,
    _has_required_rules,
    audit_governance,
)

EXPECTED_REPOSITORY = "rumman52/Shuddho"
EXPECTED_POLICY_NAME = "Shuddho main review and CI"
API_ROOT = "https://api.github.com"
POLICY_PATH = Path(__file__).resolve().parents[1] / "infra" / "github" / "main-ruleset.json"


class ApplyMainRulesetError(ValueError):
    """Unsafe, ambiguous, or unverified ruleset operation."""


class _NoCredentialRedirect(HTTPRedirectHandler):
    """Never forward an administrator bearer token through an HTTP redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request_json(method: str, url: str, token: str, payload: dict | None = None):
    """Make a bounded GitHub JSON request without following redirects."""
    if method not in {"GET", "POST"}:
        raise ApplyMainRulesetError("unsupported GitHub API method")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ApplyMainRulesetError("GitHub API URL has an invalid port") from exc
    trusted_github = parsed.scheme == "https" and parsed.hostname == "api.github.com" and port in (None, 443)
    loopback_test = (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.username is None
        and parsed.password is None
    )
    if not (trusted_github or loopback_test) or parsed.username is not None or parsed.password is not None:
        raise ApplyMainRulesetError("GitHub API request must use the trusted GitHub origin")
    if not isinstance(token, str) or not token.strip():
        raise ApplyMainRulesetError("missing GitHub token")

    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shuddho-v01-ruleset-operator",
    }
    if payload is not None:
        if method != "POST" or not isinstance(payload, dict):
            raise ApplyMainRulesetError("invalid GitHub API payload")
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with build_opener(_NoCredentialRedirect()).open(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, ValueError, OSError) as exc:
        status = getattr(exc, "code", "unavailable")
        if method == "POST" and status == 403:
            detail = "; verify the token has repository Administration: write permission"
        else:
            detail = ""
        raise ApplyMainRulesetError(f"GitHub ruleset API unavailable (status={status}){detail}") from exc


def _validate_candidate(policy: object) -> dict:
    if not isinstance(policy, dict):
        raise ApplyMainRulesetError("V-01 policy must be a JSON object")
    if policy.get("name") != EXPECTED_POLICY_NAME:
        raise ApplyMainRulesetError(f"V-01 policy name must be {EXPECTED_POLICY_NAME!r}")
    if "id" in policy:
        raise ApplyMainRulesetError("policy template must not contain a server-assigned ruleset id")
    rules = policy.get("rules")
    if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
        raise ApplyMainRulesetError("V-01 policy rules are malformed")
    types = [rule.get("type") for rule in rules]
    if len(types) != len(set(types)):
        raise ApplyMainRulesetError("V-01 policy must not contain duplicate rule types")
    if (
        not _active_main_ruleset(policy)
        or not _has_required_rules(policy)
        or policy.get("bypass_actors") != []
    ):
        raise ApplyMainRulesetError("candidate policy does not satisfy V-01 required checks, independent review, and no-bypass rules")
    check_rules = [rule for rule in rules if rule.get("type") == "required_status_checks"]
    check_parameters = check_rules[0].get("parameters") if len(check_rules) == 1 else None
    if not isinstance(check_parameters, dict) or check_parameters.get("do_not_enforce_on_create") is not False:
        raise ApplyMainRulesetError("candidate policy must enforce required checks on newly created refs")
    return policy


def _pattern_matches_main(pattern: object) -> bool:
    if not isinstance(pattern, str):
        return True
    if pattern in {"~ALL", "~DEFAULT_BRANCH"}:
        return True
    return fnmatch.fnmatchcase("refs/heads/main", pattern)


def _could_target_main(rule: object) -> bool:
    """Conservatively identify active rulesets that may already affect main."""
    if not isinstance(rule, dict):
        return True
    if rule.get("target") != "branch" or rule.get("enforcement") != "active":
        return False
    conditions = rule.get("conditions")
    refs = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(refs, dict):
        return True
    includes, excludes = refs.get("include"), refs.get("exclude")
    if not isinstance(includes, list) or not includes or not isinstance(excludes, list):
        return True
    if not any(_pattern_matches_main(item) for item in includes):
        return False
    if any(not isinstance(item, str) for item in excludes):
        return True
    if any(_pattern_matches_main(item) for item in excludes):
        return False
    return True


def _list_main_target_rulesets(root: str, token: str, listed: object) -> list[dict]:
    """Resolve list summaries to detail before deciding whether they target main."""
    if not isinstance(listed, list) or len(listed) >= 100:
        raise ApplyMainRulesetError("ruleset listing is invalid or possibly truncated")
    details = []
    for item in listed:
        if not isinstance(item, dict):
            raise ApplyMainRulesetError("ruleset listing contains a malformed entry")
        # List responses may omit conditions. Treat unknown scope conservatively,
        # then use the detail response as the source of truth for applicability.
        if not _could_target_main(item):
            continue
        ruleset_id = item.get("id")
        if type(ruleset_id) is not int or ruleset_id < 1:
            raise ApplyMainRulesetError("an active ruleset may target main but has no valid identifier")
        detail = _request_json("GET", root + f"/rulesets/{ruleset_id}", token)
        if not isinstance(detail, dict) or detail.get("id") != ruleset_id:
            raise ApplyMainRulesetError(f"ruleset {ruleset_id} detail could not be verified")
        if _could_target_main(detail):
            details.append(detail)
    return details


def _is_compliant_existing(rule: object) -> bool:
    if not isinstance(rule, dict):
        return False
    rules = rule.get("rules")
    if not isinstance(rules, list) or any(not isinstance(item, dict) for item in rules):
        return False
    types = [item.get("type") for item in rules]
    if len(types) != len(set(types)):
        return False
    check_rules = [item for item in rules if item.get("type") == "required_status_checks"]
    check_parameters = check_rules[0].get("parameters") if len(check_rules) == 1 else None
    return (
        _active_main_ruleset(rule)
        and _has_required_rules(rule)
        and rule.get("bypass_actors") == []
        and isinstance(check_parameters, dict)
        and check_parameters.get("do_not_enforce_on_create") is False
    )


def _verify_applied_state(
    root: str,
    token: str,
    *,
    expected_id: int | None = None,
    expected_name: str | None = None,
) -> dict:
    """Read back the unique effective main policy after a potentially mutating POST."""
    listed = _request_json("GET", root + "/rulesets?includes_parents=true&per_page=100", token)
    main_rulesets = _list_main_target_rulesets(root, token, listed)
    if len(main_rulesets) != 1:
        raise ApplyMainRulesetError("effective main ruleset list is missing or ambiguous")
    readback = main_rulesets[0]
    ruleset_id = readback.get("id")
    if expected_id is not None and ruleset_id != expected_id:
        raise ApplyMainRulesetError("read-back ruleset id differs from the created id")
    if expected_name is not None and readback.get("name") != expected_name:
        raise ApplyMainRulesetError("read-back ruleset name differs from the requested policy")
    branch_after = _request_json("GET", root + "/branches/main", token)
    try:
        matched_id = audit_governance(branch_after, [readback])
    except GovernanceAuditError as exc:
        raise ApplyMainRulesetError(f"main branch or ruleset did not pass the read-only audit: {exc}") from exc
    if matched_id != ruleset_id or not _is_compliant_existing(readback):
        raise ApplyMainRulesetError("read-back policy does not satisfy the V-01 contract")
    return readback


def apply_main_ruleset(
    repository: str,
    token: str,
    policy: object,
    *,
    apply: bool,
    confirm_repository: str | None = None,
) -> dict:
    """Plan or explicitly apply V-01. Never replaces an existing policy."""
    if repository != EXPECTED_REPOSITORY:
        raise ApplyMainRulesetError(f"this operator only supports {EXPECTED_REPOSITORY}")
    if not isinstance(token, str) or not token.strip():
        raise ApplyMainRulesetError("missing GitHub token")
    candidate = _validate_candidate(policy)
    if apply and confirm_repository != repository:
        raise ApplyMainRulesetError("applying requires explicit --confirm-repository matching the target repository")

    root = f"{API_ROOT}/repos/{repository}"
    branch = _request_json("GET", root + "/branches/main", token)
    if not isinstance(branch, dict) or branch.get("name") != "main" or type(branch.get("protected")) is not bool:
        raise ApplyMainRulesetError("main branch protection state is malformed or unavailable")
    listed = _request_json("GET", root + "/rulesets?includes_parents=true&per_page=100", token)
    if not isinstance(listed, list) or len(listed) >= 100:
        raise ApplyMainRulesetError("ruleset listing is invalid or possibly truncated")
    same_name = [item for item in listed if isinstance(item, dict) and item.get("name") == candidate["name"]]
    if any(not isinstance(item, dict) for item in listed):
        raise ApplyMainRulesetError("ruleset listing contains a malformed entry")
    main_rulesets = _list_main_target_rulesets(root, token, listed)

    if len(main_rulesets) > 1:
        raise ApplyMainRulesetError("multiple active rulesets may target main; manual policy reconciliation is required")
    if main_rulesets:
        existing = main_rulesets[0]
        if branch["protected"] is True and _is_compliant_existing(existing):
            try:
                matched_id = audit_governance(branch, [existing])
            except GovernanceAuditError as exc:
                raise ApplyMainRulesetError(f"existing main ruleset failed read-only audit: {exc}") from exc
            return {
                "status": "already_configured",
                "ruleset_id": matched_id,
                "configuration_readback_verified": True,
                "merge_enforcement_verified": False,
                "qualified": False,
                "required_next": "administrator-run negative and positive merge-control tests",
            }
        raise ApplyMainRulesetError(
            "an active ruleset may already target main but is not fully verified; refusing to create or replace policy"
        )
    if same_name:
        raise ApplyMainRulesetError(
            "a ruleset with the desired name exists but is not a verified active main policy; manual reconciliation is required"
        )
    if branch["protected"] is True:
        raise ApplyMainRulesetError(
            "main already reports protection but no compliant active ruleset was verified; inspect legacy and inherited policy manually"
        )

    if not apply:
        return {
            "status": "dry_run",
            "repository": repository,
            "would_create": True,
            "policy_name": candidate["name"],
            "configuration_readback_verified": False,
            "merge_enforcement_verified": False,
            "qualified": False,
            "required_next": "review this plan; use --apply and --confirm-repository only with an authorized administrator token",
        }

    try:
        created = _request_json("POST", root + "/rulesets", token, candidate)
    except ApplyMainRulesetError as post_error:
        # POST has no idempotency key. The server may have committed even if
        # its response was lost, so reconcile by reading state before telling
        # the operator anything that could trigger a duplicate create.
        try:
            recovered = _verify_applied_state(root, token, expected_name=candidate["name"])
        except ApplyMainRulesetError as verify_error:
            raise ApplyMainRulesetError(
                f"ruleset POST outcome is uncertain ({post_error}); read-back did not prove success "
                f"({verify_error}); do not retry blindly, inspect repository settings first"
            ) from post_error
        return {
            "status": "post_response_uncertain_but_readback_verified",
            "ruleset_id": recovered["id"],
            "configuration_readback_verified": True,
            "merge_enforcement_verified": False,
            "qualified": False,
            "recovered_after_uncertain_post": True,
            "required_next": "administrator-run negative and positive merge-control tests; preserve rule id and observation time",
        }

    ruleset_id = created.get("id") if isinstance(created, dict) else None
    if type(ruleset_id) is not int or ruleset_id < 1:
        try:
            recovered = _verify_applied_state(root, token, expected_name=candidate["name"])
        except ApplyMainRulesetError as verify_error:
            raise ApplyMainRulesetError(
                f"ruleset POST returned no valid id; outcome is uncertain ({verify_error}); "
                "do not retry blindly, inspect repository settings first"
            ) from verify_error
        return {
            "status": "post_response_uncertain_but_readback_verified",
            "ruleset_id": recovered["id"],
            "configuration_readback_verified": True,
            "merge_enforcement_verified": False,
            "qualified": False,
            "recovered_after_uncertain_post": True,
            "required_next": "administrator-run negative and positive merge-control tests; preserve rule id and observation time",
        }

    try:
        readback = _verify_applied_state(root, token, expected_id=ruleset_id, expected_name=candidate["name"])
    except ApplyMainRulesetError as exc:
        raise ApplyMainRulesetError(
            f"ruleset {ruleset_id} was created but read-back verification failed: {exc}; "
            "do not retry blindly, inspect it first"
        ) from exc

    return {
        "status": "configuration_applied_readback_verified",
        "ruleset_id": ruleset_id,
        "configuration_readback_verified": True,
        "merge_enforcement_verified": False,
        "qualified": False,
        "required_next": "administrator-run negative and positive merge-control tests; preserve rule id and observation time",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=EXPECTED_REPOSITORY)
    parser.add_argument("--apply", action="store_true", help="create the ruleset; dry-run is the default")
    parser.add_argument("--confirm-repository", help="must exactly match --repository when --apply is supplied")
    args = parser.parse_args(argv)
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        result = apply_main_ruleset(
            args.repository,
            os.environ.get("GITHUB_TOKEN", ""),
            policy,
            apply=args.apply,
            confirm_repository=args.confirm_repository,
        )
    except (OSError, json.JSONDecodeError, ApplyMainRulesetError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
