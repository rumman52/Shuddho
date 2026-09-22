from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for cohort admission staging tests")
jwt = pytest.importorskip("jwt", reason="Install the coworker extra for cohort admission staging tests")

from scripts import staging_cohort_admission as admission
from services.coworker.auth import Principal


ISSUER = "https://identity.example.test/auth/v1"


def token(subject: str, issuer: str = ISSUER) -> str:
    return jwt.encode({"iss": issuer, "sub": subject}, key="", algorithm="none")


def settings(*, allowed=(), enforced=True, max_users=25):
    return SimpleNamespace(
        auth_issuer=ISSUER,
        cohort_enforced=enforced,
        cohort_account_ids=frozenset(allowed),
        cohort_max_users=max_users,
    )


def test_token_account_id_matches_server_principal_mapping():
    value = admission.token_account_id(token("alice"), settings())
    assert value == Principal(ISSUER, "alice", 0).account_id


def test_token_account_id_rejects_wrong_issuer():
    with pytest.raises(admission.CohortAdmissionFailure, match="issuer"):
        admission.token_account_id(token("alice", "https://other.example.test"), settings())


def test_cohort_configuration_requires_invited_and_denied_boundaries():
    invited = Principal(ISSUER, "alice", 0).account_id
    denied = Principal(ISSUER, "bob", 0).account_id
    admission.require_configuration(settings(allowed={invited}), invited, denied)

    with pytest.raises(admission.CohortAdmissionFailure, match="must be true"):
        admission.require_configuration(settings(allowed={invited}, enforced=False), invited, denied)

    with pytest.raises(admission.CohortAdmissionFailure, match="not in the backend cohort allowlist"):
        admission.require_configuration(settings(allowed=set()), invited, denied)

    with pytest.raises(admission.CohortAdmissionFailure, match="unexpectedly in"):
        admission.require_configuration(settings(allowed={invited, denied}), invited, denied)


def test_merge_evidence_preserves_existing_release_proof(tmp_path):
    base = tmp_path / "evidence.json"
    base.write_text(
        '{"ci":{"status":"passed","evidence":"run-1"}}',
        encoding="utf-8",
    )
    result = admission.merge_evidence(
        base,
        {"cohort_admission": {"status": "passed", "evidence": "staging-cohort"}},
    )
    assert result["ci"]["status"] == "passed"
    assert result["cohort_admission"]["status"] == "passed"
