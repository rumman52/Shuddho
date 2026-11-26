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
from pathlib import Path
import re

import httpx

from scripts.cohort_release_gate import validate_rollout
from scripts.release_contract import pilot_canonical_only_capabilities_disabled
from scripts.day10_release_decision import pilot_authorization_terms, read_json, read_json_with_sha
from scripts.ruke_pilot_eval import _read_evidence_bytes, immutable_write, strict_json_loads
from scripts.staging_api_exercise import env_secret, require_https_base
from scripts.staging_release_freeze import api_runtime_capabilities_match_rollout
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


def require_pilot_authorization_claim(claim: object, rollout: dict) -> None:
    """Reject expired or mismatched authorization terms; not signer authentication."""
    if (not isinstance(claim, dict)
            or set(claim) != {"scope_sha256", "max_spend_microusd", "expires_at"}
            or pilot_authorization_terms(claim, rollout, now=datetime.now(timezone.utc)) is None):
        raise PilotVerificationFailure("Day 10 pilot authorization terms are absent, invalid, or expired.")


def _require_release_decision_snapshot(rollout_path: Path, decision_path: Path, revision: str) -> tuple[dict, str, dict]:
    """Check the exact released digest and canonical GO, without claiming human authentication."""
    if not SHA40.fullmatch(revision):
        raise PilotVerificationFailure("Expected an exact 40-character source revision.")
    # Bind the admitted rollout and its decision SHA to one descriptor read.
    rollout, digest = read_json_with_sha(rollout_path)
    decision = read_json(decision_path)
    if not isinstance(rollout, dict) or not isinstance(decision, dict):
        raise PilotVerificationFailure("Expected rollout and decision JSON objects.")
    rollout_failures = validate_rollout(rollout, max_cohort_users=10)
    if rollout_failures:
        raise PilotVerificationFailure("Release rollout has failed canonical rollout checks.")
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
    claim = decision.get("pilot_authorization_claim")
    require_pilot_authorization_claim(claim, rollout)
    return rollout, digest, claim


def require_release_decision(rollout_path: Path, decision_path: Path, revision: str) -> tuple[dict, str]:
    """Compatibility entrypoint: verify the exact decision and current pilot terms."""
    rollout, digest, _ = _require_release_decision_snapshot(rollout_path, decision_path, revision)
    return rollout, digest


