"""Fail-closed reconciliation of *two real-day* PA-10 daily briefing probes.

An operator must separately prove from Temporal server logs that occurrences were
natural timer firings, not manual triggers. API history alone cannot prove origin.
This file cannot schedule, backfill, or synthesize either occurrence.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, time, timedelta, timezone
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


def next_paused_opportunity(first: dict, second: dict) -> datetime:
    """Compute the next *local calendar* due time after Day 8, including DST."""
    schedule = first.get("schedule")
    require(isinstance(schedule, dict)
            and type(schedule.get("hour")) is int
            and type(schedule.get("minute")) is int
            and 0 <= schedule["hour"] <= 23 and 0 <= schedule["minute"] <= 59,
            "Cannot calculate the next paused schedule opportunity.")
    require(first.get("overlap_policy") == "skip",
            "Daily briefing must use the approved skip overlap policy.")
    catchup = first.get("catchup_window_seconds")
    require(type(catchup) is int and 60 <= catchup <= 86400,
            "Daily briefing requires an explicit bounded catch-up window.")
    try:
        zone = ZoneInfo(str(first.get("timezone", "")))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise GateFailure("Cannot calculate a paused opportunity without a valid timezone.") from error
    next_local_date = timestamp(second.get("due_at"), "Day 8 due_at").astimezone(zone).date() + timedelta(days=1)
    local_due = datetime.combine(next_local_date,
                                 time(schedule["hour"], schedule["minute"]), tzinfo=zone)
    due = local_due.astimezone(timezone.utc)
    require(due.astimezone(zone).replace(tzinfo=None) == local_due.replace(tzinfo=None),
            "The next local scheduled time is nonexistent in the owner's timezone.")
    return due


def verify_two_day(
    first: dict, second: dict, paused: dict, *, require_paused_opportunity: bool = True,
) -> dict:
    """Check two daily runs and, by default, a later zero-admission pause opportunity."""
    now = datetime.now(timezone.utc)
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
    goal_id = first.get("goal_id")
    goal_revision = first.get("goal_revision")
    require(isinstance(goal_id, str) and bool(goal_id.strip())
            and type(goal_revision) is int and goal_revision >= 1,
            "Daily briefing must identify one owner-approved goal and revision.")
    project_id = first.get("project_id")
    require(isinstance(project_id, str) and bool(project_id.strip()),
            "Daily briefing must identify one owner-approved project.")
    identity = ("release", "owner_id", "automation_id", "synthetic_account_label",
                "goal_id", "goal_revision", "project_id", "authorized_document_ids",
                "expires_at")
    schedule_identity = ("timezone", "schedule", "automation_revision", "run_profile",
                         "output_language", "quiet_hours", "overlap_policy",
                         "catchup_window_seconds", "schedule_applied_revision",
                         "schedule_applied_enabled")
    for index, item in enumerate((first, second), start=1):
        require(item.get("schema_version") == 2
                and item.get("evidence_kind") == "pa10_scheduled_profile"
                and item.get("scenario") == "daily_coworker"
                and item.get("status") == "passed"
                and item.get("run_profile") == "briefing"
                and item.get("run_state") == "completed",
                f"Day {index} is not a passed daily briefing profile probe.")
        require(type(item.get("new_notification_count")) is int
                and item.get("new_notification_count") == 1
                and all(item.get(k) for k in ("occurrence_id", "run_id",
                                                 "completion_notification_id", "operator_case_reference"))
                and "started_notification_id" not in item,
                f"Day {index} is missing one-run/one-completion-notice evidence.")
        revision = item.get("automation_revision")
        require(type(revision) is int and revision >= 1,
                f"Day {index} must identify a valid accepted automation revision.")
        require(item.get("schedule_applied_revision") == revision
                and item.get("schedule_applied_enabled") is True,
                f"Day {index} must prove the current Temporal schedule revision is active.")
        expiry = timestamp(item.get("expires_at"), f"Day {index} expires_at")
        require(expiry > timestamp(item.get("due_at"), f"Day {index} due_at"),
                f"Day {index} occurrence must precede the approved schedule expiry.")
        for field in (*identity, *schedule_identity):
            require(item.get(field) == first.get(field), f"Day {index} changed {field}.")
    # One completion notice is persisted per occurrence; consecutive natural
    # occurrences must therefore carry two different notification IDs.
    notice_ids = [item.get("completion_notification_id") for item in (first, second)]
    require(all(isinstance(value, str) and bool(value.strip()) for value in notice_ids)
            and len(notice_ids) == 2 and len(notice_ids) == len(set(notice_ids)),
            "Both days must have two distinct nonblank completion notification IDs.")
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
    require(paused.get("schedule_applied_revision") == paused.get("paused_revision")
            and paused.get("schedule_applied_enabled") is False,
            "Pause evidence must prove Temporal applied the paused revision.")
    require(type(paused.get("previous_revision")) is int
            and paused["previous_revision"] == first["automation_revision"]
            and type(paused.get("paused_revision")) is int
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
    verified_timestamps: list[datetime] = []
    for item in (first, second):
        due = timestamp(item.get("due_at"), "due_at")
        local = due.astimezone(zone)
        require((local.hour, local.minute, local.second) ==
                (schedule["hour"], schedule["minute"], 0),
                "An occurrence was not due at the owner-approved local schedule time.")
        verified = timestamp(item.get("verified_at"), "verified_at")
        require(timestamp(item.get("prepared_at"), "prepared_at") <= due <= verified <= now,
                "Occurrence must be prepared and verified in order by the current time.")
        due_timestamps.append(due)
        verified_timestamps.append(verified)
        local_dates.append(local.date())
    require(timestamp(second.get("prepared_at"), "Day 8 prepared_at") > verified_timestamps[0],
            "Day 8 baseline must be prepared after Day 7 verification.")
    require(local_dates[1] == local_dates[0] + timedelta(days=1)
            and due_timestamps[1] > due_timestamps[0],
            "Expected consecutive *local calendar days*, not two same-day triggers.")
    for field in ("occurrence_id", "run_id", "completion_notification_id"):
        require(first.get(field) != second.get(field), f"Both days reused {field}.")
    docs_first = strings(first.get("document_ids"), "Day 7 source documents")
    docs_second = strings(second.get("document_ids"), "Day 8 source documents")
    approved = strings(first.get("authorized_document_ids"), "Owner-approved goal document scope")
    require(len(approved) <= 5 and set(docs_first) == set(docs_second) == set(approved)
            and len(docs_first) == len(approved),
            "Both daily Agent runs must use exactly the owner-approved goal documents.")
    pins_first = strings(first.get("input_version_ids"), "Day 7 immutable source pins")
    pins_second = strings(second.get("input_version_ids"), "Day 8 immutable source pins")
    require(len(pins_first) == len(docs_first) == len(pins_second),
            "Every authorized source must have exactly one pinned version per run.")
    require(pins_first == strings(second.get("prior_run_input_version_ids"),
                                  "Day 8 recheck of Day 7 source pins"),
            "Day 7 original source versions changed or were not rechecked on Day 8.")
    # Version vectors are aligned to each day's document order, which may
    # differ. Only one owner-authorized document may change between firings.
    first_versions = dict(zip(docs_first, pins_first))
    second_versions = dict(zip(docs_second, pins_second))
    changed_document_ids = [
        document_id for document_id in docs_first
        if first_versions[document_id] != second_versions[document_id]
    ]
    require(len(changed_document_ids) == 1,
            "Exactly one authorized document must have a changed pinned version.")
    paused_at = timestamp(paused.get("paused_at"), "paused_at")
    require(verified_timestamps[1] <= paused_at <= now,
            "Pause must be observed after Day 8 verification and by the current time.")
    require(timestamp(first.get("expires_at"), "expires_at") > paused_at,
            "The approved schedule expiry must remain after the Day 8 pause.")
    post_due = next_paused_opportunity(first, second)
    catchup = first.get("catchup_window_seconds")
    require(type(catchup) is int and 60 <= catchup <= 86400,
            "Daily briefing requires an explicit bounded catch-up window.")
    require(verified_timestamps[1] < paused_at < post_due,
            "Pause must occur after Day 8 verification and before the next scheduled opportunity.")
    require(timestamp(first.get("expires_at"), "expires_at") > post_due,
            "An expired schedule cannot establish a later paused opportunity.")
    observation = None
    if require_paused_opportunity:
        for field, expected in (
            ("pause_baseline_occurrence_ids", (first["occurrence_id"], second["occurrence_id"])),
            ("pause_baseline_run_ids", (first["run_id"], second["run_id"])),
            ("pause_baseline_notification_ids",
             (first["completion_notification_id"], second["completion_notification_id"])),
        ):
            baseline = strings(paused.get(field), field)
            require(set(expected).issubset(baseline),
                    f"{field} must retain both actual daily receipts before pause.")
        observation = paused.get("post_pause_observation")
        require(isinstance(observation, dict),
                "Post-pause scheduled-opportunity observation is required before qualification.")
        require(timestamp(observation.get("due_at"), "post-pause opportunity due_at") == post_due,
                "Post-pause observation does not match the next approved local schedule due time.")
        observed_at = timestamp(observation.get("observed_at"), "post-pause observed_at")
        require(post_due + timedelta(seconds=catchup) <= observed_at <= now,
                "Post-pause observation must follow the entire catch-up window and precede now.")
        require(observation.get("automation_state") == "paused"
                and observation.get("schedule_applied_revision") == paused["paused_revision"]
                and observation.get("schedule_applied_enabled") is False
                and observation.get("owner_id") == first["owner_id"]
                and observation.get("automation_id") == first["automation_id"]
                and observation.get("release") == first["release"]
                and observation.get("operator_case_reference") == case_reference,
                "Post-pause observation changed owner/release, revision, schedule or operator case.")
        for field in ("new_occurrence_count", "new_run_count", "new_notification_count"):
            require(type(observation.get(field)) is int and observation[field] == 0,
                    f"Post-pause {field} must be exactly zero.")
    return {
        "status": "passed" if require_paused_opportunity else "preflight_only",
        "scenario": "day7_two_day_daily_briefing",
        "release": first["release"], "owner_id": first["owner_id"],
        "automation_id": first["automation_id"], "project_id": first["project_id"],
        "expires_at": first["expires_at"],
        "schedule_applied_revision": first["schedule_applied_revision"],
        "timezone": first["timezone"],
        "scheduled_local_dates": [str(item) for item in local_dates],
        "first_occurrence_id": first["occurrence_id"],
        "second_occurrence_id": second["occurrence_id"],
        "first_run_id": first["run_id"], "second_run_id": second["run_id"],
        "document_ids": docs_first,
        "first_input_version_ids": pins_first, "second_input_version_ids": pins_second,
        "changed_document_id": changed_document_ids[0],
        "paused_revision": paused["paused_revision"],
        "paused_opportunity_due_at": post_due.isoformat(),
        "post_pause_observed_at": observation["observed_at"] if observation else None,
        "post_pause_zero_admissions_verified": observation is not None,
        "operator_case_references": [first["operator_case_reference"],
                                     second["operator_case_reference"],
                                     paused["operator_case_reference"]],
        "limitation": "Natural timer provenance and downstream delivery absence still require independent Temporal and transport logs.",
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
