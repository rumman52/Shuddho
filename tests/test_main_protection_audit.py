"""V-01 defense in depth: detect absent main branch governance on every push.

These are *configuration-read* assertions, not proof that the GitHub merge
button blocks an unreviewed or pending-check PR. Owner-run negative controls
remain necessary before V-01 can be closed.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess
import textwrap

import pytest

from scripts.main_protection_audit import GovernanceAuditError, audit_governance, inspect_repository


CHECKS = {"test-and-build", "coworker", "ci-merge-gate"}


def protected_branch() -> dict:
    return {"name": "main", "protected": True}


def approved_ruleset() -> dict:
    return {
        "id": 123,
        "source": "rumman52/Shuddho",
        "source_type": "Repository",
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
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": name, "integration_id": 15368} for name in sorted(CHECKS)
                    ],
                },
            },
        ],
    }


def test_exact_main_ruleset_with_independent_review_and_two_checks_is_candidate():
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
    checks.append({"context": "test-and-build", "integration_id": 98765})
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


@pytest.mark.parametrize(
    "rule_type",
    ["pull_request", "required_status_checks", "deletion", "non_fast_forward"],
)
def test_duplicate_ruleset_type_cannot_mask_a_weaker_policy(rule_type):
    rule = approved_ruleset()
    duplicate = deepcopy(next(row for row in rule["rules"] if row["type"] == rule_type))
    if rule_type == "pull_request":
        duplicate["parameters"]["required_approving_review_count"] = 0
    if rule_type == "required_status_checks":
        duplicate["parameters"]["strict_required_status_checks_policy"] = False
    rule["rules"].append(duplicate)
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


@pytest.mark.parametrize("malformed", [None, {}, {"type": None}, {"type": 7}])
def test_malformed_ruleset_entries_fail_closed(malformed):
    rule = approved_ruleset()
    rule["rules"].append(malformed)
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


def test_redacted_bypass_actors_fails_closed_with_actionable_reason():
    # GitHub's documented GET response withholds bypass_actors when the
    # caller lacks ruleset write access; missing does not prove an empty list.
    rule = approved_ruleset()
    del rule["bypass_actors"]
    with pytest.raises(GovernanceAuditError, match="redacted bypass_actors"):
        audit_governance(protected_branch(), [rule])


def test_null_bypass_actors_is_not_trusted_as_empty():
    rule = approved_ruleset()
    rule["bypass_actors"] = None
    with pytest.raises(GovernanceAuditError, match="redacted bypass_actors"):
        audit_governance(protected_branch(), [rule])


def test_a_separate_fully_inspectable_ruleset_can_qualify_even_if_another_is_redacted():
    redacted = approved_ruleset()
    del redacted["bypass_actors"]
    assert audit_governance(protected_branch(), [redacted, approved_ruleset()]) == 123


def test_visible_bypass_actor_is_never_accepted_as_no_bypass():
    rule = approved_ruleset()
    rule["bypass_actors"] = [
        {"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    ]
    with pytest.raises(GovernanceAuditError, match="no enforceable main ruleset"):
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
            # The full GitHub detail must identify the requested REST repository.
            snapshot = approved_ruleset()
            snapshot["source"] = "owner/repo"
            return snapshot
        raise AssertionError(f"unexpected API request: {url}")

    monkeypatch.setattr(mod, "_get_json", fake_get_json)
    assert inspect_repository("owner/repo", "ci-token") == 123
    assert len(calls) == 3


def test_installation_token_reads_branch_and_ruleset_details(monkeypatch):
    from scripts import main_protection_audit as mod

    rule = approved_ruleset()
    rule["source"] = "owner/repo"

    def fake_get_json(url, token):
        if url.endswith("/branches/main"):
            assert token == "installation-token"
            return protected_branch()
        if url.endswith("/rulesets/123"):
            assert token == "installation-token"
            return rule
        assert token == "workflow-token"
        assert url.endswith("/rulesets?includes_parents=true&per_page=100")
        return [{"id": 123, "target": "branch", "enforcement": "active"}]

    monkeypatch.setattr(mod, "_get_json", fake_get_json)
    assert inspect_repository("owner/repo", "workflow-token", ruleset_token="installation-token") == 123
    del rule["bypass_actors"]
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        inspect_repository("owner/repo", "workflow-token", ruleset_token="installation-token")
    with pytest.raises(GovernanceAuditError, match="token"):
        inspect_repository("owner/repo", "workflow-token", ruleset_token="")


def test_bad_repo_identifiers_are_rejected_before_fetch(monkeypatch):
    from scripts import main_protection_audit as mod

    def never_call(*args):
        raise AssertionError("no outbound calls expected")

    monkeypatch.setattr(mod, "_get_json", never_call)
    for name in ("", "owner", "owner/repo/more", "../repo", "owner/répo"):
        with pytest.raises(GovernanceAuditError):
            inspect_repository(name, "ci-token")


def test_day1_baseline_trio_runs_in_one_existing_fail_closed_coworker_gate():
    """Preserve the workbook's exact baseline without duplicating Fly tests."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step_name = "      - name: Verify Fly repository coding contracts without skips"
    assert workflow.count(step_name) == 1
    gate = workflow.split(step_name, 1)[1].split("\n      - name:", 1)[0]
    assert gate.count("uv run --extra coworker pytest ") == 1
    for selector in (
        "tests/test_coworker.py::test_provider_capacity_settings_fail_closed",
        "tests/test_sandbox_control_plane.py::test_sandbox_worker_command_is_networkless_minimal_and_fail_closed",
        "tests/test_fly_repository_coding.py",
    ):
        assert selector in gate
    assert "-q -rs --junitxml=/tmp/fly-repository-coding.xml" in gate
    for module in ("tests.test_coworker", "tests.test_sandbox_control_plane", "tests.test_fly_repository_coding"):
        assert f"scripts.mandatory_test_gate /tmp/fly-repository-coding.xml --required-module {module}" in gate
    assert "continue-on-error" not in gate