def load_member_tokens(path: Path) -> list[str]:
    """Read one bounded, stable, owner-private token snapshot."""
    try:
        payload, _ = _read_evidence_bytes(
            path, max_bytes=MAX_SECRET_FILE_BYTES, require_private=True,
        )
        tokens = strict_json_loads(payload.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        raise PilotVerificationFailure("Cannot read owner-private pilot token file (0600).") from None
    if (not isinstance(tokens, list) or not 5 <= len(tokens) <= 10
            or any(not isinstance(token, str) or not token or token != token.strip()
                   for token in tokens)
            or len(set(tokens)) != len(tokens)):
        raise PilotVerificationFailure("Expected five to ten distinct member tokens.")
    return tokens


def require_exact_pilot_members(settings: Settings, tokens: list[str],
                                denied_token: str, maximum: int) -> tuple[list[str], str]:
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
    return member_ids, denied_id


def probe_access(client: httpx.Client, member_tokens: list[str], denied_token: str,
                 member_ids: list[str]) -> None:
    """Bind each successful live account read to its prevalidated member token."""
    if (not isinstance(member_ids, list)
            or len(member_ids) != len(member_tokens)
            or any(not isinstance(owner, str) or not owner for owner in member_ids)
            or len(set(member_ids)) != len(member_ids)):
        raise PilotVerificationFailure("Pilot member identity list was not verified.")
    for token, expected_id in zip(member_tokens, member_ids):
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer " + token})
        if response.status_code != 200:
            raise PilotVerificationFailure("A pilot member was not admitted by the live API.")
        try:
            account = response.json()
        except ValueError:
            raise PilotVerificationFailure("Pilot member identity was not verified.") from None
        if not isinstance(account, dict) or account.get("account_id") != expected_id:
            raise PilotVerificationFailure("Pilot member identity was not verified.")
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



def verify_live_runtime(client: httpx.Client, token: str, rollout: dict, revision: str,
                        members_checked: int) -> None:
    """Pin the admitted API to the exact reviewed source, full flags and cohort."""
    response = client.get(
        "/api/v1/runtime-manifest", headers={"Authorization": "Bearer " + token},
    )
    if response.status_code != 200:
        raise PilotVerificationFailure("The authenticated runtime manifest was not available.")
    try:
        runtime = response.json()
    except ValueError:
        raise PilotVerificationFailure("The runtime manifest was not valid JSON.") from None
    if not isinstance(runtime, dict):
        raise PilotVerificationFailure("The runtime manifest was not an object.")
    capabilities = runtime.get("capabilities")
    declared = rollout.get("capabilities")
    cohort = runtime.get("cohort")
    declared_cohort = rollout.get("cohort")
    if not (
        type(runtime.get("schema_version")) is int
        and runtime["schema_version"] == 2
        and runtime.get("source_revision") == revision
        and runtime.get("environment") == rollout.get("environment")
        and api_runtime_capabilities_match_rollout(capabilities, declared)
        and pilot_canonical_only_capabilities_disabled(runtime.get("canonical_only_capabilities"))
        and isinstance(runtime.get("reviewed_skills"), dict)
        and runtime.get("action_providers") == rollout.get("action_providers", [])
        and isinstance(cohort, dict)
        and isinstance(declared_cohort, dict)
        and cohort.get("enforced") is True
        and type(cohort.get("max_users")) is int
        and cohort["max_users"] == declared_cohort.get("max_users")
        and type(cohort.get("configured_members")) is int
        and cohort["configured_members"] == members_checked
    ):
        raise PilotVerificationFailure("Live API identity, flags or cohort differ from the frozen release.")


def immutable_report(path: Path, result: dict) -> None:
    """Never overwrite even a failed or previous pilot access verification."""
    try:
        # Exclusive create, fsync and 0600 regardless of the operator's umask.
        immutable_write(path, result)
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
        rollout, digest, claim = _require_release_decision_snapshot(args.rollout, args.decision, args.source_revision)
        member_tokens = load_member_tokens(args.member_tokens_file)
        settings = Settings.from_env()
        denied_token = env_secret("SHUDDHO_PILOT_NONMEMBER_TOKEN")
        base_url = require_https_base(env_secret("SHUDDHO_PILOT_API_BASE_URL"))
        member_ids, denied_id = require_exact_pilot_members(
            settings, member_tokens, denied_token, rollout["cohort"]["max_users"],
        )
        require_pilot_authorization_claim(claim, rollout)
        assert_denied_unprovisioned(settings, denied_id)
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False,
                          trust_env=False) as client:
            verify_live_runtime(client, member_tokens[0], rollout,
                                args.source_revision, len(member_tokens))
            probe_access(client, member_tokens, denied_token, member_ids)
        assert_denied_unprovisioned(settings, denied_id)
        require_pilot_authorization_claim(claim, rollout)
        report = {
            "schema_version": 1,
            "status": "passed",
            "check": "post_admission_complete_cohort_access",
            "release_id": rollout["release_id"],
            "source_revision": args.source_revision,
            "rollout_manifest_sha256": digest,
            "members_checked": len(member_tokens),
            "members_http_200": len(member_tokens),
            "runtime_manifest_verified": True,
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
        # Preserve the *first* failed attempt without disclosing response bodies,
        # credentials, local secret paths, user IDs or exception messages.
        failure = {
            "schema_version": 1,
            "status": "failed",
            "check": "post_admission_complete_cohort_access",
            "failure_type": type(exc).__name__,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "admission_performed_by_cli": False,
            "human_approvals_authenticated_by_cli": False,
        }
        try:
            immutable_report(args.output, failure)
        except (PilotVerificationFailure, OSError):
            # An existing receipt must never be replaced, even on failure.
            pass
        print(json.dumps(failure, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
