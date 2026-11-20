"""Day 01 admin ruleset repair: no live writes, all network calls simulated."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from scripts import reconcile_main_ruleset as reconcile
from scripts.apply_main_ruleset import ApplyMainRulesetError

REPO = "rumman52/Shuddho"
SHA = "6f7eae6b9642b9ba22de055aeee11acd1f5ece16"


def policy() -> dict:
    from pathlib import Path
    return json.loads(
        Path("infra/github/main-ruleset.json").read_text(encoding="utf-8")
    )


def weak_existing() -> dict:
    return {
        "id": reconcile.RULESET_ID,
        "name": "Shuddho main review and CI",
        "source": REPO,
        "source_type": "Repository",
        "target": "branch",
        "enforcement": "active",
        "conditions": {
            "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
        },
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "required_reviewers": [],
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": False,
                "require_extra_approval_for_unattributed_changes": False,
                "allowed_merge_methods": ["merge", "squash", "rebase"],
            }},
        ],
    }


@pytest.fixture
def api(monkeypatch):
    state = {
        "current": weak_existing(),
        "main_sha": SHA,
        "writes": [],
        "calls": [],
        "commit_put": True,
        "raise_after_put": False,
    }

    def fake(method, url, token, payload=None):
        state["calls"].append((method, url))
        assert token == "fake-admin-token"
        assert url.startswith("https://api.github.com/repos/" + REPO)
        if method == "GET" and url.endswith("/branches/main"):
            return {
                "name": "main",
                "protected": True,
                "commit": {"sha": state["main_sha"]},
            }
        if method == "GET" and "/rulesets?" in url:
            return [{
                "id": state["current"]["id"],
                "name": state["current"]["name"],
                "target": "branch",
                "enforcement": "active",
            }]
        if method == "GET" and url.endswith(f"/rulesets/{state['current']['id']}"):
            return deepcopy(state["current"])
        if method == "PUT" and url.endswith(f"/rulesets/{reconcile.RULESET_ID}"):
            state["writes"].append(deepcopy(payload))
            if state["commit_put"]:
                state["current"] = {
                    **deepcopy(payload), "id": reconcile.RULESET_ID,
                    "source": REPO, "source_type": "Repository",
                }
            if state["raise_after_put"]:
                raise ApplyMainRulesetError("PUT response lost after commit")
            return {"id": reconcile.RULESET_ID}
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(reconcile, "_request_json", fake)
    # Existing shared readback helper uses its own module-global transport.
    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    return state


def call(**kwargs):
    return reconcile.reconcile_main_ruleset(
        REPO, "fake-admin-token", policy(),
        expected_main_sha=SHA, **kwargs,
    )


def test_dry_run_reports_existing_rule_and_does_not_create_or_modify(api):
    report = call()
    assert report["status"] == "dry_run"
    assert report["ruleset_id"] == 27324410
    assert report["would_create"] is False
    assert report["would_update_existing"] is True
    assert report["main_sha"] == SHA
    assert report["observed_sha256"] == reconcile.ruleset_fingerprint(api["current"])
    assert report["required_checks"] == ["test-and-build", "coworker", "ci-merge-gate"]
    assert report["qualified"] is False
    assert report["merge_enforcement_verified"] is False
    assert api["writes"] == []


def test_apply_updates_once_after_confirmations_and_verifies_same_id(api):
    digest = call()["observed_sha256"]
    done = call(
        apply=True,
        expected_current_ruleset_sha256=digest,
        confirm_repository=REPO,
        confirm_ruleset_id=27324410,
    )
    assert done["status"] == "configuration_updated_readback_verified"
    assert done["ruleset_id"] == reconcile.RULESET_ID
    assert done["qualified"] is False
    assert done["merge_enforcement_verified"] is False
    assert len(api["writes"]) == 1
    submitted = api["writes"][0]
    assert submitted["bypass_actors"] == []
    assert submitted["conditions"]["ref_name"] == {
        "include": ["refs/heads/main"], "exclude": [],
    }
    review = next(row["parameters"] for row in submitted["rules"] if row["type"] == "pull_request")
    assert review["required_approving_review_count"] == 1
    assert review["allowed_merge_methods"] == ["merge", "squash", "rebase"]
    checks = next(row["parameters"] for row in submitted["rules"] if row["type"] == "required_status_checks")
    assert checks["strict_required_status_checks_policy"] is True
    assert all(row["integration_id"] == 15368 for row in checks["required_status_checks"])
    assert {row["context"] for row in checks["required_status_checks"]} == {
        "test-and-build", "coworker", "ci-merge-gate",
    }


@pytest.mark.parametrize("kwargs", [
    {"confirm_repository": REPO, "confirm_ruleset_id": 27324410},
    {"expected_current_ruleset_sha256": "a" * 64, "confirm_ruleset_id": 27324410},
    {"expected_current_ruleset_sha256": "a" * 64, "confirm_repository": REPO},
    {"expected_current_ruleset_sha256": "a" * 64, "confirm_repository": REPO, "confirm_ruleset_id": 123},
    {"expected_current_ruleset_sha256": "invalid", "confirm_repository": REPO, "confirm_ruleset_id": 27324410},
])
def test_missing_or_invalid_apply_confirmation_fails_before_network(api, kwargs):
    with pytest.raises(ApplyMainRulesetError, match="requires exact"):
        call(apply=True, **kwargs)
    assert api["calls"] == []


def test_changed_branch_sha_blocks_update(api):
    api["main_sha"] = "f" * 40
    with pytest.raises(ApplyMainRulesetError, match="main SHA"):
        call()
    assert api["writes"] == []


def test_stale_ruleset_fingerprint_blocks_update(api):
    digest = call()["observed_sha256"]
    api["current"]["rules"][2]["parameters"]["allowed_merge_methods"] = ["squash"]
    with pytest.raises(ApplyMainRulesetError, match="configuration changed since dry-run"):
        call(
            apply=True, expected_current_ruleset_sha256=digest,
            confirm_repository=REPO, confirm_ruleset_id=27324410,
        )
    assert api["writes"] == []


def test_current_main_rule_change_during_second_read_blocks_put(api, monkeypatch):
    digest = call()["observed_sha256"]
    first_get = reconcile._request_json
    state = {"details": 0}

    def drift(method, url, token, payload=None):
        result = first_get(method, url, token, payload)
        if method == "GET" and url.endswith("/rulesets/27324410"):
            state["details"] += 1
            if state["details"] >= 2:
                result["rules"][2]["parameters"]["required_approving_review_count"] = 1
        return result

    monkeypatch.setattr(reconcile, "_request_json", drift)
    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", drift)
    with pytest.raises(ApplyMainRulesetError, match="changed just before PUT"):
        call(
            apply=True, expected_current_ruleset_sha256=digest,
            confirm_repository=REPO, confirm_ruleset_id=27324410,
        )
    assert api["writes"] == []


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(id=111),
    lambda x: x.update(bypass_actors=[{"actor_id": 1, "actor_type": "User"}]),
    lambda x: x.update(source_type="Organization"),
    lambda x: x["conditions"]["ref_name"].update(exclude=["refs/heads/main"]),
    lambda x: x["rules"].append({"type": "commit_message_pattern", "parameters": {"pattern": "x"}}),
    lambda x: x["rules"][2]["parameters"].update(required_approving_review_count=2),
    lambda x: x["rules"][2]["parameters"].update(require_code_owner_review=True),
    lambda x: x["rules"][2]["parameters"].update(required_reviewers=[{"id": 12}]),
])
def test_unknown_stronger_or_other_resource_policy_never_overwritten(api, mutation):
    mutation(api["current"])
    with pytest.raises(ApplyMainRulesetError):
        call()
    assert api["writes"] == []


def test_additional_existing_required_check_is_not_discarded(api):
    api["current"]["rules"].append({
        "type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {"context": "legal-review", "integration_id": 15368}
            ],
        },
    })
    with pytest.raises(ApplyMainRulesetError, match="additional required status checks"):
        call()
    assert api["writes"] == []


def test_already_compliant_does_not_put_or_claim_enforcement(api):
    api["current"] = {
        **policy(), "id": 27324410,
        "source": REPO, "source_type": "Repository",
    }
    report = call()
    assert report["status"] == "already_configured"
    assert report["qualified"] is False
    assert api["writes"] == []


def test_lost_put_response_with_verified_readback_is_not_retried(api):
    digest = call()["observed_sha256"]
    api["raise_after_put"] = True
    report = call(
        apply=True, expected_current_ruleset_sha256=digest,
        confirm_repository=REPO, confirm_ruleset_id=27324410,
    )
    assert report["status"] == "put_outcome_uncertain_but_verified"
    assert len(api["writes"]) == 1
    assert report["qualified"] is False


def test_unverified_put_response_fails_closed_without_retry(api):
    digest = call()["observed_sha256"]
    api["commit_put"] = False
    api["raise_after_put"] = True
    with pytest.raises(ApplyMainRulesetError, match="do not retry"):
        call(
            apply=True, expected_current_ruleset_sha256=digest,
            confirm_repository=REPO, confirm_ruleset_id=27324410,
        )
    assert len(api["writes"]) == 1


def test_rejects_unrelated_repository_and_invalid_main_sha_before_network(api):
    with pytest.raises(ApplyMainRulesetError, match="repository"):
        reconcile.reconcile_main_ruleset(
            "unrelated/repository", "fake-admin-token", policy(),
            expected_main_sha=SHA,
        )
    with pytest.raises(ApplyMainRulesetError, match="exact 40-character"):
        reconcile.reconcile_main_ruleset(
            REPO, "fake-admin-token", policy(), expected_main_sha="abc",
        )
    assert api["calls"] == []



@pytest.mark.parametrize("existing_rows", [
    [
        {"context": "coworker", "integration_id": 15368},
        {"context": "coworker", "integration_id": 15368},
    ],
    [
        {"context": "coworker", "integration_id": 15368, "unreviewed_constraint": True},
    ],
])
def test_ambiguous_existing_status_checks_require_manual_reconciliation(api, existing_rows):
    """An existing status-check rule with ambiguous entries must not be silently replaced."""
    api["current"]["rules"].append({
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": existing_rows,
        },
    })
    with pytest.raises(ApplyMainRulesetError, match="additional required status checks"):
        call()
    assert api["writes"] == []


def test_known_unscoped_existing_check_can_still_be_reconciled(api):
    """An existing required context lacking a publisher can be tightened to the reviewed App ID."""
    api["current"]["rules"].append({
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": False,
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {"context": "coworker", "integration_id": None},
            ],
        },
    })
    report = call()
    assert report["status"] == "dry_run"
    assert report["required_checks"] == ["test-and-build", "coworker", "ci-merge-gate"]
    assert api["writes"] == []



@pytest.mark.parametrize("ambiguous_row", [
    {"context": "coworker", "integration_id": 15368},
    {"context": "coworker", "integration_id": 15368, "unreviewed_constraint": True},
])
def test_already_compliant_ruleset_rejects_ambiguous_native_status_checks(api, ambiguous_row):
    """The early 'already_configured' return must not mask native-rule ambiguity."""
    api["current"] = {
        **policy(), "id": reconcile.RULESET_ID,
        "source": REPO, "source_type": "Repository",
    }
    rows = api["current"]["rules"][-1]["parameters"]["required_status_checks"]
    if "unreviewed_constraint" in ambiguous_row:
        rows[1] = ambiguous_row
    else:
        rows.append(ambiguous_row)
    with pytest.raises(ApplyMainRulesetError, match="additional required status checks"):
        call()
    assert api["writes"] == []



@pytest.mark.parametrize("publisher", [
    98765, 0, "15368", 15368.0, True,
])
def test_unreviewed_existing_check_publisher_requires_manual_reconciliation(api, publisher):
    """A native context's explicit third-party or malformed publisher cannot be overwritten."""
    api["current"]["rules"].append({
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {"context": "coworker", "integration_id": publisher},
            ],
        },
    })
    with pytest.raises(ApplyMainRulesetError, match="publisher"):
        call()
    # Even a correctly confirmed operator apply may not rewrite this
    # unreviewed native publisher; the test transport records any PUT.
    with pytest.raises(ApplyMainRulesetError, match="publisher"):
        call(
            apply=True,
            expected_current_ruleset_sha256=reconcile.ruleset_fingerprint(api["current"]),
            confirm_repository=REPO,
            confirm_ruleset_id=reconcile.RULESET_ID,
        )
    assert api["writes"] == []


@pytest.mark.parametrize("publisher", [None, 15368])
def test_known_null_or_reviewed_check_publisher_can_be_reconciled(api, publisher):
    """Unscoped/pinned entries may be reviewed, without any mutation during a dry-run."""
    api["current"]["rules"].append({
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": False,
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {"context": "coworker", "integration_id": publisher},
            ],
        },
    })
    report = call()
    assert report["status"] == "dry_run"
    assert report["required_checks"] == ["test-and-build", "coworker", "ci-merge-gate"]
    assert api["writes"] == []