def test_main_push_gate_depends_on_governance_without_privileged_pr_access():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  governance-audit:\n", 1)[1]
    assert "github.event_name == 'push'" in job
    assert "github.repository == 'rumman52/Shuddho'" in job
    assert "github.ref == 'refs/heads/main'" in job
    assert "environment: v01-governance" in job
    assert "persist-credentials: false" in job
    assert "uses: ./.github/actions/audit-main-ruleset" in job
    assert "secrets.V01_RULESET_APP_PRIVATE_KEY" in job
    assert "V01_RULESET_APP_" not in workflow.split("\n  governance-audit:\n", 1)[0]
    provision = Path(".github/workflows/provision-pa10-staging-worker.yml").read_text(encoding="utf-8")
    source_gate = provision.split("\n  source_gate:\n", 1)[1].split("\n  ruleset_audit:\n", 1)[0]
    # The PA-10 source gate runs BEFORE any protected-environment approval.
    # Keep it secret-free; a successful privileged main CI audit must be
    # established separately before staging credential access can be unlocked.
    assert "GITHUB_TOKEN: ${{ github.token }}" in source_gate
    assert "secrets." not in source_gate
    assert "github.ref == 'refs/heads/main'" in source_gate
    assert "inputs.confirm == 'PROVISION'" in source_gate
    assert "continue-on-error" not in job
    gate = workflow.split("\n  ci-merge-gate:\n", 1)[1].split("\n  governance-audit:\n", 1)[0]
    assert "    if: always()" in gate
    needs = gate.split("    needs:\n", 1)[1].split("    runs-on:", 1)[0]
    assert "      - frontend\n" in needs
    assert "      - browser-qualification\n" in needs
    assert "      - postgres-18-qualification\n" in needs
    assert "      - governance-audit\n" in needs
    assert "      - pr-base-ancestry\n" in needs
    assert "FRONTEND_RESULT: ${{ needs.frontend.result }}" in gate
    assert "BROWSER_QUALIFICATION_RESULT: ${{ needs['browser-qualification'].result }}" in gate
    assert "POSTGRES18_RESULT: ${{ needs['postgres-18-qualification'].result }}" in gate
    assert "GOVERNANCE_AUDIT_RESULT: ${{ needs.governance-audit.result }}" in gate
    assert "PR_ANCESTRY_RESULT: ${{ needs[\'pr-base-ancestry\'].result }}" in gate
    assert "continue-on-error" not in gate
    assert "python -m scripts.independent_review_gate" in gate


