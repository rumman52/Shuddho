"""Post-admission access verification for an explicitly authorized 5–10-person pilot.

This command never edits the allowlist or admits users. The Day 10 decision
receipt is a *mechanical* prerequisite: an authorized human must separately
authenticate the Founder and platform-owner approvals before admission.
Use an owner-controlled token file outside the repository; no token, subject,
account ID or response body is written to evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat

import httpx

from scripts.cohort_release_gate import validate_rollout
from scripts.day10_release_decision import read_json
from scripts.ruke_pilot_eval import sha256 as file_sha256, strict_json_loads
from scripts.staging_api_exercise import env_secret, require_https_base
from scripts.staging_cohort_admission import (
    CohortAdmissionFailure,
    assert_denied_unprovisioned,
    token_account_id,
)
from services.coworker.config import Settings

SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAX_SECRET_FILE_BYTES = 65_536


class PilotVerificationFailure(ValueError):
    """An operated pilot access check cannot be credited."""


def require_release_decision(rollout_path: Path, decision_path: Path, revision: str) -> tuple[dict, str]:
    """Check the exact released digest and canonical GO, without claiming human authentication."""
    if not SHA40.fullmatch(revision):
        raise PilotVerificationFailure("Expected an exact 40-character source revision.")
    rollout = read_json(rollout_path)
    decision = read_json(decision_path)
    if not isinstance(rollout, dict) or not isinstance(decision, dict):
        raise PilotVerificationFailure("Expected rollout and decision JSON objects.")
    rollout_failures = validate_rollout(rollout, max_cohort_users=10)
    if rollout_failures:
        raise PilotVerificationFailure("Release rollout has failed canonical rollout checks.")
    digest = file_sha256(rollout_path)
    cohort = rollout.get("cohort")
    limit = cohort.get("max_users") if isinstance(cohort, dict) else None
    if type(limit) is not int or not 5 <= limit <= 10:
        raise PilotVerificationFailure("Pilot cohort maximum must be between five and ten.")
    if not all((
        decision.get("canonical_decision") == "GO_CONTROLLED_COHORT",
        decision.get("decision") == "READY_FOR_OWNER_CONTROLLED_PILOT",
        decision.get("pilot_activated") is False,
        decision.get("blockers") == [],
        decision.get("release_id") == rollout.get("release_id"),
        decision.get("source_revision") == revision,
        decision.get("rollout_manifest_sha256") == digest,
    )):
        raise PilotVerificationFailure("Day 10 GO/approval decision is absent or mismatched.")
    return rollout, digest


def load_member_tokens(path: Path) -> list[str]:
    """Read only a small owner-private JSON array; reject symlinks and shared permissions."""
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode)
                or not 0 < meta.st_size <= MAX_SECRET_FILE_BYTES
                or stat.S_IMODE(meta.st_mode) & 0o077):
            raise PilotVerificationFailure("Pilot token file must be a private regular file (0600).")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            payload = handle.read(MAX_SECRET_FILE_BYTES + 1)
        tokens = strict_json_loads(payload.decode("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        if isinstance(exc, PilotVerificationFailure):
            raise
        raise PilotVerificationFailure("Cannot read owner-private pilot token file.") from None
    finally:
        if fd != -1:
            os.close(fd)
    if (not isinstance(tokens, list) or not 5 <= len(tokens) <= 10
            or any(not isinstance(token, str) or not token or token != token.strip()
                   for token in tokens)
            or len(set(tokens)) != len(tokens)):
        raise PilotVerificationFailure("Expected five to ten distinct member tokens.")
    return tokens


def require_exact_pilot_members(settings: Settings, tokens: list[str],
                                denied_token: str, maximum: int) -> str:
    """Compare *every* token's issuer/subject mapping to the exact backend allowlist."""
    if not settings.cohort_enforced:
        raise PilotVerificationFailure("Backend cohort enforcement is disabled.")
    configured = settings.cohort_account_ids
    if (type(settings.cohort_max_users) is not int
            or settings.cohort_max_users != maximum
            or not 5 <= len(configured) <= maximum):
        raise PilotVerificationFailure("Backend has no qualified five-to-ten-user allowlist.")
    if denied_token in tokens:
        raise PilotVerificationFailure("Nonmember and member credentials overlap.")
    member_ids = [token_account_id(token, settings) for token in tokens]
    denied_id = token_account_id(denied_token, settings)
    if (len(member_ids) != len(set(member_ids))
            or set(member_ids) != set(configured)
            or denied_id in configured):
        raise PilotVerificationFailure("Pilot member tokens do not exactly match the backend allowlist.")
    return denied_id


def probe_access(client: httpx.Client, member_tokens: list[str], denied_token: str) -> None:
    """Check all members, then a fresh nonmember, without recording identities or payloads."""
    for token in member_tokens:
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})
        if response.status_code != 200:
            raise PilotVerificationFailure("A pilot member was not admitted by the live API.")
    denied = client.get("/api/v1/me", headers={"Authorization": "Bearer " + denied_token})
    if denied.status_code != 403:
        raise PilotVerificationFailure("The live API did not deny the nonmember with HTTP 403.")
    try:
        body = denied.json()
    except ValueError:
        raise PilotVerificationFailure("Nonmember denial did not return JSON.") from None
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict) or (
            body["error"].get("code") != "cohort_not_enabled"):
        raise PilotVerificationFailure("Nonmember denial did not return cohort_not_enabled.")


def immutable_report(path: Path, result: dict) -> None:
    """Never overwrite even a failed or previous pilot access verification."""
    encoded = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    except FileExistsError:
        raise PilotVerificationFailure("Report already exists; use a new first-run-safe path.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--member-tokens-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rollout, digest = require_release_decision(args.rollout, args.decision, args.source_revision)
        member_tokens = load_member_tokens(args.member_tokens_file)
        settings = Settings.from_env()
        denied_token = env_secret("SHUDDHO_PILOT_NONMEMBER_TOKEN")
        base_url = require_https_base(env_secret("SHUDDHO_PILOT_API_BASE_URL"))
        denied_id = require_exact_pilot_members(
            settings, member_tokens, denied_token, rollout["cohort"]["max_users"],
        )
        assert_denied_unprovisioned(settings, denied_id)
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            probe_access(client, member_tokens, denied_token)
        assert_denied_unprovisioned(settings, denied_id)
        report = {
            "schema_version": 1,
            "status": "passed",
            "check": "post_admission_complete_cohort_access",
            "release_id": rollout["release_id"],
            "source_revision": args.source_revision,
            "rollout_manifest_sha256": digest,
            "members_checked": len(member_tokens),
            "members_http_200": len(member_tokens),
            "nonmember_http_403": True,
            "nonmember_unprovisioned_before_after": True,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "admission_performed_by_cli": False,
            "human_approvals_authenticated_by_cli": False,
            "operator_must_authenticate_approval_and_runtime_identity": True,
        }
        immutable_report(args.output, report)
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0
    except (CohortAdmissionFailure, PilotVerificationFailure, httpx.HTTPError, OSError, ValueError) as exc:
        # Never include token values, subjects or response payloads.
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
