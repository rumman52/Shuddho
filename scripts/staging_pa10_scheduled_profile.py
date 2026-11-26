from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

if __package__:
    from .staging_prerequisite_preflight import PreflightFailure, _validate_https_endpoint
else:
    from staging_prerequisite_preflight import PreflightFailure, _validate_https_endpoint


STATE_SCHEMA_VERSION = 1
LEGACY_PROFILE_EVIDENCE_SCHEMA_VERSION = 1
BRIEFING_EVIDENCE_SCHEMA_VERSION = 2
PRODUCTION_NAMES = {"prod", "production"}
SCENARIOS = {
    "daily_coworker": {"profile": "briefing", "schedule": {"daily"}},
    "weekly_coworker": {"profile": "briefing", "schedule": {"weekly"}},
    "deadline_coworker": {"profile": "deadline", "schedule": {"daily", "weekly"}},
    "goal_driven_proactivity": {"profile": "proactive", "schedule": {"daily", "weekly"}},
}


class ScheduledProfileProbeFailure(RuntimeError):
    pass


def require_one_completion_notification(notices: object) -> dict:
    """Require one persisted owner notification for a completed briefing occurrence."""
    if not isinstance(notices, list) or len(notices) != 1:
        raise ScheduledProfileProbeFailure(
            "Expected exactly one completion notification for the scheduled occurrence."
        )
    notice = notices[0]
    if (
        not isinstance(notice, dict)
        or not isinstance(notice.get("id"), str)
        or not notice["id"].strip()
        or notice.get("kind") != "automation_completed"
    ):
        raise ScheduledProfileProbeFailure(
            "Expected exactly one completion notification for the scheduled occurrence."
        )
    return notice


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_future_expiry(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScheduledProfileProbeFailure("Recurring briefing must have an explicit expiry.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ScheduledProfileProbeFailure("Recurring briefing expiry is not a valid ISO timestamp.") from None
    if parsed.tzinfo is None or parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise ScheduledProfileProbeFailure("Recurring briefing expiry must be a future timezone-aware timestamp.")
    return value


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES", "").lower() != "true":
        raise ScheduledProfileProbeFailure(
            "Set SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES=true only in approved controlled staging."
        )
    if os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true":
        raise ScheduledProfileProbeFailure(
            "Set SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true only for a synthetic staging account."
        )


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ScheduledProfileProbeFailure(f"{name} is required.")
    return value


def clean_origin(value: str) -> str:
    # Enforce the shared public-host/control-character/port checks *before*
    # sending the synthetic owner's bearer token to the staging API.
    try:
        _validate_https_endpoint(value, "SHUDDHO_STAGING_API_BASE_URL")
    except PreflightFailure as error:
        raise ScheduledProfileProbeFailure(str(error)) from None
    parsed = urlparse(value)
    if parsed.path not in {"", "/"} or "?" in value or "#" in value:
        raise ScheduledProfileProbeFailure(
            "SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin."
        )
    return value[:-1] if parsed.path == "/" else value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScheduledProfileProbeFailure(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ScheduledProfileProbeFailure(f"{label} must contain a JSON object.")
    return value


def write_private_evidence(path: Path, evidence: dict) -> None:
    """Persist source/owner/run operator evidence atomically with mode 0600.

    Import the already-tested Day 7 gate writer lazily to avoid a module-load
    cycle: the gate imports load_json from this scheduled-profile module.
    Never expose private filesystem paths or payloads in operator errors.
    """
    if __package__:
        from .staging_day7_two_day_gate import write_private_report
    else:
        from staging_day7_two_day_gate import write_private_report
    try:
        write_private_report(path, evidence)
    except OSError as error:
        raise ScheduledProfileProbeFailure(
            f"Could not commit private operator evidence: {type(error).__name__}."
        ) from None


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def json_object(response: httpx.Response, label: str) -> dict:
    if response.status_code != 200:
        raise ScheduledProfileProbeFailure(
            f"{label} returned HTTP {response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise ScheduledProfileProbeFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ScheduledProfileProbeFailure(f"{label} returned an unexpected shape.")
    return value


def release_identity(
    client: httpx.Client,
    token: str,
    rollout_path: Path,
    provider_policy_path: Path,
) -> dict:
    rollout = load_json(rollout_path, "rollout manifest")
    load_json(provider_policy_path, "provider-policy plan")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ScheduledProfileProbeFailure("Rollout manifest release_id is required.")
    manifest = json_object(
        client.get("/api/v1/runtime-manifest", headers=auth(token)),
        "runtime manifest",
    )
    environment = env("SHUDDHO_STAGING_EXPECTED_ENVIRONMENT").strip()
    if environment.lower() in PRODUCTION_NAMES:
        raise ScheduledProfileProbeFailure(
            "SHUDDHO_STAGING_EXPECTED_ENVIRONMENT must identify non-production."
        )
    if manifest.get("environment") != environment:
        raise ScheduledProfileProbeFailure(
            "Runtime environment does not match the expected staging environment."
        )
    revision = manifest.get("source_revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ScheduledProfileProbeFailure(
            "Runtime manifest must expose a full lowercase source revision."
        )
    capabilities = manifest.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("automations") is not True
        or capabilities.get("personal_goals") is not True
    ):
        raise ScheduledProfileProbeFailure(
            "Automations and personal goals must be enabled in controlled staging."
        )
    deployment_reference = env("SHUDDHO_STAGING_DEPLOYMENT_REFERENCE").strip()
    if not deployment_reference:
        raise ScheduledProfileProbeFailure(
            "SHUDDHO_STAGING_DEPLOYMENT_REFERENCE must not be blank."
        )
    return {
        "release_id": release_id.strip(),
        "source_revision": revision,
        "environment": environment,
        "deployment_reference": deployment_reference,
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "provider_policy_sha256": sha256_file(provider_policy_path),
    }


def load_authorized_daily_scope(client: httpx.Client, token: str, automation: dict) -> dict:
    """Bind the daily briefing's read scope to the current owner-scoped goal."""
    goal_id = automation.get("goal_id")
    revision = automation.get("goal_revision")
    grants = automation.get("connector_read_grant_ids")
    if not isinstance(goal_id, str) or not goal_id.strip() or type(revision) is not int or revision < 1:
        raise ScheduledProfileProbeFailure("Daily briefing automation has no pinned owner goal/revision.")
    if grants != []:
        raise ScheduledProfileProbeFailure("Day 7 permits document-only reads, not connector grants.")
    goal = json_object(client.get(f"/api/v1/goals/{goal_id}", headers=auth(token)),
                       "owner-approved daily briefing goal")
    if (goal.get("id") != goal_id or goal.get("revision") != revision
            or goal.get("state") != "active"):
        raise ScheduledProfileProbeFailure("Owner-approved goal identity/revision/state changed.")
    project_id = goal.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ScheduledProfileProbeFailure(
            "Day 7 goal must be bound to an explicit owner-owned project ID."
        )
    resources = goal.get("authorized_resources")
    if (not isinstance(resources, list) or not 1 <= len(resources) <= 5
            or any(not isinstance(resource, dict)
                   or resource.get("kind") != "document"
                   or not isinstance(resource.get("reference"), str)
                   or not resource["reference"].strip() for resource in resources)):
        raise ScheduledProfileProbeFailure(
            "Day 7 goal must authorize one to five selected documents only."
        )
    documents = [resource["reference"] for resource in resources]
    if len(set(documents)) != len(documents):
        raise ScheduledProfileProbeFailure("Owner-approved goal contains duplicate documents.")
    project = json_object(
        client.get(f"/api/v1/projects/{project_id}", headers=auth(token)),
        "owner-approved briefing project",
    )
    if project.get("id") != project_id:
        raise ScheduledProfileProbeFailure("Owner-approved project identity changed.")
    project_resources = project.get("resources")
    if not isinstance(project_resources, list):
        raise ScheduledProfileProbeFailure("Owner-approved project resources have an unexpected shape.")
    linked_documents = {
        resource.get("resource_id")
        for resource in project_resources
        if isinstance(resource, dict) and resource.get("resource_type") == "document"
        and isinstance(resource.get("resource_id"), str)
    }
    if not set(documents).issubset(linked_documents):
        raise ScheduledProfileProbeFailure(
            "Every approved briefing document must remain linked to the selected project."
        )
    return {"goal_id": goal_id, "goal_revision": revision, "project_id": project_id,
            "authorized_document_ids": documents}


def require_daily_run_scope(document_ids: object, scope: dict) -> None:
    """Reject Agent run document reads outside exactly the pinned goal scope."""
    approved = scope.get("authorized_document_ids")
    if (not isinstance(document_ids, list) or not document_ids
            or any(not isinstance(item, str) or not item.strip() for item in document_ids)
            or len(set(document_ids)) != len(document_ids)
            or not isinstance(approved, list) or document_ids != approved):
        raise ScheduledProfileProbeFailure(
            "Daily briefing Agent run did not use exactly the owner-approved documents."
        )


DAILY_PREPARED_PROFILE_FIELDS = (
    "timezone", "schedule", "run_profile", "output_language",
    "quiet_hours", "overlap_policy", "catchup_window_seconds",
)


def require_daily_policy(profile: dict) -> None:
    """Reject a non-contract pilot policy before preparing or accepting evidence."""
    # The gate imports load_json from this module, so load the shared validator
    # lazily, after both modules have finished initialization.
    if __package__:
        from .staging_day7_two_day_gate import GateFailure, require_daily_calendar
    else:
        from staging_day7_two_day_gate import GateFailure, require_daily_calendar
    try:
        require_daily_calendar(profile)
    except GateFailure as error:
        raise ScheduledProfileProbeFailure(f"Daily briefing policy rejected: {error}") from None


def require_prepared_daily_profile(prepared: dict, automation: dict) -> None:
    """Bind the live scheduled profile to the exact owner-approved snapshot.

    An applied revision alone does not prove the actual daily time, locale,
    quiet hours or delivery policy still matches the reviewed preparation.
    Missing fields fail closed; none are inferred from a prepared receipt.
    """
    if (
        not isinstance(prepared, dict)
        or not isinstance(automation, dict)
        or any(
            field not in prepared
            or field not in automation
            or prepared[field] != automation[field]
            for field in DAILY_PREPARED_PROFILE_FIELDS
        )
    ):
        raise ScheduledProfileProbeFailure(
            "Daily briefing schedule or delivery policy drifted from the prepared owner-approved profile."
        )
    # Equal values are not proof of validity (e.g. 3600.0 == 3600).
    require_daily_policy(prepared)
    require_daily_policy(automation)


def load_owned(
    client: httpx.Client,
    token: str,
    automation_id: str,
    scenario: str,
) -> dict:
    me = json_object(client.get("/api/v1/me", headers=auth(token)), "staging account")
    owner_id = str(me.get("account_id") or "")
    if not owner_id:
        raise ScheduledProfileProbeFailure("Synthetic account has no account_id.")

    payload = json_object(
        client.get("/api/v1/automations", headers=auth(token)),
        "automations",
    )
    if payload.get("enabled") is not True:
        raise ScheduledProfileProbeFailure("Automations are disabled.")
    rows = payload.get("automations")
    if not isinstance(rows, list):
        raise ScheduledProfileProbeFailure("Automation list has an unexpected shape.")
    selected = [
        item for item in rows
        if str(item.get("id") or "") == automation_id and item.get("state") == "active"
    ]
    if len(selected) != 1:
        raise ScheduledProfileProbeFailure(
            "Expected one active owner-scoped automation with the requested id."
        )
    automation = selected[0]
    contract = SCENARIOS[scenario]
    schedule = automation.get("schedule")
    if (
        automation.get("run_profile") != contract["profile"]
        or not isinstance(schedule, dict)
        or schedule.get("kind") not in contract["schedule"]
    ):
        raise ScheduledProfileProbeFailure(
            f"Automation does not match the {scenario} profile/schedule contract."
        )

    if scenario in {"daily_coworker", "weekly_coworker"}:
        require_future_expiry(automation.get("expires_at"))
        if (
            automation.get("schedule_applied_revision") != automation.get("revision")
            or automation.get("schedule_applied_enabled") is not True
            or automation.get("schedule_error_code")
        ):
            raise ScheduledProfileProbeFailure(
                "Temporal worker has not applied the active automation revision."
            )
    daily_scope = (
        load_authorized_daily_scope(client, token, automation)
        if scenario == "daily_coworker" else {}
    )
    history = json_object(
        client.get(f"/api/v1/automations/{automation_id}/history", headers=auth(token)),
        "automation history",
    ).get("history")
    notices = json_object(
        client.get("/api/v1/notifications", headers=auth(token)),
        "notifications",
    ).get("notifications")
    if not isinstance(history, list) or not isinstance(notices, list):
        raise ScheduledProfileProbeFailure(
            "Scheduled-profile evidence endpoints returned an unexpected shape."
        )
    return {
        "owner_id": owner_id,
        "automation": automation,
        "daily_scope": daily_scope,
        "history": history,
        "notifications": notices,
    }


def prepare(args: argparse.Namespace) -> dict:
    require_guard()
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = release_identity(
            client, token, args.rollout, args.provider_policy_plan
        )
        current = load_owned(client, token, args.automation_id, args.scenario)
    if args.scenario == "daily_coworker":
        require_daily_policy(current["automation"])
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "evidence_kind": "pa10_scheduled_profile",
        "scenario": args.scenario,
        "release": release,
        "synthetic_account_label": env(
            "SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL"
        ).strip(),
        "owner_id": current["owner_id"],
        "automation_id": args.automation_id,
        "automation_revision": int(current["automation"]["revision"]),
        "timezone": current["automation"]["timezone"],
        "schedule": current["automation"]["schedule"],
        "run_profile": current["automation"]["run_profile"],
        "output_language": current["automation"]["output_language"],
        "quiet_hours": current["automation"].get("quiet_hours"),
        "overlap_policy": current["automation"].get("overlap_policy"),
        "catchup_window_seconds": current["automation"].get("catchup_window_seconds"),
        "expires_at": current["automation"].get("expires_at"),
        "schedule_applied_revision": current["automation"].get("schedule_applied_revision"),
        "schedule_applied_enabled": current["automation"].get("schedule_applied_enabled"),
        **current["daily_scope"],
        "baseline_occurrence_ids": sorted(
            str(item.get("occurrence_id"))
            for item in current["history"]
            if item.get("occurrence_id") is not None
        ),
        "baseline_notification_ids": sorted(
            str(item.get("id"))
            for item in current["notifications"]
            if item.get("id") is not None
        ),
        "prepared_at": utcnow_iso(),
    }
    write_private_evidence(args.state, state)
    return state


def verify(args: argparse.Namespace) -> dict:
    require_guard()
    state = load_json(args.state, "scheduled-profile state")
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ScheduledProfileProbeFailure(
            "Scheduled-profile state has an unexpected schema."
        )
    scenario = str(state.get("scenario") or "")
    if scenario not in SCENARIOS:
        raise ScheduledProfileProbeFailure("Scheduled-profile scenario is unsupported.")
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    source_edit_path = getattr(args, "source_edit_receipt", None)
    if scenario == "daily_coworker" and args.prior_evidence is not None:
        if source_edit_path is None:
            raise ScheduledProfileProbeFailure(
                "Second natural-day verification requires an independently reviewed source-edit receipt."
            )
    elif source_edit_path is not None:
        raise ScheduledProfileProbeFailure(
            "A source-edit receipt is permitted only for a second daily briefing verification."
        )
    source_edit = (load_json(source_edit_path, "authorized source-edit receipt")
                   if source_edit_path is not None else None)
    old_occurrences = set(state.get("baseline_occurrence_ids") or [])
    old_notices = set(state.get("baseline_notification_ids") or [])
    deadline = time.monotonic() + max(1, args.timeout)
    last_error: ScheduledProfileProbeFailure | None = None

    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                release = release_identity(
                    client, token, args.rollout, args.provider_policy_plan
                )
                if release != state.get("release"):
                    raise ScheduledProfileProbeFailure(
                        "Deployed release identity changed between prepare and verify."
                    )
                current = load_owned(
                    client, token, str(state["automation_id"]), scenario
                )
                if current["owner_id"] != state.get("owner_id"):
                    raise ScheduledProfileProbeFailure(
                        "Synthetic account identity changed during the scenario."
                    )
                daily_scope = current["daily_scope"] if scenario == "daily_coworker" else {}
                if scenario == "daily_coworker":
                    if (not daily_scope
                            or any(state.get(field) != daily_scope.get(field) for field in (
                                "goal_id", "goal_revision", "project_id", "authorized_document_ids"
                            ))):
                        raise ScheduledProfileProbeFailure(
                            "Owner-approved goal or selected document scope changed since preparation."
                        )
                if scenario == "daily_coworker":
                    require_prepared_daily_profile(state, current["automation"])
                if int(current["automation"]["revision"]) != int(state["automation_revision"]):
                    raise ScheduledProfileProbeFailure(
                        "Automation revision changed during the scenario."
                    )
                if (
                    current["automation"].get("expires_at") != state.get("expires_at")
                    or current["automation"].get("schedule_applied_revision") != state.get("schedule_applied_revision")
                    or current["automation"].get("schedule_applied_enabled") is not True
                ):
                    raise ScheduledProfileProbeFailure(
                        "Automation expiry or Temporal applied schedule state changed during the scenario."
                    )
                history = [
                    item for item in current["history"]
                    if str(item.get("occurrence_id") or "") not in old_occurrences
                ]
                if len(history) != 1:
                    raise ScheduledProfileProbeFailure(
                        f"Expected exactly one new logical occurrence; found {len(history)}."
                    )
                occurrence = history[0]
                if occurrence.get("trigger_type") != "schedule":
                    raise ScheduledProfileProbeFailure(
                        "Scheduled-profile occurrence did not use the schedule trigger."
                    )
                if occurrence.get("occurrence_state") != "accepted":
                    raise ScheduledProfileProbeFailure(
                        f"Occurrence state is {occurrence.get('occurrence_state')!r}; expected 'accepted'."
                    )
                if occurrence.get("run_state") != "completed":
                    raise ScheduledProfileProbeFailure(
                        "Scheduled-profile Agent run is not completed."
                    )
                occurrence_id = str(occurrence.get("occurrence_id") or "")
                run_id = str(occurrence.get("run_id") or "")
                if not occurrence_id or not run_id:
                    raise ScheduledProfileProbeFailure(
                        "Scheduled-profile occurrence is missing its occurrence/run identity."
                    )
                # Count every *new* notice from this automation before
                # narrowing to the expected occurrence. Otherwise a notice
                # linked to an unexpected/duplicate occurrence is silently
                # hidden and the daily "one owner delivery" probe can pass.
                new_automation_notices = [
                    item for item in current["notifications"]
                    if str(item.get("id") or "") not in old_notices
                    and str(item.get("automation_id") or "") == str(state["automation_id"])
                ]
                if scenario == "daily_coworker" and (
                    len(new_automation_notices) != 1
                    or str(new_automation_notices[0].get("occurrence_id") or "") != occurrence_id
                ):
                    raise ScheduledProfileProbeFailure(
                        "Daily briefing has an unexpected new notification for the automation."
                    )
                notices = [
                    item for item in new_automation_notices
                    if str(item.get("occurrence_id") or "") == occurrence_id
                ]
                notification_evidence = {}
                if state.get("run_profile") == "briefing":
                    completion_notice = require_one_completion_notification(notices)
                    evidence_schema_version = BRIEFING_EVIDENCE_SCHEMA_VERSION
                    notification_evidence = {
                        "completion_notification_id": str(completion_notice["id"]),
                        "new_notification_count": len(notices),
                    }
                else:
                    started = [item for item in notices if item.get("kind") == "automation_started"]
                    completed = [item for item in notices if item.get("kind") == "automation_completed"]
                    if len(started) != 1 or len(completed) != 1:
                        raise ScheduledProfileProbeFailure(
                            "Expected exactly one start notice and one completion notice."
                        )
                    evidence_schema_version = LEGACY_PROFILE_EVIDENCE_SCHEMA_VERSION
                    notification_evidence = {
                        "started_notification_id": str(started[0]["id"]),
                        "completion_notification_id": str(completed[0]["id"]),
                        "new_notification_count": len(notices),
                    }
                # These are counts over the freshly read owner-scoped history,
                # not claims of natural timer provenance. The second readback
                # below also checks the completed run and immutable source pins.
                daily_count_evidence = {}
                if scenario == "daily_coworker":
                    daily_count_evidence = {
                        "new_occurrence_count": len(history),
                        "new_run_count": len({
                            str(item.get("run_id")) for item in history if item.get("run_id")
                        }),
                    }
                pin_evidence = {}
                if scenario == "daily_coworker":
                    run = json_object(
                        client.get(f"/api/v1/agent-runs/{run_id}", headers=auth(token)),
                        "daily briefing Agent run",
                    )
                    versions = run.get("input_version_ids")
                    documents = run.get("document_ids")
                    if (str(run.get("id")) != run_id or run.get("state") != "completed"
                            or not isinstance(versions, list) or not versions
                            or not isinstance(documents, list) or len(documents) != len(versions)
                            or any(not isinstance(v, str) or not v for v in versions + documents)
                            or len(set(versions)) != len(versions)
                            or len(set(documents)) != len(documents)):
                        raise ScheduledProfileProbeFailure(
                            "Daily briefing Agent run has no complete immutable document-version pins."
                        )
                    require_daily_run_scope(documents, daily_scope)
                    pin_evidence = {
                        **daily_scope,
                        "input_version_ids": versions,
                        "document_ids": documents,
                    }
                    if args.prior_evidence is not None:
                        prior = load_json(args.prior_evidence, "prior daily briefing evidence")
                        if (prior.get("status") != "passed"
                                or prior.get("scenario") != "daily_coworker"
                                or prior.get("release") != release
                                or prior.get("owner_id") != state.get("owner_id")
                                or prior.get("automation_id") != state.get("automation_id")
                                or any(prior.get(field) != daily_scope.get(field) for field in (
                                    "goal_id", "goal_revision", "project_id", "authorized_document_ids"
                                ))
                                or not isinstance(prior.get("input_version_ids"), list)
                                or not prior["input_version_ids"]):
                            raise ScheduledProfileProbeFailure(
                                "Prior daily briefing evidence does not belong to this release/owner/automation."
                            )
                        prior_run = json_object(
                            client.get(
                                f'/api/v1/agent-runs/{prior["run_id"]}', headers=auth(token),
                            ),
                            "prior daily briefing Agent run",
                        )
                        old_versions = prior_run.get("input_version_ids")
                        if (str(prior_run.get("id")) != str(prior["run_id"])
                                or prior_run.get("state") != "completed"
                                or old_versions != prior["input_version_ids"]
                                or prior_run.get("document_ids") != daily_scope["authorized_document_ids"]):
                            raise ScheduledProfileProbeFailure(
                                "Original Day 7 document pins were not preserved at Day 8 verification."
                            )
                        pin_evidence["prior_run_input_version_ids"] = old_versions

                evidence = {
                    "schema_version": evidence_schema_version,
                    "evidence_kind": "pa10_scheduled_profile",
                    "scenario": scenario,
                    "status": "passed",
                    "release": release,
                    "synthetic_account_label": state["synthetic_account_label"],
                    "owner_id": state["owner_id"],
                    "automation_id": state["automation_id"],
                    "automation_revision": state["automation_revision"],
                    "timezone": state["timezone"],
                    "schedule": state["schedule"],
                    "run_profile": state["run_profile"],
                    "output_language": state["output_language"],
                    "quiet_hours": state["quiet_hours"],
                    "overlap_policy": state["overlap_policy"],
                    "catchup_window_seconds": state["catchup_window_seconds"],
                    "expires_at": state["expires_at"],
                    "schedule_applied_revision": state["schedule_applied_revision"],
                    "schedule_applied_enabled": state["schedule_applied_enabled"],
                    "prepared_at": state["prepared_at"],
                    "verified_at": utcnow_iso(),
                    "occurrence_id": occurrence_id,
                    "due_at": occurrence.get("due_at"),
                    "run_id": run_id,
                    **daily_count_evidence,
                    **pin_evidence,
                    "run_state": "completed",
                    "run_updated_at": occurrence.get("run_updated_at"),
                    **notification_evidence,
                    "operator_case_reference": args.operator_case_reference.strip(),
                }
                if source_edit is not None:
                    evidence["authorized_source_edit"] = source_edit
                if not evidence["operator_case_reference"]:
                    raise ScheduledProfileProbeFailure(
                        "A durable operator case/reference is required."
                    )
                write_private_evidence(args.output, evidence)
                return evidence
            except ScheduledProfileProbeFailure as error:
                last_error = error
                time.sleep(max(1, args.poll_interval))
    raise last_error or ScheduledProfileProbeFailure(
        "Scheduled-profile evidence did not become available before timeout."
    )



def pause_two_day(args: argparse.Namespace) -> dict:
    """Pause only an owner-scoped synthetic daily schedule with two-day evidence."""
    from scripts.staging_day7_two_day_gate import GateFailure, verify_two_day

    require_guard()
    state = load_json(args.state, "Day 8 scheduled-profile state")
    if state.get("scenario") != "daily_coworker":
        raise ScheduledProfileProbeFailure("Two-day pause requires the daily_coworker profile.")
    case_ref = args.operator_case_reference.strip()
    if not case_ref:
        raise ScheduledProfileProbeFailure("A durable operator case reference is required.")
    first = load_json(args.first_evidence, "Day 7 passed evidence")
    second = load_json(args.second_evidence, "Day 8 passed evidence")
    revision = int(state["automation_revision"])
    base_url = clean_origin(env("SHUDDHO_STAGING_API_BASE_URL"))
    token = env("SHUDDHO_STAGING_TOKEN_A")
    with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
        release = release_identity(client, token, args.rollout, args.provider_policy_plan)
        if release != state.get("release"):
            raise ScheduledProfileProbeFailure("Release changed before two-day pause.")
        current = load_owned(client, token, str(state["automation_id"]), "daily_coworker")
        if (current["owner_id"] != state.get("owner_id")
                or int(current["automation"]["revision"]) != revision):
            raise ScheduledProfileProbeFailure("Owner or revision changed before two-day pause.")
        # The pause itself is a state mutation. Before POSTing, prove the
        # live schedule/delivery policy still matches *both* dated receipts
        # and the owner-approved preparation, not only its revision number.
        for prepared in (state, first, second):
            require_prepared_daily_profile(prepared, current["automation"])
        daily_scope = current["daily_scope"]
        if (not daily_scope
                or any(item.get(field) != daily_scope.get(field)
                       for item in (state, first, second)
                       for field in ("goal_id", "goal_revision", "project_id", "authorized_document_ids"))
                or any(item.get("expires_at") != current["automation"].get("expires_at")
                       for item in (state, first, second))):
            raise ScheduledProfileProbeFailure(
                "Live owner-approved goal scope changed before two-day pause."
            )
        evidence = {
            **daily_scope,
            "status": "paused", "release": release,
            "synthetic_account_label": state["synthetic_account_label"],
            "owner_id": state["owner_id"], "automation_id": state["automation_id"],
            "expires_at": current["automation"].get("expires_at"),
            "previous_revision": revision,
            "operator_case_reference": case_ref,
        }
        # This temporary object is only a preflight placeholder and is never
        # written as evidence. Actual pause time/revision are read back below.
        evidence["paused_revision"] = revision + 1
        evidence["paused_at"] = utcnow_iso()
        evidence["schedule_applied_revision"] = revision + 1
        evidence["schedule_applied_enabled"] = False
        try:
            verify_two_day(first, second, evidence, require_paused_opportunity=False)
        except GateFailure as error:
            raise ScheduledProfileProbeFailure(
                f"Two-day evidence rejected before pause: {error}"
            ) from None
        paused = json_object(
            client.post(
                f'/api/v1/automations/{state["automation_id"]}/pause',
                headers=auth(token), json={"expected_revision": revision},
            ), "pause synthetic automation",
        )
        if (paused.get("state") != "paused"
                or int(paused.get("revision", -1)) <= revision):
            raise ScheduledProfileProbeFailure(
                "Pause did not persist the expected synthetic automation transition."
            )
        observed = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            observed = json_object(
                client.get(f'/api/v1/automations/{state["automation_id"]}', headers=auth(token)),
                "read back paused automation",
            )
            if (
                observed.get("state") == "paused"
                and int(observed.get("revision", -1)) > revision
                and observed.get("schedule_applied_revision") == observed.get("revision")
                and observed.get("schedule_applied_enabled") is False
                and not observed.get("schedule_error_code")
                and observed.get("id") == state["automation_id"]
            ):
                break
            time.sleep(2)
        else:
            raise ScheduledProfileProbeFailure(
                "Temporal worker did not apply the paused automation revision before timeout."
            )
        if int(paused.get("revision", -1)) != int(observed.get("revision", -2)):
            raise ScheduledProfileProbeFailure("Pause response and readback revisions disagree.")
        # Do not certify an applied pause if its readback quietly changed
        # owner-approved timing, quiet hours or briefing delivery settings.
        require_prepared_daily_profile(state, observed)
        evidence["schedule_applied_revision"] = observed.get("schedule_applied_revision")
        evidence["schedule_applied_enabled"] = observed.get("schedule_applied_enabled")
        evidence["paused_revision"] = int(observed["revision"])
        evidence["paused_at"] = utcnow_iso()
        # Baseline only after the pause is applied, so a later read-only check
        # can compare the *same owner's* stored occurrence/run/notice identities.
        history = json_object(
            client.get(f'/api/v1/automations/{state["automation_id"]}/history',
                       headers=auth(token)), "pause history baseline",
        ).get("history")
        notices = json_object(
            client.get("/api/v1/notifications", headers=auth(token)),
            "pause notification baseline",
        ).get("notifications")
        if not isinstance(history, list) or not isinstance(notices, list):
            raise ScheduledProfileProbeFailure("Pause baseline endpoints returned invalid lists.")
        occurrence_ids = sorted({
            item["occurrence_id"] for item in history if isinstance(item, dict)
            and isinstance(item.get("occurrence_id"), str) and item["occurrence_id"]
        })
        run_ids = sorted({
            item["run_id"] for item in history if isinstance(item, dict)
            and isinstance(item.get("run_id"), str) and item["run_id"]
        })
        notification_ids = sorted({
            item["id"] for item in notices if isinstance(item, dict)
            and item.get("automation_id") == state["automation_id"]
            and isinstance(item.get("id"), str) and item["id"]
        })
        # This newly approved synthetic daily routine must have exactly the
        # Day 7/8 natural occurrences, admitted runs and completion notices
        # when paused. Extra IDs (even if present before this readback) could
        # otherwise be laundered into the baseline and conceal unintended
        # admissions/deliveries during the pause transition.
        own_notices = [
            item for item in notices if isinstance(item, dict)
            and item.get("automation_id") == state["automation_id"]
        ]
        if (len(history) != 2 or len(own_notices) != 2
                or any(not isinstance(item, dict) for item in history)
                or any(not isinstance(item, dict) for item in notices)
                or set(occurrence_ids) != {first["occurrence_id"], second["occurrence_id"]}
                or set(run_ids) != {first["run_id"], second["run_id"]}
                or set(notification_ids) != {
                    first["completion_notification_id"],
                    second["completion_notification_id"],
                }):
            raise ScheduledProfileProbeFailure(
                "Pause baseline must contain exactly the two observed occurrences, "
                "runs and completion notifications; unexpected activity blocks acceptance."
            )
        evidence.update({
            "pause_baseline_occurrence_ids": occurrence_ids,
            "pause_baseline_run_ids": run_ids,
            "pause_baseline_notification_ids": notification_ids,
        })
        try:
            verify_two_day(first, second, evidence, require_paused_opportunity=False)
        except GateFailure as error:
            raise ScheduledProfileProbeFailure(f"Post-pause evidence rejected: {error}") from None
    write_private_evidence(args.output, evidence)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect release-bound evidence for one Agent-backed scheduled PA-10 profile occurrence. "
            "The separate one-notice reminder gate is intentionally not represented here. "
            "Repeat with fresh evidence for DST, edits, pause/resume, quiet-hours and other cases."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    prepare_parser.add_argument("--automation-id", required=True)
    prepare_parser.add_argument("--rollout", type=Path, required=True)
    prepare_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--rollout", type=Path, required=True)
    verify_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--operator-case-reference", required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--timeout", type=int, default=300)
    verify_parser.add_argument("--poll-interval", type=int, default=3)
    verify_parser.add_argument("--prior-evidence", type=Path, default=None,
                               help="Day 7 evidence; recheck original version pins during Day 8 verify")
    verify_parser.add_argument("--source-edit-receipt", type=Path, default=None,
                               help="Operator-reviewed source edit between natural daily firings")
    pause_parser = sub.add_parser("pause-two-day")
    pause_parser.add_argument("--rollout", type=Path, required=True)
    pause_parser.add_argument("--provider-policy-plan", type=Path, required=True)
    pause_parser.add_argument("--state", type=Path, required=True)
    pause_parser.add_argument("--first-evidence", type=Path, required=True)
    pause_parser.add_argument("--second-evidence", type=Path, required=True)
    pause_parser.add_argument("--operator-case-reference", required=True)
    pause_parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args)
        elif args.command == "verify":
            result = verify(args)
        else:
            result = pause_two_day(args)
    except (httpx.HTTPError, ScheduledProfileProbeFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None
    if args.command == "prepare":
        print(json.dumps({
            "status": "prepared",
            "state": str(args.state),
            "scenario": result["scenario"],
            "automation_id": result["automation_id"],
            "release": result["release"],
            "next": (
                "Allow exactly one reviewed synthetic scheduled occurrence through Temporal, "
                "retain the operator case reference, then run verify."
            ),
        }, indent=2))
    elif args.command == "verify":
        print(json.dumps({
            "status": result["status"],
            "scenario": result["scenario"],
            "output": str(args.output),
            "occurrence_id": result["occurrence_id"],
            "run_id": result["run_id"],
            "completion_notification_id": result["completion_notification_id"],
        }, indent=2))
    else:
        print(json.dumps({"status": result["status"],
                          "automation_id": result["automation_id"],
                          "paused_revision": result["paused_revision"],
                          "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
