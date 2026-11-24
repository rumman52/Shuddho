"""Read-only owner-scoped post-pause scheduled-opportunity collector for Day 7/8.

This does not operate a Temporal schedule, synthesize a firing, or prove downstream
transport delivery. Independent Temporal/notification transport logs remain mandatory.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from scripts.staging_day7_two_day_gate import (
    GateFailure,
    next_paused_opportunity,
    verify_two_day,
    write_private_report,
)
from scripts.staging_pa10_scheduled_profile import (
    ScheduledProfileProbeFailure,
    auth,
    clean_origin,
    env,
    json_object,
    load_json,
    release_identity,
    require_guard,
    require_prepared_daily_profile,
    utcnow_iso,
)


def _ids(rows: object, field: str, label: str) -> set[str]:
    if not isinstance(rows, list):
        raise ScheduledProfileProbeFailure(f"{label} endpoint returned an invalid list.")
    if any(not isinstance(item, dict)
           or not isinstance(item.get(field), str) or not item[field]
           for item in rows):
        raise ScheduledProfileProbeFailure(f"{label} endpoint returned incomplete identities.")
    result = {item[field] for item in rows}
    if len(result) != len(rows):
        raise ScheduledProfileProbeFailure(f"{label} endpoint returned duplicate identities.")
    return result


def _baseline(paused: dict, field: str) -> set[str]:
    raw = paused.get(field)
    if (not isinstance(raw, list) or not raw
            or any(not isinstance(x, str) or not x for x in raw)
            or len(set(raw)) != len(raw)):
        raise ScheduledProfileProbeFailure(f"Missing or malformed {field}.")
    return set(raw)


def write_private_paused_evidence(path: Path, evidence: dict) -> None:
    """Commit sensitive post-pause operator evidence atomically with mode 0600.

    The two-day gate's private writer uses a same-directory temporary file
    and os.replace, so existing symlinks are replaced rather than followed.
    Never expose filesystem paths or sensitive payloads in CLI errors.
    """
    try:
        write_private_report(path, evidence)
    except OSError as error:
        raise ScheduledProfileProbeFailure(
            f"Could not commit private paused-opportunity evidence: {type(error).__name__}."
        ) from None


def collect_paused_opportunity(args: argparse.Namespace) -> dict:
    """Reject a prematurely observed or nonzero paused daily opportunity."""
    require_guard()
    first = load_json(args.first_evidence, "Day 7 daily briefing receipt")
    second = load_json(args.second_evidence, "Day 8 daily briefing receipt")
    paused = load_json(args.pause_evidence, "Day 8 applied-pause receipt")
    case_ref = args.operator_case_reference.strip()
    if not case_ref or paused.get("operator_case_reference") != case_ref:
        raise ScheduledProfileProbeFailure("Operator case does not match paused routine.")
    try:
        verify_two_day(first, second, paused, require_paused_opportunity=False)
        due = next_paused_opportunity(first, second)
    except GateFailure as error:
        raise ScheduledProfileProbeFailure(f"Pre-pause evidence rejected: {error}") from None

    catchup = first["catchup_window_seconds"]
    if datetime.now(timezone.utc) < due + timedelta(seconds=catchup):
        raise ScheduledProfileProbeFailure(
            "Next local scheduled opportunity and full catch-up window have not elapsed."
        )
    if env("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL").strip() != first["synthetic_account_label"]:
        raise ScheduledProfileProbeFailure("Synthetic account label changed after pause.")

    origin = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    automation_id = paused["automation_id"]
    baseline_occurrences = _baseline(paused, "pause_baseline_occurrence_ids")
    baseline_runs = _baseline(paused, "pause_baseline_run_ids")
    baseline_notices = _baseline(paused, "pause_baseline_notification_ids")

    with httpx.Client(base_url=origin, timeout=20, follow_redirects=False) as client:
        release = release_identity(client, token, args.rollout, args.provider_policy_plan)
        if release != first["release"]:
            raise ScheduledProfileProbeFailure("Deployed release changed since Day 7.")
        me = json_object(client.get("/api/v1/me", headers=auth(token)), "synthetic owner")
        if me.get("account_id") != first["owner_id"]:
            raise ScheduledProfileProbeFailure("Paused automation owner identity changed.")
        current = json_object(
            client.get(f"/api/v1/automations/{automation_id}", headers=auth(token)),
            "paused synthetic automation",
        )
        # Once paused, the live schedule must still carry the seven exact
        # owner-approved settings. Do not silently accept a changed briefing
        # profile merely because the scheduler is disabled and counts are zero.
        require_prepared_daily_profile(first, current)
        if (current.get("id") != automation_id
                or current.get("state") != "paused"
                or current.get("revision") != paused["paused_revision"]
                or current.get("schedule_applied_revision") != paused["paused_revision"]
                or current.get("schedule_applied_enabled") is not False
                or current.get("schedule_error_code")
                or current.get("schedule") != first["schedule"]
                or current.get("timezone") != first["timezone"]
                or current.get("overlap_policy") != first["overlap_policy"]
                or current.get("catchup_window_seconds") != catchup
                or current.get("expires_at") != first["expires_at"]
                or current.get("goal_id") != first["goal_id"]
                or current.get("goal_revision") != first["goal_revision"]):
            raise ScheduledProfileProbeFailure(
                "Paused automation state/schedule/goal differs from approved Day 7 identity."
            )
        history = json_object(
            client.get(f"/api/v1/automations/{automation_id}/history",
                       headers=auth(token)), "paused automation occurrence history",
        ).get("history")
        notices = json_object(
            client.get("/api/v1/notifications", headers=auth(token)),
            "paused owner notification inbox",
        ).get("notifications")
        if not isinstance(history, list) or not isinstance(notices, list):
            raise ScheduledProfileProbeFailure("Owner-scoped history/notification lists are unavailable.")
        new_history_ids = _ids(history, "occurrence_id", "automation history")
        new_run_ids = {
            row["run_id"] for row in history if isinstance(row.get("run_id"), str)
            and row["run_id"]
        }
        if any(row.get("run_id") is not None
               and (not isinstance(row.get("run_id"), str) or not row["run_id"])
               for row in history):
            raise ScheduledProfileProbeFailure("Automation history has invalid run identities.")
        own_notices = [item for item in notices if isinstance(item, dict)
                       and item.get("automation_id") == automation_id]
        if any(not isinstance(item, dict) for item in notices):
            raise ScheduledProfileProbeFailure("Notification endpoint returned invalid records.")
        new_notice_ids = _ids(own_notices, "id", "automation notifications")

        if (not baseline_occurrences.issubset(new_history_ids)
                or not baseline_runs.issubset(new_run_ids)
                or not baseline_notices.issubset(new_notice_ids)):
            raise ScheduledProfileProbeFailure(
                "Owner-scoped baseline disappeared; history may be truncated or replaced."
            )
        observed_at = utcnow_iso()
        observation = {
            "due_at": due.isoformat(), "observed_at": observed_at,
            "new_occurrence_count": len(new_history_ids - baseline_occurrences),
            "new_run_count": len(new_run_ids - baseline_runs),
            "new_notification_count": len(new_notice_ids - baseline_notices),
            "owner_id": first["owner_id"], "automation_id": automation_id,
            "release": release, "automation_state": current["state"],
            "schedule_applied_revision": current["schedule_applied_revision"],
            "schedule_applied_enabled": current["schedule_applied_enabled"],
            "operator_case_reference": case_ref,
        }
        complete = {**paused, "post_pause_observation": observation}
        try:
            verify_two_day(first, second, complete)
        except GateFailure as error:
            raise ScheduledProfileProbeFailure(
                f"Post-pause scheduled opportunity did not qualify: {error}"
            ) from None
    write_private_paused_evidence(args.output, complete)
    return complete


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--provider-policy-plan", type=Path, required=True)
    parser.add_argument("--first-evidence", type=Path, required=True)
    parser.add_argument("--second-evidence", type=Path, required=True)
    parser.add_argument("--pause-evidence", type=Path, required=True)
    parser.add_argument("--operator-case-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = collect_paused_opportunity(args)
    except (httpx.HTTPError, ScheduledProfileProbeFailure, OSError) as error:
        parser.exit(1, f"Post-pause staged observation blocked: {error}\n")
    print(json.dumps({
        "status": "passed", "output": str(args.output),
        "automation_id": receipt["automation_id"],
        "post_pause_opportunity_due_at": receipt["post_pause_observation"]["due_at"],
        "independent_temporal_and_delivery_proof": "still required",
    }))


if __name__ == "__main__":
    main()
