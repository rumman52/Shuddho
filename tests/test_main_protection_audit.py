"""V-01 defense in depth: detect absent main branch governance on every push.

These are *configuration-read* assertions, not proof that the GitHub merge
button blocks an unreviewed or pending-check PR. Owner-run negative controls
remain necessary before V-01 can be closed.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.main_protection_audit import GovernanceAuditError, audit_governance, inspect_repository


CHECKS = {"coworker", "test-and-build", "ci-merge-gate"}


def protected_branch() -> dict:
    return {"name": "main", "protected": True}


def approved_ruleset() -> dict:
    return {
        "id": 123,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews_on_push": True,
                    "require_last_push_approval": True,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": name, "integration_id": 15368} for name in sorted(CHECKS)
                    ],
                },
            },
        ],
    }


def test_exact_main_ruleset_with_independent_review_and_three_checks_is_candidate():
    assert audit_governance(protected_branch(), [approved_ruleset()]) == 123


def test_missing_branch_protection_and_missing_rules_are_rejected():
    with pytest.raises(GovernanceAuditError, match="branch protection"):
        audit_governance({"name": "main", "protected": False}, [approved_ruleset()])
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [])


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda x: x.update(enforcement="disabled"), "ruleset"),
        (lambda x: x.update(target="tag"), "ruleset"),
        (lambda x: x["conditions"]["ref_name"].update(include=["refs/heads/dev"]), "ruleset"),
        (lambda x: x["conditions"]["ref_name"].update(exclude=["refs/heads/main"]), "ruleset"),
        (lambda x: x["conditions"]["ref_name"].update(exclude=["refs/heads/ma*"]), "ruleset"),
        (lambda x: x["conditions"]["ref_name"].update(exclude=["refs/heads/other"]), "ruleset"),
        (lambda x: x.update(bypass_actors=[{"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}]), "ruleset"),
        (lambda x: x["rules"][2]["parameters"].update(required_approving_review_count=0), "ruleset"),
        (lambda x: x["rules"][2]["parameters"].update(dismiss_stale_reviews_on_push=False), "ruleset"),
        (lambda x: x["rules"][2]["parameters"].update(require_last_push_approval=False), "ruleset"),
        (lambda x: x["rules"][2]["parameters"].update(required_review_thread_resolution=False), "ruleset"),
        (lambda x: x["rules"][3]["parameters"].update(strict_required_status_checks_policy=False), "ruleset"),
        (lambda x: x["rules"][3]["parameters"]["required_status_checks"].pop(), "ruleset"),
        (lambda x: x["rules"].pop(0), "ruleset"),
        (lambda x: x["rules"].pop(1), "ruleset"),
    ],
)
def test_incomplete_or_bypassable_ruleset_does_not_count(mutate, reason):
    rule = approved_ruleset()
    mutate(rule)
    with pytest.raises(GovernanceAuditError, match=reason):
        audit_governance(protected_branch(), [rule])



@pytest.mark.parametrize("source", [None, -1, True, "15368", 15369])
def test_required_checks_must_be_pinned_to_trusted_github_actions_source(source):
    rule = approved_ruleset()
    rule["rules"][3]["parameters"]["required_status_checks"][0]["integration_id"] = source
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


def test_duplicate_required_check_with_untrusted_source_must_fail():
    rule = approved_ruleset()
    checks = rule["rules"][3]["parameters"]["required_status_checks"]
    checks.append({"context": "coworker", "integration_id": 98765})
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


def test_irrelevant_inactive_ruleset_does_not_override_valid_protection():
    inactive = deepcopy(approved_ruleset())
    inactive["enforcement"] = "disabled"
    assert audit_governance(protected_branch(), [inactive, approved_ruleset()]) == 123


def test_bool_instead_of_integer_approval_count_is_rejected():
    rule = approved_ruleset()
    rule["rules"][2]["parameters"]["required_approving_review_count"] = True
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


def test_repository_inspection_reads_actual_ruleset_detail_and_branch(monkeypatch):
    from scripts import main_protection_audit as mod

    calls: list[str] = []

    def fake_get_json(url, token):
        assert token == "ci-token"
        calls.append(url)
        if url.endswith("/branches/main"):
            return protected_branch()
        if url.endswith("/rulesets?includes_parents=true&per_page=100"):
            return [{"id": 123, "target": "branch", "enforcement": "active"}]
        if url.endswith("/rulesets/123"):
            return approved_ruleset()
        raise AssertionError(f"unexpected API request: {url}")

    monkeypatch.setattr(mod, "_get_json", fake_get_json)
    assert inspect_repository("owner/repo", "ci-token") == 123
    assert len(calls) == 3


def test_bad_repo_identifiers_are_rejected_before_fetch(monkeypatch):
    from scripts import main_protection_audit as mod

    def never_call(*args):
        raise AssertionError("no outbound calls expected")

    monkeypatch.setattr(mod, "_get_json", never_call)
    for name in ("", "owner", "owner/repo/more", "../repo", "owner/répo"):
        with pytest.raises(GovernanceAuditError):
            inspect_repository(name, "ci-token")


def test_ci_main_push_audit_is_not_a_substitute_for_pr_gate():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  governance-audit:\n", 1)[1]
    assert "github.event_name == 'push'" in job
    assert "python -m scripts.main_protection_audit" in job
    assert "GITHUB_TOKEN: ${{ github.token }}" in job
    assert "continue-on-error" not in job
    assert "ci-merge-gate:" in workflow