def test_ruleset_audit_action_scopes_credential_to_one_repo_and_rechecks_protection():
    action = Path(".github/actions/audit-main-ruleset/action.yml").read_text(encoding="utf-8")
    _, after_mint = action.split("    - name: Mint installation token", 1)
    mint, after_guard = after_mint.split("    - name: Confirm the checked-out revision is still protected main", 1)
    guard, audit = after_guard.split("    - name: Inspect active V-01 main governance", 1)
    mint = "    - name: Mint installation token" + mint
    guard = "    - name: Confirm the checked-out revision is still protected main" + guard
    assert "actions/create-github-app-token@1b10c78c7865c340bc4f6099eb2f838309f1e8c3" in mint
    assert "owner: rumman52" in mint and "repositories: Shuddho" in mint
    assert "permission-administration: write" in mint
    assert "permission-contents: read" in mint
    assert mint.count("permission-contents: read") == 1
    assert "skip-token-revoke" not in mint
    assert "inputs.private-key" not in guard + audit
    assert "scripts.pa10_main_head_guard" in guard
    assert "GITHUB_TOKEN: ${{ steps.installation.outputs.token }}" in guard
    assert "GITHUB_RULESET_AUDIT_TOKEN: ${{ steps.installation.outputs.token }}" in audit
    assert "python3 -m scripts.main_protection_audit" in audit


def _run_ci_result_gate(results: dict[str, str]) -> subprocess.CompletedProcess:
    """Execute the actual workflow shell, not a reimplementation of its policy."""
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = workflow.split("      - name: Require complete CI success\n", 1)[1]
    body = step.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", textwrap.dedent(body)],
        env={**os.environ, "CI_EVENT_NAME": "push", "POSTGRES18_RESULT": "success", "PR_ANCESTRY_RESULT": "success", **results}, text=True, capture_output=True, timeout=5,
    )


