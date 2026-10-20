"""Read-only V-01 GitHub branch policy diagnostic; NOT merge authorization.

An administrator can collect evidence with:
  gh api repos/OWNER/REPO/branches/main/protection > /tmp/protection.json
  gh api 'repos/OWNER/REPO/rulesets?includes_parents=true' > /tmp/rulesets.json
  gh api repos/OWNER/REPO/rulesets/ID > /tmp/ruleset-ID.json

Run:
  python -m scripts.v01_native_protection_audit \
    --branch-protection-json /tmp/protection.json \
    --rulesets-json /tmp/rulesets.json \
    --ruleset-detail-json /tmp/ruleset-ID.json

Or:
  GITHUB_TOKEN=<admin-read-token> python -m scripts.v01_native_protection_audit \
    --live-repository OWNER/REPO

Configuration evidence is never proof of effective enforced settings.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REQUIRED_JOBS = frozenset({'test-and-build', 'coworker', 'ci-merge-gate'})
REPO_PATTERN = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
BRANCH = 'main'


def _enabled(value: object) -> bool:
    return isinstance(value, dict) and value.get('enabled') is True


def _review_fields(review: object, *, ruleset: bool) -> list[str]:
    if not isinstance(review, dict):
        return ['independent_review_not_required']
    issues = []
    if type(review.get('required_approving_review_count')) is not int or review['required_approving_review_count'] < 1:
        issues.append('independent_review_not_required')
    dismiss_key = 'dismiss_stale_reviews_on_push' if ruleset else 'dismiss_stale_reviews'
    if review.get(dismiss_key) is not True:
        issues.append('stale_reviews_not_dismissed')
    if review.get('require_last_push_approval') is not True:
        issues.append('last_push_review_not_required')
    if ruleset:
        if review.get('required_review_thread_resolution') is not True:
            issues.append('review_threads_not_required_resolved')
    else:
        allowances = review.get('bypass_pull_request_allowances')
        if allowances is not None and (
            not isinstance(allowances, dict)
            or any(allowances.get(k) for k in ('users', 'teams', 'apps'))
        ):
            issues.append('review_bypass_allowances_present')
    return issues


def _missing_status_checks(policy: object, *, ruleset: bool) -> list[str]:
    issues = []
    if not isinstance(policy, dict):
        return ['required_status_checks_missing']
    strict_key = 'strict_required_status_checks_policy' if ruleset else 'strict'
    if policy.get(strict_key) is not True:
        issues.append('strict_required_checks_missing')
    if ruleset:
        checks = policy.get('required_status_checks')
        contexts = [c.get('context') for c in checks if isinstance(c, dict)] if isinstance(checks, list) else []
    else:
        contexts = policy.get('contexts', [])
        checks = policy.get('checks', [])
        contexts = (contexts if isinstance(contexts, list) else []) + ([c.get('context') for c in checks if isinstance(c, dict)] if isinstance(checks, list) else [])
    missing = sorted(REQUIRED_JOBS - {s for s in contexts if isinstance(s, str)})
    issues.extend(f'missing_required_checks:{name}' for name in missing)
    return issues


def _branch_protection_findings(protection: object) -> list[str]:
    if not isinstance(protection, dict) or protection.get('message'):
        return ['native_branch_protection_unreadable']
    issues = _missing_status_checks(protection.get('required_status_checks'), ruleset=False)
    issues.extend(_review_fields(protection.get('required_pull_request_reviews'), ruleset=False))
    if not _enabled(protection.get('required_conversation_resolution')):
        issues.append('review_threads_not_required_resolved')
    if not _enabled(protection.get('enforce_admins')):
        issues.append('admin_bypass_not_disabled')
    if not isinstance(protection.get('allow_force_pushes'), dict) or protection['allow_force_pushes'].get('enabled') is not False:
        issues.append('force_push_status_not_proven_disabled')
    if not isinstance(protection.get('allow_deletions'), dict) or protection['allow_deletions'].get('enabled') is not False:
        issues.append('deletion_status_not_proven_disabled')
    return issues


def _ruleset_findings(ruleset: object, branch: str) -> list[str]:
    if not isinstance(ruleset, dict):
        return ['malformed_ruleset']
    issues = []
    if ruleset.get('enforcement') != 'active' or ruleset.get('target') != 'branch':
        issues.append('ruleset_not_active_branch')
    conditions = ruleset.get('conditions')
    ref = conditions.get('ref_name') if isinstance(conditions, dict) else None
    include = ref.get('include') if isinstance(ref, dict) else None
    exclude = ref.get('exclude') if isinstance(ref, dict) else None
    # Conservative: wildcard and inherited-condition semantics require
    # effective-rule inspection and are not proven by this local checker.
    target = f'refs/heads/{branch}'
    if not isinstance(include, list) or target not in include or not isinstance(exclude, list) or exclude:
        issues.append('main_branch_applicability_not_proven')
    bypass = ruleset.get('bypass_actors')
    if not isinstance(bypass, list) or bypass:
        issues.append('ruleset_bypass_not_proven_absent')
    rules = ruleset.get('rules')
    if not isinstance(rules, list):
        return issues + ['ruleset_rules_unreadable']
    grouped = {}
    for item in rules:
        if not isinstance(item, dict) or not isinstance(item.get('type'), str) or item['type'] in grouped:
            return issues + ['malformed_or_duplicate_rules']
        grouped[item['type']] = item.get('parameters', {})
    issues.extend(_review_fields(grouped.get('pull_request'), ruleset=True))
    issues.extend(_missing_status_checks(grouped.get('required_status_checks'), ruleset=True))
    for rule in ('non_fast_forward', 'deletion'):
        if rule not in grouped:
            issues.append(f'missing_ruleset_rule:{rule}')
    return issues


def assess_native_policy(*, branch_protection: object = None, rulesets: object = None, branch: str = BRANCH) -> dict:
    """Classify configuration evidence, NEVER live enforcement."""
    candidates = []
    findings = []
    if branch_protection is not None:
        problems = _branch_protection_findings(branch_protection)
        if not problems:
            candidates.append('branch_protection')
        else:
            findings.extend(problems)
    if rulesets is not None:
        if not isinstance(rulesets, list):
            findings.append('rulesets_unreadable')
        elif not rulesets:
            findings.append('no_active_rulesets_supplied')
        else:
            for rule in rulesets:
                problems = _ruleset_findings(rule, branch)
                if not problems:
                    candidates.append('active_ruleset')
                else:
                    findings.extend(problems)
    if branch_protection is None and rulesets is None:
        findings.append('no_readable_native_policy')
    candidate = candidates[0] if candidates else None
    return {
        'classification': 'configuration_candidate' if candidate else 'blocked',
        'candidate_source': candidate,
        'branch': branch,
        'findings': sorted(set(findings)) if not candidate else [],
        'enforcement_verified': False,
        'remaining_gates': ['independent_negative_control_required',
                            'administrator_effective_permissions_required',
                            'unreviewed_or_failed_ci_merges_must_be_blocked'],
        'warning': 'Read-only settings inspection is not a live merge lock or production release authorization.',
    }


def _fetch_json(url: str, token: str) -> object:
    req = Request(url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'shuddho-v01-native-policy-readonly',
    })
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def _live_evidence(repository: str, token: str) -> tuple[object, object]:
    if not REPO_PATTERN.fullmatch(repository):
        raise ValueError('invalid repository selector')
    if not token:
        raise ValueError('GITHUB_TOKEN unavailable')
    base = f'https://api.github.com/repos/{repository}'
    protection = None
    rulesets = None
    try:
        protection = _fetch_json(f'{base}/branches/{BRANCH}/protection', token)
    except (HTTPError, URLError, OSError, ValueError):
        pass
    try:
        listings = _fetch_json(f'{base}/rulesets?includes_parents=true', token)
        if isinstance(listings, list):
            rulesets = []
            for listing in listings:
                if not isinstance(listing, dict) or type(listing.get('id')) is not int:
                    raise ValueError('malformed ruleset listing')
                rulesets.append(_fetch_json(f"{base}/rulesets/{listing['id']}", token))
    except (HTTPError, URLError, OSError, ValueError):
        rulesets = None
    return protection, rulesets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--branch-protection-json', type=Path)
    parser.add_argument('--rulesets-json', type=Path)
    parser.add_argument('--ruleset-detail-json', action='append', type=Path, default=[])
    parser.add_argument('--live-repository')
    args = parser.parse_args()
    try:
        if args.live_repository:
            if args.branch_protection_json or args.rulesets_json or args.ruleset_detail_json:
                raise ValueError('do not combine live and saved evidence')
            protection, rulesets = _live_evidence(args.live_repository, os.environ.get('GITHUB_TOKEN', ''))
        else:
            protection = json.loads(args.branch_protection_json.read_text()) if args.branch_protection_json else None
            rulesets = json.loads(args.rulesets_json.read_text()) if args.rulesets_json else None
            details = [json.loads(path.read_text()) for path in args.ruleset_detail_json]
            if details:
                rulesets = details
        result = assess_native_policy(branch_protection=protection, rulesets=rulesets)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Never include exception values: paths, tokens or URLs might be untrusted.
        result = assess_native_policy()
        result['findings'] = ['evidence_read_or_validation_failed']
    print(json.dumps(result, sort_keys=True, indent=2))
    raise SystemExit(0 if result['classification'] == 'configuration_candidate' else 2)


if __name__ == '__main__':
    main()
