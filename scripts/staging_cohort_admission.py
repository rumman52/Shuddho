from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
import jwt
from sqlalchemy import select

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.models import Account


class CohortAdmissionFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def token_account_id(token: str, settings: Settings) -> str:
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except jwt.PyJWTError:
        raise CohortAdmissionFailure("Could not inspect the staging token subject.") from None
    subject = claims.get("sub")
    issuer = claims.get("iss")
    if not isinstance(subject, str) or not subject:
        raise CohortAdmissionFailure("Staging token has no usable subject.")
    if issuer != settings.auth_issuer:
        raise CohortAdmissionFailure("Staging token issuer does not match SHUDDHO_AUTH_ISSUER.")
    return Principal(settings.auth_issuer, subject, 0).account_id


def require_configuration(settings: Settings, allowed_id: str, denied_id: str) -> None:
    if not settings.cohort_enforced:
        raise CohortAdmissionFailure("SHUDDHO_COWORKER_COHORT_ENFORCED must be true.")
    if not settings.cohort_account_ids:
        raise CohortAdmissionFailure("The configured Coworker cohort is empty.")
    if len(settings.cohort_account_ids) > settings.cohort_max_users:
        raise CohortAdmissionFailure("The configured Coworker cohort exceeds its maximum size.")
    if allowed_id not in settings.cohort_account_ids:
        raise CohortAdmissionFailure("The invited staging account is not in the backend cohort allowlist.")
    if denied_id in settings.cohort_account_ids:
        raise CohortAdmissionFailure("The denied staging account is unexpectedly in the backend cohort allowlist.")


def assert_denied_unprovisioned(settings: Settings, denied_id: str) -> None:
    sessions = session_factory(settings.database_url)
    engine = sessions.kw["bind"]
    try:
        with sessions() as db:
            if db.scalar(select(Account.id).where(Account.id == denied_id)) is not None:
                raise CohortAdmissionFailure(
                    "The denied staging identity already has a Coworker account row. Use a fresh non-member staging identity for this exercise."
                )
    finally:
        engine.dispose()


def merge_evidence(path: Path | None, update: dict) -> dict:
    base = {}
    if path:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise CohortAdmissionFailure("Base staging evidence must be a JSON object.")
        base.update(value)
    base.update(update)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate server-enforced Coworker cohort admission with invited and denied staging identities."
    )
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    settings = Settings.from_env()
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    allowed_token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    denied_token = env_secret("SHUDDHO_STAGING_TOKEN_DENIED")
    if allowed_token == denied_token:
        raise SystemExit("Invited and denied staging tokens must be different.")

    try:
        allowed_id = token_account_id(allowed_token, settings)
        denied_id = token_account_id(denied_token, settings)
        if allowed_id == denied_id:
            raise CohortAdmissionFailure("Invited and denied tokens resolve to the same account.")
        require_configuration(settings, allowed_id, denied_id)
        assert_denied_unprovisioned(settings, denied_id)

        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            invited = client.get(
                "/api/v1/me",
                headers={"Authorization": "Bearer " + allowed_token},
            )
            if invited.status_code != 200:
                raise CohortAdmissionFailure(
                    f"Invited cohort account returned HTTP {invited.status_code}; expected 200."
                )

            denied = client.get(
                "/api/v1/me",
                headers={"Authorization": "Bearer " + denied_token},
            )
            if denied.status_code != 403:
                raise CohortAdmissionFailure(
                    f"Non-member staging account returned HTTP {denied.status_code}; expected 403."
                )
            try:
                body = denied.json()
            except ValueError:
                raise CohortAdmissionFailure("Denied cohort response did not return JSON.") from None
            if not isinstance(body, dict) or body.get("error", {}).get("code") != "cohort_not_enabled":
                raise CohortAdmissionFailure("Denied cohort response did not return cohort_not_enabled.")

        assert_denied_unprovisioned(settings, denied_id)
        evidence = merge_evidence(
            args.base_evidence,
            {
                "cohort_admission": passed(
                    f"backend allowlist admitted 1 invited staging account, denied 1 fresh non-member before provisioning, configured_members={len(settings.cohort_account_ids)}, max_users={settings.cohort_max_users}"
                )
            },
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "checks": {"cohort_admission": "passed"},
            "configured_members": len(settings.cohort_account_ids),
            "max_users": settings.cohort_max_users,
        }, indent=2))
    except (CohortAdmissionFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
