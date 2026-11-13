"""Fail-closed reconciliation of *two real-day* PA-10 daily briefing probes.

An operator must separately prove from Temporal server logs that occurrences were
natural timer firings, not manual triggers. API history alone cannot prove origin.
This file cannot schedule, backfill, or synthesize either occurrence.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if __package__:
    from .staging_pa10_scheduled_profile import load_json
else:
    from staging_pa10_scheduled_profile import load_json


class GateFailure(RuntimeError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise GateFailure(reason)


def timestamp(raw: object, field: str) -> datetime:
    require(isinstance(raw, str) and bool(raw), f"Missing {field} timestamp.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError) as error:
        raise GateFailure(f"Malformed {field} timestamp.") from error
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"{field} must include an explicit timezone offset.")
    return parsed.astimezone(timezone.utc)


def strings(value: object, field: str) -> list[str]:
    require(isinstance(value, list) and bool(value), f"{field} must be a nonempty list.")
    require(all(isinstance(item, str) and bool(item.strip()) for item in value),
            f"{field} entries must be nonblank strings.")
    require(len(value) == len(set(value)), f"{field} contains duplicate ids.")
    return value


def verify_two_day(first: dict, second: dict, paused: dict) -> dict:
    """Check cross-day pins, local schedule, identity, notices and paused state."""
    require(all(isinstance(x, dict) for x in (first, second, paused)),
            "Expected three JSON evidence objects.")
    release = first.get("release")
    require(isinstance(release, dict), "Release identity must be a JSON object.")
    for field in ("release_id", "source_revision", "environment", "deployment_reference",
                  "rollout_manifest_sha256", "provider_policy_sha256"):
        value = release.get(field)
        require(isinstance(value, str) and bool(value.strip()),
                f"Release identity is missing {field}.")
    require(re.fullmatch(r"[0-9a-f]{40}", release["source_revision"]) is not None,
            "Release identity source revision must be a full lowercase SHA-1.")
    for field in ("rollout_manifest_sha256", "provider_policy_sha256"):
        require(re.fullmatch(r"[0-9a-f]{64}", release[field]) is not None,
                f"Release identity {field} must be a lowercase SHA-256.")
    require(release["environment"].strip().lower() not in {"prod", "production"},
            "Day 7 acceptance requires a nonproduction deployment.")
    for field in ("owner_id", "automation_id", "synthetic_account_label"):
        value = first.get(field)
        require(isinstance(value, str) and bool(value.strip()),
                f"Evidence must have a nonblank {field}.")
    identity = ("release", "owner_id", "automation_id", "synthetic_account_label")
    schedule_identity = ("timezone", "schedule", "automation_revision", "run_profile",
                         "output_language", "quiet_hours")
    for index, item in enumerate((first, second), start=1):
        require(item.get("schema_version") == 1
                and item.get("evidence_kind") == "pa10_scheduled_profile"
                and item.get("scenario") == "daily_coworker"
                and item.get("status") == "passed"
                and item.get("run_profile") == "briefing"
                and item.get("run_state") == "completed",
                f"Day {index} is not a passed daily briefing profile probe.")
        require(item.get("new_notification_count") == 2
                and all(item.get(k) for k in ("occurrence_id", "run_id", "started_notification_id",
                                                 "completion_notification_id", "operator_case_reference")),
                f"Day {index} is missing one-run/two-notice evidence.")
        for field in (*identity, *schedule_identity):
            require(item.get(field) == first.get(field), f"Day {index} changed {field}.")
    case_reference = first.get("operator_case_reference")
    require(isinstance(case_reference, str) and bool(case_reference.strip())
            and second.get("operator_case_reference") == case_reference
            and paused.get("operator_case_reference") == case_reference,
            "Both natural-day probes and pause must link the same operator case.")
    for field in identity:
        require(paused.get(field) == first.get(field), f"Pause evidence changed {field}.")
    require(paused.get("status") == "paused"
            and bool(paused.get("operator_case_reference")),
            "Pause evidence must confirm a paused synthetic automation.")
    require(paused.get("previous_revision") == first.get("automation_revision")
            and isinstance(paused.get("paused_revision"), int)
            and paused["paused_revision"] > paused["previous_revision"],
            "Pause must follow the accepted schedule revision.")
    schedule = first.get("schedule")
    require(isinstance(schedule, dict) and schedule.get("kind") == "daily"
            and type(schedule.get("hour")) is int and 0 <= schedule["hour"] <= 23
            and type(schedule.get("minute")) is int and 0 <= schedule["minute"] <= 59,
            "Expected an explicit daily calendar time.")
    try:
        zone = ZoneInfo(str(first.get("timezone", "")))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise GateFailure("Timezone must be a valid IANA zone.") from error
    local_dates: list[date] = []
    due_timestamps: list[datetime] = []
    for item in (first, second):
        due = timestamp(item.get("due_at"), "due_at")
        local = due.astimezone(zone)
        require((local.hour, local.minute, local.second) ==
                (schedule["hour"], schedule["minute"], 0),
                "An occurrence was not due at the owner-approved local schedule time.")
        require(timestamp(item.get("prepared_at"), "prepared_at") <= due
                <= timestamp(item.get("verified_at"), "verified_at"),
                "Occurrence must happen between its staging preparation and verification.")
        due_timestamps.append(due)
        local_dates.append(local.date())
    require(local_dates[1] == local_dates[0] + timedelta(days=1)
            and due_timestamps[1] > due_timestamps[0],
            "Expected consecutive *local calendar days*, not two same-day triggers.")
    for field in ("occurrence_id", "run_id", "started_notification_id", "completion_notification_id"):
        require(first.get(field) != second.get(field), f"Both days reused {field}.")
    docs_first = strings(first.get("document_ids"), "Day 7 source documents")
    docs_second = strings(second.get("document_ids"), "Day 8 source documents")
    require(set(docs_first) == set(docs_second), "The authorized document set changed between days.")
    pins_first = strings(first.get("input_version_ids"), "Day 7 immutable source pins")
    pins_second = strings(second.get("input_version_ids"), "Day 8 immutable source pins")
    require(len(pins_first) == len(docs_first) == len(pins_second),
            "Every authorized source must have exactly one pinned version per run.")
    require(pins_first == strings(second.get("prior_run_input_version_ids"),
                                  "Day 8 recheck of Day 7 source pins"),
            "Day 7 original source versions changed or were not rechecked on Day 8.")
    require(set(pins_first) != set(pins_second),
            "No source version changed between the two days.")
    require(timestamp(paused.get("paused_at"), "paused_at") >=
            timestamp(second.get("verified_at"), "Day 8 verified_at"),
            "Pause was not performed after Day 8 verification.")
    return {
        "status": "passed", "scenario": "day7_two_day_daily_briefing",
        "release": first["release"], "owner_id": first["owner_id"],
        "automation_id": first["automation_id"], "timezone": first["timezone"],
        "scheduled_local_dates": [str(item) for item in local_dates],
        "first_occurrence_id": first["occurrence_id"],
        "second_occurrence_id": second["occurrence_id"],
        "first_run_id": first["run_id"], "second_run_id": second["run_id"],
        "document_ids": docs_first,
        "first_input_version_ids": pins_first, "second_input_version_ids": pins_second,
        "paused_revision": paused["paused_revision"],
        "operator_case_references": [first["operator_case_reference"],
                                     second["operator_case_reference"],
                                     paused["operator_case_reference"]],
        "limitation": "Schedule provenance still requires independent Temporal natural-timer logs.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--pause", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_two_day(load_json(args.first, "first day"),
                                load_json(args.second, "second day"),
                                load_json(args.pause, "pause"))
    except (GateFailure, OSError, ValueError) as error:
        parser.exit(1, f"Day 7 two-day evidence rejected: {error}\n")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "output": str(args.output),
                      "natural_timer_provenance": "requires independent Temporal logs"}))


if __name__ == "__main__":
    main()