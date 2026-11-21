"""Pure, offline Day 1 diagnostics: no GitHub mutations and no test credentials."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.day1_ruleset_drift import EvidenceError, analyze, main

SHA = "16025e73cb3ef80e00b2ec054f78607ae44613fd"


def policy():
    return {
        "name": "Shuddho main review and CI", "target": "branch", "enforcement": "active",
        "bypass_actors": [], "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"}, {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
                "require_code_owner_review": False,
            }},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "do_not_enforce_on_create": False,
                "required_status_checks": [
                    {"context": "test-and-build", "integration_id": 15368},
                    {"context": "coworker", "integration_id": 15368},
                    {"context": "ci-merge-gate", "integration_id": 15368},
                ],
            }},
        ],
    }


def branch():
    return {"name": "main", "protected": True, "commit": {"sha": SHA}}


def live():
    item = copy.deepcopy(policy())
    item["id"] = 27324410
    item["source"] = "rumman52/Shuddho"
    item["source_type"] = "Repository"
    item["conditions"]["ref_name"]["include"] = ["~DEFAULT_BRANCH"]
    return item


def test_live_day1_drift_is_explicit_and_never_qualified():
    item = live()
    item["rules"] = item["rules"][:-1]
    params = item["rules"][2]["parameters"]
    params.update(required_approving_review_count=0, dismiss_stale_reviews_on_push=False,
                  require_last_push_approval=False, required_review_thread_resolution=False)
    report = analyze(branch(), item, policy(), expected_main_sha=SHA)
    assert report["status"] == "blocked_configuration"
    assert report["qualified"] is False
    assert report["merge_enforcement_verified"] is False
    for gap in ("reviews.independent_approval_count", "reviews.dismiss_stale_reviews_on_push",
                "reviews.require_last_push_approval", "reviews.required_review_thread_resolution",
                "ruleset.unique_required_status_checks", "checks.first_party_test-and-build",
                "checks.first_party_ci-merge-gate"):
        assert gap in report["drift"]


def test_compliant_configuration_remains_unqualified_without_operated_merge_controls():
    report = analyze(branch(), live(), policy(), expected_main_sha=SHA)
    assert report["status"] == "configuration_candidate"
    assert report["drift"] == []
    assert report["qualified"] is False
    assert report["merge_enforcement_verified"] is False
    assert report["independent_review_verified"] is False


def test_redacted_bypass_actors_fail_closed():
    item = live()
    del item["bypass_actors"]
    report = analyze(branch(), item, policy(), expected_main_sha=SHA)
    assert "ruleset.bypass_actors_verified_empty" in report["drift"]


def test_wrong_or_malformed_sha_cannot_pass():
    report = analyze(branch(), live(), policy(), expected_main_sha="1" * 40)
    assert "branch.commit_sha" in report["drift"]
    with pytest.raises(EvidenceError, match="40-character"):
        analyze(branch(), live(), policy(), expected_main_sha="deadbeef")


def test_policy_weakened_in_checkout_is_rejected_before_comparison():
    changed = policy()
    changed["rules"][2]["parameters"]["required_approving_review_count"] = 0
    with pytest.raises(EvidenceError, match="independent current-head"):
        analyze(branch(), live(), changed, expected_main_sha=SHA)


def test_status_check_wrong_integration_or_boolean_id_fails_closed():
    item = live()
    item["rules"][-1]["parameters"]["required_status_checks"][0]["integration_id"] = True
    report = analyze(branch(), item, policy(), expected_main_sha=SHA)
    assert "checks.first_party_test-and-build" in report["drift"]


def test_cli_writes_one_private_report_and_will_not_overwrite(tmp_path, capsys):
    for name, body in (("branch", branch()), ("ruleset", live()), ("policy", policy())):
        (tmp_path / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")
    argv = [
        "--branch-json", str(tmp_path / "branch.json"),
        "--ruleset-json", str(tmp_path / "ruleset.json"),
        "--policy-json", str(tmp_path / "policy.json"),
        "--expected-main-sha", SHA,
        "--output", str(tmp_path / "evidence.json"),
    ]
    assert main(argv) == 0
    data = json.loads((tmp_path / "evidence.json").read_text())
    # The receipt must identify the exact captured bytes, not just a decoded
    # object which could have changed whitespace, order, or provenance.
    for filename, field in (
        ("branch", "branch_readback_sha256"),
        ("ruleset", "ruleset_readback_sha256"),
        ("policy", "reviewed_policy_sha256"),
    ):
        expected = hashlib.sha256((tmp_path / f"{filename}.json").read_bytes()).hexdigest()
        assert data[field] == expected
    assert data["qualified"] is False
    assert (tmp_path / "evidence.json").stat().st_mode & 0o777 == 0o600
    assert main(argv) == 2
    assert "blocked_input" in capsys.readouterr().out


def test_ruleset_report_hash_changes_for_same_meaning_different_bytes(tmp_path, capsys):
    for name, body in (("branch", branch()), ("ruleset", live()), ("policy", policy())):
        (tmp_path / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")
    argv = [
        "--branch-json", str(tmp_path / "branch.json"),
        "--ruleset-json", str(tmp_path / "ruleset.json"),
        "--policy-json", str(tmp_path / "policy.json"),
        "--expected-main-sha", SHA,
    ]
    assert main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    (tmp_path / "ruleset.json").write_text(json.dumps(live(), indent=2), encoding="utf-8")
    assert main(argv) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["status"] == second["status"] == "configuration_candidate"
    assert first["drift"] == second["drift"] == []
    assert first["ruleset_readback_sha256"] != second["ruleset_readback_sha256"]
    assert first["branch_readback_sha256"] == second["branch_readback_sha256"]
    assert first["reviewed_policy_sha256"] == second["reviewed_policy_sha256"]
    assert second["qualified"] is False


def test_cli_rejects_symlinked_input(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(branch()))
    (tmp_path / "branch.json").symlink_to(source)
    (tmp_path / "ruleset.json").write_text(json.dumps(live()))
    (tmp_path / "policy.json").write_text(json.dumps(policy()))
    assert main([
        "--branch-json", str(tmp_path / "branch.json"),
        "--ruleset-json", str(tmp_path / "ruleset.json"),
        "--policy-json", str(tmp_path / "policy.json"),
        "--expected-main-sha", SHA,
    ]) == 2

def test_live_ruleset_missing_mandatory_coworker_cannot_be_ignored():
    weakened_live = live()
    checks = weakened_live["rules"][-1]["parameters"]["required_status_checks"]
    weakened_live["rules"][-1]["parameters"]["required_status_checks"] = [
        entry for entry in checks if entry["context"] != "coworker"
    ]
    report = analyze(branch(), weakened_live, policy(), expected_main_sha=SHA)
    assert report["status"] == "blocked_configuration"
    assert "checks.first_party_coworker" in report["drift"]
    assert report["qualified"] is False

    good = analyze(branch(), live(), policy(), expected_main_sha=SHA)
    assert good["status"] == "configuration_candidate"
    assert good["qualified"] is False


@pytest.mark.parametrize("bad_check", [
    {"context": "coworker", "integration_id": True},
    {"context": "coworker", "integration_id": 12345},
    {"context": 17, "integration_id": 15368},
    {"context": "test-and-build", "integration_id": 15368},
])
def test_reviewed_policy_rejects_untrusted_or_duplicate_additional_checks(bad_check):
    updated_policy = policy()
    updated_policy["rules"][-1]["parameters"]["required_status_checks"].append(bad_check)
    with pytest.raises(EvidenceError, match="reviewed policy"):
        analyze(branch(), live(), updated_policy, expected_main_sha=SHA)

@pytest.mark.parametrize("bad_branch_json", [
    # A normal decoder would silently pick the last value, obscuring input
    # that may have been tampered with or captured ambiguously.
    '{"name":"wrong","name":"main","protected":true}',
    '{"name":"main","protected":true,"commit":{"sha":"wrong","sha":"' + SHA + '"}}',
    '{"name":"main","protected":true,"quality":NaN,"commit":{"sha":"' + SHA + '"}}',
    '{"name":"main","protected":true,"quality":1e999,"commit":{"sha":"' + SHA + '"}}',
])
def test_cli_rejects_duplicate_json_keys_and_nonfinite_values(
    tmp_path, capsys, bad_branch_json
):
    (tmp_path / "branch.json").write_text(bad_branch_json)
    (tmp_path / "ruleset.json").write_text(json.dumps(live()))
    (tmp_path / "policy.json").write_text(json.dumps(policy()))
    code = main([
        "--branch-json", str(tmp_path / "branch.json"),
        "--ruleset-json", str(tmp_path / "ruleset.json"),
        "--policy-json", str(tmp_path / "policy.json"),
        "--expected-main-sha", SHA,
    ])
    assert code == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked_input"


def test_coworker_is_unconditionally_required_even_if_checked_in_template_is_weakened():
    # A modified checked-in template cannot make the third Day 1 check
    # disappear from BOTH the policy and a supplied live snapshot.
    weakened_policy = policy()
    checks = weakened_policy["rules"][-1]["parameters"]["required_status_checks"]
    weakened_policy["rules"][-1]["parameters"]["required_status_checks"] = [
        entry for entry in checks if entry["context"] != "coworker"
    ]
    weakened_live = live()
    checks = weakened_live["rules"][-1]["parameters"]["required_status_checks"]
    weakened_live["rules"][-1]["parameters"]["required_status_checks"] = [
        entry for entry in checks if entry["context"] != "coworker"
    ]
    with pytest.raises(EvidenceError, match="mandatory first-party checks"):
        analyze(branch(), weakened_live, weakened_policy, expected_main_sha=SHA)


@pytest.mark.parametrize(
    "extra_rows",
    [
        [{"context": "extra-stage", "integration_id": 15368},
         {"context": "extra-stage", "integration_id": 15368}],
        [{"context": "extra-stage", "integration_id": 98765}],
        [{"context": "extra-stage"}],
        [{"context": "extra-stage", "integration_id": None}],
        [{"context": "extra-stage", "integration_id": True}],
        [{"context": "extra-stage", "integration_id": "15368"}],
        [{"context": "", "integration_id": 15368}],
        [{"context": "  ", "integration_id": 15368}],
        [{"context": "extra-stage", "integration_id": 15368, "unknown": True}],
        [None],
        ["not-a-status-object"],
    ],
    ids=[
        "duplicate-extra-first-party",
        "extra-wrong-app",
        "extra-missing-app",
        "extra-null-app",
        "extra-bool-app",
        "extra-string-app",
        "extra-empty-name",
        "extra-blank-name",
        "extra-unknown-key",
        "extra-null-row",
        "extra-string-row",
    ],
)
def test_live_untrusted_or_ambiguous_extra_status_rows_are_blocked(extra_rows):
    """Offline snapshots must not hide an extra native check that cannot be trusted."""
    snapshot = live()
    snapshot["rules"][-1]["parameters"]["required_status_checks"].extend(extra_rows)
    report = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert report["status"] == "blocked_configuration"
    assert "checks.unambiguous_first_party_rows" in report["drift"]
    assert report["qualified"] is False


def test_unexpected_keys_on_mandatory_native_status_row_are_detected():
    snapshot = live()
    snapshot["rules"][-1]["parameters"]["required_status_checks"][0]["unknown"] = "ignored-before"
    report = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert "checks.unambiguous_first_party_rows" in report["drift"]


def test_reviewed_policy_rejects_extra_unrecognized_status_row_keys():
    altered = policy()
    altered["rules"][-1]["parameters"]["required_status_checks"][0]["unreviewed"] = True
    with pytest.raises(EvidenceError, match="reviewed policy"):
        analyze(branch(), live(), altered, expected_main_sha=SHA)


def test_one_unique_extra_first_party_native_check_remains_nonqualifying_candidate():
    snapshot = live()
    snapshot["rules"][-1]["parameters"]["required_status_checks"].append(
        {"context": "additional-first-party", "integration_id": 15368}
    )
    report = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert report["status"] == "configuration_candidate"
    assert report["drift"] == []
    assert report["qualified"] is False
    assert report["merge_enforcement_verified"] is False


@pytest.mark.parametrize(
    ("field", "untrusted_value"),
    [
        ("source", "foreign/Other"),
        ("source", "rumman52/shuddho"),
        ("source", None),
        ("source", ""),
        ("source_type", "Organization"),
        ("source_type", "Enterprise"),
        ("source_type", None),
        ("source_type", ""),
    ],
)
def test_offline_governance_rejects_missing_or_foreign_repository_origin(field, untrusted_value):
    """A matching rule ID and check set do not establish repository ownership."""
    snapshot = live()
    snapshot[field] = untrusted_value
    result = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert result["status"] == "blocked_configuration"
    assert "ruleset.repository_origin" in result["drift"]
    assert result["qualified"] is False


@pytest.mark.parametrize("field", ["source", "source_type"])
def test_offline_governance_rejects_omitted_repository_origin(field):
    snapshot = live()
    del snapshot[field]
    result = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert result["status"] == "blocked_configuration"
    assert "ruleset.repository_origin" in result["drift"]


def test_repo_owned_ruleset_still_only_yields_nonqualifying_candidate():
    snapshot = live()
    assert snapshot["source"] == "rumman52/Shuddho"
    assert snapshot["source_type"] == "Repository"
    result = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert result["status"] == "configuration_candidate"
    assert result["drift"] == []
    assert result["qualified"] is False
    assert result["independent_review_verified"] is False


@pytest.mark.parametrize(
    "include",
    [
        ["~DEFAULT_BRANCH", "refs/heads/dev"],
        ["refs/heads/main", "refs/heads/release"],
        ["~DEFAULT_BRANCH", "refs/heads/main"],
        ["~DEFAULT_BRANCH", "~ALL"],
        ["~DEFAULT_BRANCH", "~DEFAULT_BRANCH"],
        ["refs/heads/main", 3],
    ],
    ids=[
        "additional-branch", "main-and-release", "dual-aliases",
        "all-branches", "duplicate-default", "nonstring-extra",
    ],
)
def test_native_scope_must_be_one_exact_main_selector(include):
    """An extra selector must not pass as exact main despite including main."""
    snapshot = live()
    snapshot["conditions"]["ref_name"]["include"] = include
    result = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert result["status"] == "blocked_configuration"
    assert "ruleset.main_scope" in result["drift"]
    assert result["qualified"] is False


@pytest.mark.parametrize("location", ["conditions", "ref_name"])
def test_native_scope_rejects_unreviewed_condition_fields(location):
    snapshot = live()
    destination = (
        snapshot["conditions"] if location == "conditions"
        else snapshot["conditions"]["ref_name"]
    )
    destination["unreviewed_selector"] = {"include": ["refs/heads/main"]}
    result = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert "ruleset.main_scope" in result["drift"]
    assert result["status"] == "blocked_configuration"


@pytest.mark.parametrize("location", ["conditions", "ref_name"])
def test_reviewed_policy_rejects_unapproved_scope_fields(location):
    altered = policy()
    destination = (
        altered["conditions"] if location == "conditions"
        else altered["conditions"]["ref_name"]
    )
    destination["unknown_selector"] = ["refs/heads/other"]
    with pytest.raises(EvidenceError, match="reviewed policy must target only main"):
        analyze(branch(), live(), altered, expected_main_sha=SHA)


@pytest.mark.parametrize("include", [["~DEFAULT_BRANCH"], ["refs/heads/main"]])
def test_exact_single_main_scope_remains_nonqualifying_candidate(include):
    snapshot = live()
    snapshot["conditions"]["ref_name"]["include"] = include
    result = analyze(branch(), snapshot, policy(), expected_main_sha=SHA)
    assert result["status"] == "configuration_candidate"
    assert result["drift"] == []
    assert result["qualified"] is False
    assert result["merge_enforcement_verified"] is False


@pytest.mark.parametrize("attacked_name", ["branch", "ruleset", "policy"])
def test_input_replaced_by_symlink_at_open_is_rejected(
    tmp_path, monkeypatch, capsys, attacked_name
):
    """A pre-open is_symlink/stat check cannot authorize a later swapped path."""
    originals = {"branch": branch(), "ruleset": live(), "policy": policy()}
    for name, body in originals.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")

    attacked = tmp_path / f"{attacked_name}.json"
    shadow = tmp_path / "shadow.json"
    # The malicious replacement is itself syntactically valid, so acceptance
    # of the swapped path would produce a misleading clean candidate receipt.
    shadow.write_text(json.dumps(originals[attacked_name]), encoding="utf-8")
    actual_read_bytes = Path.read_bytes
    actual_os_open = os.open
    swapped = False

    def swap_to_symlink():
        nonlocal swapped
        if not swapped:
            attacked.unlink()
            attacked.symlink_to(shadow)
            swapped = True

    def raced_path_read_bytes(path):
        if path == attacked:
            swap_to_symlink()
        return actual_read_bytes(path)

    def raced_fd_open(file, flags, *args, **kwargs):
        if os.fspath(file) == os.fspath(attacked):
            swap_to_symlink()
        return actual_os_open(file, flags, *args, **kwargs)

    # Exercise either implementation's actual opening operation. The legacy
    # version uses Path.read_bytes; a safe version uses one no-follow fd.
    monkeypatch.setattr(Path, "read_bytes", raced_path_read_bytes)
    monkeypatch.setattr(os, "open", raced_fd_open)
    code = main([
        "--branch-json", str(tmp_path / "branch.json"),
        "--ruleset-json", str(tmp_path / "ruleset.json"),
        "--policy-json", str(tmp_path / "policy.json"),
        "--expected-main-sha", SHA,
    ])
    assert swapped is True
    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked_input"
