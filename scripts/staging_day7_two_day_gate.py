"""Fail-closed reconciliation of *two real-day* PA-10 daily briefing probes.

An operator must separately prove from Temporal server logs that occurrences were
natural timer firings, not manual triggers. API history alone cannot prove origin.
This file cannot schedule, backfill, or synthesize either occurrence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
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


def require_daily_calendar(profile: dict) -> tuple[dict, ZoneInfo]:
    """Validate the exact Day 7 pilot policy, not general automation settings."""
    require(isinstance(profile, dict), "Daily briefing requires a policy object.")
    schedule = profile.get("schedule")
    require(isinstance(schedule, dict) and schedule.get("kind") == "daily"
            and type(schedule.get("hour")) is int and 0 <= schedule["hour"] <= 23
            and type(schedule.get("minute")) is int and 0 <= schedule["minute"] <= 59,
            "Expected an explicit daily calendar time.")
    # A matching first/second schedule is not a valid daily schedule if it
    # could not have been accepted by AutomationSchedule. For kind=daily the
    # runtime schema requires an explicit *empty* weekdays array.
    require(type(schedule.get("weekdays")) is list and schedule["weekdays"] == [],
            "Day 7 daily schedule requires an empty weekdays list.")
    require(set(schedule) == {"kind", "hour", "minute", "weekdays"},
            "Day 7 daily schedule contains unexpected fields.")
    # The owner-approved quiet-hours policy must be a real QuietHours value,
    # not just an arbitrary matching object copied between two probe files.
    quiet_hours = profile.get("quiet_hours")
    require(isinstance(quiet_hours, dict)
            and set(quiet_hours) == {"start", "end"}
            and all(type(quiet_hours[field]) is str
                    and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", quiet_hours[field])
                    for field in ("start", "end"))
            and quiet_hours["start"] != quiet_hours["end"],
            "Day 7 quiet hours must have distinct valid HH:MM start/end values.")
    require(profile.get("overlap_policy") == "skip",
            "Daily briefing must use the approved skip overlap policy.")
    catchup = profile.get("catchup_window_seconds")
    require(type(catchup) is int and catchup == 3600,
            "Daily briefing requires an explicit bounded catch-up window of exactly 3600 seconds.")
    zone_name = profile.get("timezone")
    require(type(zone_name) is str and 1 <= len(zone_name) <= 64,
            "Timezone must be a valid IANA zone.")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise GateFailure("Timezone must be a valid IANA zone.") from error
    return schedule, zone


def next_paused_opportunity(first: dict, second: dict) -> datetime:
    """Compute the next *local calendar* due time after Day 8, including DST."""
    schedule, zone = require_daily_calendar(first)
    next_local_date = timestamp(second.get("due_at"), "Day 8 due_at").astimezone(zone).date() + timedelta(days=1)
    local_due = datetime.combine(next_local_date,
                                 time(schedule["hour"], schedule["minute"]), tzinfo=zone)
    due = local_due.astimezone(timezone.utc)
    require(due.astimezone(zone).replace(tzinfo=None) == local_due.replace(tzinfo=None),
            "The next local scheduled time is nonexistent in the owner's timezone.")
    # A repeated fall-back civil time has TWO valid UTC instants. Choosing
    # Python's default fold=0 would silently assert an offset that the real
    # Temporal scheduler has not independently supplied. Fail closed instead
    # of treating one guessed due instant as proof of a paused opportunity.
    require(local_due.utcoffset() == local_due.replace(fold=1).utcoffset(),
            "The next local scheduled time is ambiguous across a DST fold.")
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
        require(type(item.get("schema_version")) is int
                and item["schema_version"] == 2
                and item.get("evidence_kind") == "pa10_scheduled_profile"
                and item.get("scenario") == "daily_coworker"
                and item.get("status") == "passed"
                and item.get("run_profile") == "briefing"
                and item.get("run_state") == "completed",
                f"Day {index} is not a passed daily briefing profile probe.")
        for count_field, description in (
            ("new_occurrence_count", "one new occurrence"),
            ("new_run_count", "one new run"),
        ):
            require(
                type(item.get(count_field)) is int and item[count_field] == 1,
                f"Day {index} must prove {description} for the scheduled date.",
            )
        require(type(item.get("new_notification_count")) is int
                and item.get("new_notification_count") == 1
                and all(item.get(k) for k in ("occurrence_id", "run_id",
                                                 "completion_notification_id", "operator_case_reference"))
                and "started_notification_id" not in item,
                f"Day {index} is missing one-run/one-completion-notice evidence.")
        # Truthy numbers, containers and whitespace aliases are not durable IDs.
        # Check before the preflight can authorize a pause POST, not only when
        # the final receipt supplies baseline identity lists.
        require(all(type(item.get(field)) is str and bool(item[field].strip())
                    and item[field] == item[field].strip()
                    for field in ("occurrence_id", "run_id", "completion_notification_id")),
                f"Day {index} requires canonical nonblank occurrence/run/completion IDs.")
        require(type(item.get("goal_revision")) is int and item["goal_revision"] == goal_revision,
                f"Day {index} changed the owner-approved goal revision.")
        revision = item.get("automation_revision")
        require(type(revision) is int and revision >= 1,
                f"Day {index} must identify a valid accepted automation revision.")
        require(type(item.get("schedule_applied_revision")) is int
                and item["schedule_applied_revision"] == revision
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
    require(type(paused.get("goal_revision")) is int and paused["goal_revision"] == goal_revision,
            "Pause evidence changed goal_revision.")
    for field in identity:
        require(paused.get(field) == first.get(field), f"Pause evidence changed {field}.")
    require(paused.get("status") == "paused"
            and bool(paused.get("operator_case_reference")),
            "Pause evidence must confirm a paused synthetic automation.")
    require(type(paused.get("schedule_applied_revision")) is int
            and paused["schedule_applied_revision"] == paused.get("paused_revision")
            and paused.get("schedule_applied_enabled") is False,
            "Pause evidence must prove Temporal applied the paused revision.")
    require(type(paused.get("previous_revision")) is int
            and paused["previous_revision"] == first["automation_revision"]
            and type(paused.get("paused_revision")) is int
            and paused["paused_revision"] == paused["previous_revision"] + 1,
            "Pause must follow the accepted schedule revision.")
    schedule, zone = require_daily_calendar(first)
    # Matching numeric values may have different JSON types (8 == 8.0).
    require_daily_calendar(second)
    local_dates: list[date] = []
    due_timestamps: list[datetime] = []
    verified_timestamps: list[datetime] = []
    for item in (first, second):
        due = timestamp(item.get("due_at"), "due_at")
        local = due.astimezone(zone)
        require((local.hour, local.minute, local.second, local.microsecond) ==
                (schedule["hour"], schedule["minute"], 0, 0),
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
    # A changed version is not proof that the owner edited the source in the
    # interval. This receipt is operator-supplied; its underlying audit record
    # must still be independently authenticated outside this shape validator.
    edit = second.get("authorized_source_edit")
    required_edit_fields = {
        "owner_id", "project_id", "document_id", "previous_version_id",
        "current_version_id", "edited_at", "operator_case_reference",
        "evidence_sha256",
    }
    require(isinstance(edit, dict) and set(edit) == required_edit_fields,
            "Day 8 authorized document edit receipt is missing or has unexpected fields.")
    require(edit["owner_id"] == first["owner_id"]
            and edit["project_id"] == first["project_id"]
            and edit["operator_case_reference"] == case_reference
            and edit["document_id"] == changed_document_ids[0],
            "Authorized document edit receipt changed owner, project, case or document.")
    edited_document = changed_document_ids[0]
    require(edit["previous_version_id"] == first_versions[edited_document]
            and edit["current_version_id"] == second_versions[edited_document],
            "Authorized document edit receipt does not match immutable source pins.")
    require(isinstance(edit["evidence_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", edit["evidence_sha256"]) is not None,
            "Authorized document edit receipt requires a source-evidence SHA-256.")
    edited_at = timestamp(edit["edited_at"], "authorized document edited_at")
    require(verified_timestamps[0] < edited_at < due_timestamps[1],
            "Authorized document edit must follow Day 7 verification and precede Day 8 due time.")
    paused_at = timestamp(paused.get("paused_at"), "paused_at")
    require(verified_timestamps[1] <= paused_at <= now,
            "Pause must be observed after Day 8 verification and by the current time.")
    require(timestamp(first.get("expires_at"), "expires_at") > paused_at,
            "The approved schedule expiry must remain after the Day 8 pause.")
    post_due = next_paused_opportunity(first, second)
    catchup = first["catchup_window_seconds"]
    require(verified_timestamps[1] < paused_at < post_due,
            "Pause must occur after Day 8 verification and before the next scheduled opportunity.")
    require(timestamp(first.get("expires_at"), "expires_at")
            > post_due + timedelta(seconds=catchup),
            "Schedule expiry must remain beyond the paused opportunity and catch-up window.")
    observation = None
    if require_paused_opportunity:
        for field, expected in (
            ("pause_baseline_occurrence_ids", (first["occurrence_id"], second["occurrence_id"])),
            ("pause_baseline_run_ids", (first["run_id"], second["run_id"])),
            ("pause_baseline_notification_ids",
             (first["completion_notification_id"], second["completion_notification_id"])),
        ):
            baseline = strings(paused.get(field), field)
            require(set(baseline) == set(expected),
                    f"{field} baseline must contain exactly both actual daily receipts, "
                    "without an extra occurrence, run or notification before pause.")
        observation = paused.get("post_pause_observation")
        require(isinstance(observation, dict),
                "Post-pause scheduled-opportunity observation is required before qualification.")
        require(timestamp(observation.get("due_at"), "post-pause opportunity due_at") == post_due,
                "Post-pause observation does not match the next approved local schedule due time.")
        observed_at = timestamp(observation.get("observed_at"), "post-pause observed_at")
        require(post_due + timedelta(seconds=catchup) <= observed_at <= now,
                "Post-pause observation must follow the entire catch-up window and precede now.")
        require(observation.get("automation_state") == "paused"
                and type(observation.get("schedule_applied_revision")) is int
                and observation["schedule_applied_revision"] == paused["paused_revision"]
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
        "authorized_source_edit": {
            "edited_at": edit["edited_at"],
            "previous_version_id": edit["previous_version_id"],
            "current_version_id": edit["current_version_id"],
            "evidence_sha256": edit["evidence_sha256"],
        },
        "paused_revision": paused["paused_revision"],
        "paused_opportunity_due_at": post_due.isoformat(),
        "post_pause_observed_at": observation["observed_at"] if observation else None,
        "post_pause_zero_admissions_verified": observation is not None,
        # Keep the actual local calendar date AND UTC offset for every observed
        # receipt. Do not replace the owner's IANA time zone with a fixed offset
        # or synthesize a post-pause observation during the preflight-only step.
        "owner_local_receipts": {
            "day7_due_at": due_timestamps[0].astimezone(zone).isoformat(),
            "day7_verified_at": verified_timestamps[0].astimezone(zone).isoformat(),
            "day8_due_at": due_timestamps[1].astimezone(zone).isoformat(),
            "day8_verified_at": verified_timestamps[1].astimezone(zone).isoformat(),
            "source_edited_at": edited_at.astimezone(zone).isoformat(),
            "paused_at": paused_at.astimezone(zone).isoformat(),
            "post_pause_due_at": post_due.astimezone(zone).isoformat(),
            "post_pause_observed_at": (
                timestamp(observation["observed_at"], "post-pause observed_at")
                .astimezone(zone).isoformat() if observation else None
            ),
        },
        "operator_case_references": [first["operator_case_reference"],
                                     second["operator_case_reference"],
                                     paused["operator_case_reference"]],
        "limitation": "Natural timer provenance and downstream delivery absence still require independent Temporal and transport logs.",
    }


def write_private_report(path: Path, report: dict) -> None:
    """Atomically replace restricted operator evidence without following output links.

    The report contains owner, automation, run, document and source-version IDs.
    A normal Path.write_text creates a potentially world-readable file under a
    022 umask and follows preexisting symlinks. mkstemp creates mode 0600; an
    os.replace in the same directory changes the directory entry atomically.
    """
    encoded = json.dumps(report, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".", dir=str(path.parent),
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


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
    try:
        write_private_report(args.output, report)
    except OSError as error:
        # Do not print private report contents, paths or exception arguments.
        parser.exit(1, f"Day 7 private operator report could not be committed: {type(error).__name__}.\n")
    print(json.dumps({"status": "passed", "output": str(args.output),
                      "natural_timer_provenance": "requires independent Temporal logs"}))


if __name__ == "__main__":
    main()
