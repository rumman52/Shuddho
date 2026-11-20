"""D01.T02: test that historical issue closure never confers acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from scripts.validate_ten_day_acceptance_snapshot import DEFAULT_PATH, validate_inventory


@pytest.fixture()
def inventory() -> dict:
    return json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))


def test_ten_day_inventory_is_complete_but_explicitly_unattested(inventory: dict) -> None:
    summary = validate_inventory(inventory)
    assert summary == {
        "tasks": 100,
        "exit_checks": 54,
        "issue_checked_gates": 0,
        "attested_rows": 0,
    }
    # Closing an issue does not check its five release gates or attest its ten tasks.
    closed = [day for day in inventory["days"] if day["issue_state"] == "closed"]
    assert {day["day"] for day in closed} == {3, 4, 7}
    for day in closed:
        assert not any(
            gate["issue_checkbox_checked"]
            for gate in inventory["exit_checks"]
            if gate["issue_number"] == day["issue_number"]
        )


@pytest.mark.parametrize(
    ("path", "bad_value", "error"),
    [
        (("main_sha",), "not-a-commit", "40-character"),
        (("disposition",), "READY_FOR_OWNER_CONTROLLED_PILOT", "cannot declare pilot"),
        (("tasks", 0, "acceptance"), "ATTESTED", "cannot be accepted"),
        (("exit_checks", 0, "acceptance"), "ATTESTED", "cannot be accepted"),
        (("tasks", 0, "issue_number"), 736, "missing or misassigned"),
        (("exit_checks", 0, "issue_number"), 736, "missing or misassigned"),
        (("exit_checks", 0, "issue_checkbox_checked"), "false", "real boolean"),
        (("tasks", 0, "title"), "", "lacks a task title"),
        (("days", 0, "task_count"), 9, "source counts"),
        (("days", 0, "issue_number"), 736, "must reference issue"),
    ],
)
def test_fake_or_malformed_issue_evidence_is_rejected(
    inventory: dict, path: tuple, bad_value: object, error: str
) -> None:
    changed = copy.deepcopy(inventory)
    node = changed
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad_value
    with pytest.raises(ValueError, match=error):
        validate_inventory(changed)


def test_missing_or_duplicate_inventory_rows_fail_closed(inventory: dict) -> None:
    absent = copy.deepcopy(inventory)
    absent["tasks"].pop()
    with pytest.raises(ValueError, match="100 task"):
        validate_inventory(absent)

    repeated = copy.deepcopy(inventory)
    repeated["tasks"][1]["id"] = repeated["tasks"][0]["id"]
    with pytest.raises(ValueError, match="duplicate task"):
        validate_inventory(repeated)

    missing_gate = copy.deepcopy(inventory)
    missing_gate["exit_checks"].pop()
    with pytest.raises(ValueError, match="54 exit"):
        validate_inventory(missing_gate)
