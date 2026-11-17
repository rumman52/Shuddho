"""Pure, offline Day 1 diagnostics: no GitHub mutations and no test credentials."""
import copy
import json

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
    assert data["qualified"] is False
    assert (tmp_path / "evidence.json").stat().st_mode & 0o777 == 0o600
    assert main(argv) == 2
    assert "blocked_input" in capsys.readouterr().out


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