@pytest.mark.parametrize("upstream", ["TEST_AND_BUILD_RESULT", "FRONTEND_RESULT", "COWORKER_RESULT", "BROWSER_QUALIFICATION_RESULT", "POSTGRES18_RESULT", "GOVERNANCE_AUDIT_RESULT"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", ""])
def test_merge_gate_rejects_any_unsuccessful_required_job(upstream, result):
    results = {
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": "success",
        "COWORKER_RESULT": "success",
        "BROWSER_QUALIFICATION_RESULT": "success",
        "GOVERNANCE_AUDIT_RESULT": "success",
    }
    results[upstream] = result
    completed = _run_ci_result_gate(results)
    assert completed.returncode == 1, completed.stdout + completed.stderr


def test_merge_gate_accepts_all_required_jobs_succeeding():
    completed = _run_ci_result_gate({
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": "success",
        "COWORKER_RESULT": "success",
        "BROWSER_QUALIFICATION_RESULT": "success",
        "GOVERNANCE_AUDIT_RESULT": "success",
    })
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize(("event", "scope", "frontend", "backend", "expected"), [
    ("pull_request", "docs", "skipped", "skipped", 0),
    ("pull_request", "frontend", "success", "skipped", 0),
    ("pull_request", "frontend", "skipped", "skipped", 1),
    ("pull_request", "full", "success", "skipped", 1),
    ("pull_request", "frontend", "success", "failure", 1),
    ("pull_request", "invalid", "success", "success", 1),
    ("push", "docs", "success", "skipped", 1),
])
def test_ci_gate_requires_checks_for_the_actual_scope(event, scope, frontend, backend, expected):
    completed = _run_ci_result_gate({
        "CI_EVENT_NAME": event,
        "PR_CI_SCOPE": scope,
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": frontend,
        "BROWSER_QUALIFICATION_RESULT": frontend,
        "COWORKER_RESULT": backend,
        "POSTGRES18_RESULT": backend,
        "GOVERNANCE_AUDIT_RESULT": "success" if event == "push" else "skipped",
    })
    assert completed.returncode == expected, completed.stdout + completed.stderr


@pytest.mark.parametrize("event", ["pull_request", "pull_request_review"])
def test_pr_gate_preserves_expected_audit_skip_before_independent_review(event):
    completed = _run_ci_result_gate({
        "CI_EVENT_NAME": event,
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": "success",
        "COWORKER_RESULT": "success",
        "BROWSER_QUALIFICATION_RESULT": "success",
        "GOVERNANCE_AUDIT_RESULT": "skipped",
    })
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("event", ["pull_request", "pull_request_review"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", ""])
def test_pr_gate_rejects_unsuccessful_head_ancestry(event, result):
    completed = _run_ci_result_gate({
        "CI_EVENT_NAME": event,
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": "success",
        "COWORKER_RESULT": "success",
        "BROWSER_QUALIFICATION_RESULT": "success",
        "GOVERNANCE_AUDIT_RESULT": "skipped",
        "PR_ANCESTRY_RESULT": result,
    })
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "PR head does not include" in completed.stdout


@pytest.mark.parametrize("event", ["pull_request", "pull_request_review"])
@pytest.mark.parametrize("result", ["failure", "cancelled", ""])
def test_pr_gate_does_not_hide_unexpected_audit_result(event, result):
    completed = _run_ci_result_gate({
        "CI_EVENT_NAME": event,
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": "success",
        "COWORKER_RESULT": "success",
        "BROWSER_QUALIFICATION_RESULT": "success",
        "GOVERNANCE_AUDIT_RESULT": result,
    })
    assert completed.returncode == 1, completed.stdout + completed.stderr


@pytest.mark.parametrize("event", ["", "workflow_dispatch", "pull_request_target"])
def test_merge_gate_rejects_unreviewed_event_types(event):
    completed = _run_ci_result_gate({
        "CI_EVENT_NAME": event,
        "TEST_AND_BUILD_RESULT": "success",
        "FRONTEND_RESULT": "success",
        "COWORKER_RESULT": "success",
        "BROWSER_QUALIFICATION_RESULT": "success",
        "GOVERNANCE_AUDIT_RESULT": "skipped",
    })
    assert completed.returncode == 1, completed.stdout + completed.stderr


def test_operator_ruleset_template_satisfies_both_configuration_auditors():
    from scripts.v01_native_protection_audit import assess_native_policy

    candidate = json.loads(Path("infra/github/main-ruleset.json").read_text(encoding="utf-8"))
    # GitHub assigns this field on creation; this is fixture identity only.
    candidate["id"] = 123
    # GitHub sets these provenance fields on the native detail readback;
    # the checked-in creation template must not pretend to have them.
    candidate["source"] = "rumman52/Shuddho"
    candidate["source_type"] = "Repository"
    assert audit_governance(protected_branch(), [candidate]) == 123
    result = assess_native_policy(rulesets=[candidate])
    assert result["classification"] == "configuration_candidate"
    assert result["enforcement_verified"] is False

def test_day1_coworker_is_required_by_native_ruleset_audit():
    rule = approved_ruleset()
    checks = rule["rules"][3]["parameters"]["required_status_checks"]
    rule["rules"][3]["parameters"]["required_status_checks"] = [
        entry for entry in checks if entry["context"] != "coworker"
    ]
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


@pytest.mark.parametrize("weakened", [True, None, 0, "false", "False"])
def test_native_check_enforce_on_create_cannot_be_disabled_or_type_confused(weakened):
    """A strict check still needs to run for newly created refs."""
    rule = approved_ruleset()
    rule["rules"][3]["parameters"]["do_not_enforce_on_create"] = weakened
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


def test_missing_native_enforce_on_create_flag_is_not_trusted():
    """Missing native enforcement metadata is not proof of active checks."""
    rule = approved_ruleset()
    del rule["rules"][3]["parameters"]["do_not_enforce_on_create"]
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


@pytest.mark.parametrize(
    "unreviewed_row",
    [
        {"context": "test-and-build", "integration_id": 15368},
        {"context": "unreviewed-extra-check", "integration_id": 98765},
        {"context": "unreviewed-extra-check"},
        {"context": "unreviewed-extra-check", "integration_id": "15368"},
        {"context": "", "integration_id": 15368},
        {"context": "   ", "integration_id": 15368},
        {"context": "unreviewed-extra-check", "integration_id": 15368, "unknown": True},
        None,
    ],
    ids=[
        "duplicate-first-party-context",
        "extra-untrusted-publisher",
        "extra-absent-publisher",
        "extra-type-confused-publisher",
        "empty-context",
        "whitespace-context",
        "unknown-row-constraint",
        "malformed-row",
    ],
)
def test_governance_audit_rejects_ambiguous_or_untrusted_status_rows(unreviewed_row):
    """Every native status row must be unambiguous, not only the mandatory three."""
    rule = approved_ruleset()
    rule["rules"][3]["parameters"]["required_status_checks"].append(unreviewed_row)
    with pytest.raises(GovernanceAuditError, match="ruleset"):
        audit_governance(protected_branch(), [rule])


def test_governance_audit_allows_one_additional_unique_first_party_check():
    """The candidate audit enforces minimum policy; approved extra checks strengthen it."""
    rule = approved_ruleset()
    rule["rules"][3]["parameters"]["required_status_checks"].append(
        {"context": "additional-first-party-check", "integration_id": 15368}
    )
    assert audit_governance(protected_branch(), [rule]) == 123


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "external/Other"),
        ("source", "rumman52/shuddho"),
        ("source", None),
        ("source", ""),
        ("source_type", "Organization"),
        ("source_type", "Enterprise"),
        ("source_type", None),
        ("source_type", ""),
    ],
)
def test_governance_audit_rejects_foreign_and_inherited_rulesets(field, value):
    """Even complete review/check rules cannot establish another owner's policy."""
    snapshot = approved_ruleset()
    snapshot[field] = value
    with pytest.raises(GovernanceAuditError, match="no enforceable main ruleset"):
        audit_governance(protected_branch(), [snapshot])


@pytest.mark.parametrize("field", ["source", "source_type"])
def test_governance_audit_rejects_missing_origin_metadata(field):
    snapshot = approved_ruleset()
    del snapshot[field]
    with pytest.raises(GovernanceAuditError, match="no enforceable main ruleset"):
        audit_governance(protected_branch(), [snapshot])


@pytest.mark.parametrize(
    ("field", "value"),
    [("source", "elsewhere/Project"), ("source_type", "Organization")],
)
def test_foreign_redacted_bypass_does_not_misdiagnose_a_scoped_app_credential(field, value):
    snapshot = approved_ruleset()
    snapshot[field] = value
    del snapshot["bypass_actors"]
    # The native audit must not instruct an administrator to broaden access
    # for a policy that is not owned by the inspected repository.
    with pytest.raises(GovernanceAuditError, match="no enforceable main ruleset"):
        audit_governance(protected_branch(), [snapshot])


def test_inspect_repository_binds_ruleset_source_to_requested_rest_path(monkeypatch):
    from scripts import main_protection_audit as mod

    expected = approved_ruleset()
    expected["source"] = "owner/repo"

    def fake_read(url, token):
        assert token == "readback-token"
        assert "/repos/owner/repo/" in url
        if url.endswith("/branches/main"):
            return protected_branch()
        if url.endswith("/rulesets?includes_parents=true&per_page=100"):
            return [{"id": 123, "target": "branch", "enforcement": "active"}]
        if url.endswith("/rulesets/123"):
            return expected
        raise AssertionError(url)

    monkeypatch.setattr(mod, "_get_json", fake_read)
    assert inspect_repository("owner/repo", "readback-token") == 123
    expected["source"] = "different/repo"
    with pytest.raises(GovernanceAuditError, match="no enforceable main ruleset"):
        inspect_repository("owner/repo", "readback-token")



def test_creation_template_has_no_server_origin_but_stays_valid_for_admin_creation():
    """Creation-only validation reuses this helper before GitHub assigns source."""
    from scripts.main_protection_audit import _active_main_ruleset

    candidate = json.loads(Path("infra/github/main-ruleset.json").read_text(encoding="utf-8"))
    assert "source" not in candidate
    assert "source_type" not in candidate
    assert _active_main_ruleset(candidate) is True
