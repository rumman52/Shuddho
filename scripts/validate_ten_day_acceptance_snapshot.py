"""Fail-closed structure check for the dated ten-day issue inventory.

This tool checks *inventory shape*, not live evidence, external approvals, or
release qualification. Issue closure and issue prose never grant acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/coworker-roadmap/TEN_DAY_100_TASK_54_GATE_SNAPSHOT_2026-11-20.json"
)
_NOT_ATTESTED = "NOT_ATTESTED"
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def validate_inventory(snapshot: dict[str, Any]) -> dict[str, int]:
    """Reject missing, duplicate, misassigned or self-attested inventory rows."""
    if snapshot.get("schema_version") != 1:
        raise ValueError("unsupported inventory schema")
    if not _SHA.fullmatch(str(snapshot.get("main_sha", ""))):
        raise ValueError("snapshot requires one exact 40-character source SHA")
    if snapshot.get("disposition") != "SOURCE_ONLY / NO-GO":
        raise ValueError("issue inventory cannot declare pilot qualification")
    days = snapshot.get("days")
    tasks = snapshot.get("tasks")
    gates = snapshot.get("exit_checks")
    if not isinstance(days, list) or len(days) != 10:
        raise ValueError("ten day issue snapshots required")
    if not isinstance(tasks, list) or len(tasks) != 100:
        raise ValueError("exactly 100 task rows required")
    if not isinstance(gates, list) or len(gates) != 54:
        raise ValueError("exactly 54 exit rows required")

    def verify_rows(rows: list[dict[str, Any]], *, kind: str) -> None:
        seen: set[str] = set()
        for row in rows:
            row_id = row.get("id")
            if row_id in seen:
                raise ValueError(f"duplicate {kind} row: {row_id}")
            seen.add(row_id)
            if row.get("acceptance") != _NOT_ATTESTED:
                raise ValueError(f"{row_id} cannot be accepted by issue-status prose")
            if not isinstance(row.get("issue_number"), int):
                raise ValueError(f"{row_id} lacks a numeric source issue")
            if kind == "task":
                if not isinstance(row.get("title"), str) or not row["title"].strip():
                    raise ValueError(f"{row_id} lacks a task title")
                if not isinstance(row.get("issue_reported_status"), str) or not row["issue_reported_status"].strip():
                    raise ValueError(f"{row_id} lacks its issue-reported status")
            else:
                if not isinstance(row.get("criterion"), str) or not row["criterion"].strip():
                    raise ValueError(f"{row_id} lacks its source exit criterion")
                if type(row.get("issue_checkbox_checked")) is not bool:
                    raise ValueError(f"{row_id} requires a real boolean checkbox state")

    verify_rows(tasks, kind="task")
    verify_rows(gates, kind="gate")
    for day in range(1, 11):
        issue_number = 726 + day
        matching = [d for d in days if d.get("day") == day]
        if len(matching) != 1 or matching[0].get("issue_number") != issue_number:
            raise ValueError(f"Day {day} must reference issue #{issue_number} once")
        expected_exits = 6 if day == 9 else 8 if day == 10 else 5
        if matching[0].get("task_count") != 10 or matching[0].get("exit_count") != expected_exits:
            raise ValueError(f"Day {day} source counts differ from the 100/54 plan")
        for kind, rows, count, letter in (
            ("task", tasks, 10, "T"),
            ("gate", gates, expected_exits, "E"),
        ):
            found = sorted(
                r["id"] for r in rows if r["issue_number"] == issue_number
            )
            expected = [f"D{day:02d}.{letter}{item:02d}" for item in range(1, count + 1)]
            if found != expected:
                raise ValueError(f"Day {day} {kind} IDs are missing or misassigned")
    if not isinstance(snapshot.get("historical_unreconciled_claims"), list):
        raise ValueError("historical count discrepancy must remain explicit")
    return {
        "tasks": len(tasks),
        "exit_checks": len(gates),
        "issue_checked_gates": sum(g["issue_checkbox_checked"] for g in gates),
        "attested_rows": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", nargs="?", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    summary = validate_inventory(json.loads(args.snapshot.read_text(encoding="utf-8")))
    print(f"STRUCTURE ONLY — {summary['tasks']} tasks, {summary['exit_checks']} exits; "
          f"{summary['issue_checked_gates']} issue checkboxes; "
          "NO-GO / no operated or independently accepted evidence inferred")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
