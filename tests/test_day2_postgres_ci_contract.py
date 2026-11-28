"""Source-only guard for both disposable Day 2 migration rehearsal services."""
from pathlib import Path
import re

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _job():
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("  postgres-18-qualification:\n")
    return re.split(r"(?m)^  [a-z][a-z0-9-]*:\s*$", text[start:].split("\n", 1)[1], maxsplit=1)[0]


@pytest.mark.parametrize("major,service,port", [(17, "postgres17", 5433), (18, "postgres", 5432)])
def test_day2_rehearsal_uses_separate_versioned_service(major, service, port):
    job = _job()
    match = re.search(rf"(?ms)^      {service}:\n(.*?)(?=^      [a-z0-9]+:|^    env:)", job)
    assert match, f"Missing PostgreSQL {major} service"
    block = match.group(1)
    assert f"image: postgres:{major}-bookworm" in block
    assert f'ports: ["{port}:5432"]' in block
    assert "POSTGRES_DB: shuddho_coworker_test" in block
    assert "pg_isready" in block


@pytest.mark.parametrize("major,port,receipt", [
    (17, 5433, "day2-dual-0071-postgres17.xml"),
    (18, 5432, "day2-dual-0071-postgres.xml"),
])
def test_day2_rehearsal_is_version_bound_and_mandatory(major, port, receipt):
    job = _job()
    title = f"      - name: Rehearse both Day 2 0071 migration paths on PostgreSQL {major} without skips\n"
    assert title in job
    step = job.split(title, 1)[1].split("\n      - ", 1)[0]
    assert f'SHUDDHO_TEST_POSTGRES_MAJOR: "{major}"' in step
    assert f"@localhost:{port}/shuddho_coworker_test" in step
    assert "pytest tests/test_day2_dual_0071_postgres.py -q -rs" in step
    assert f"--junitxml=/tmp/{receipt}" in step
    assert f"mandatory_test_gate /tmp/{receipt} --required-module tests.test_day2_dual_0071_postgres" in step
    assert "continue-on-error" not in step
    assert f"path: /tmp/{receipt}" in job


def test_postgres_qualification_keeps_existing_merge_gate_identity():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "name: PostgreSQL 18 staging compatibility" in _job()
    assert "      - postgres-18-qualification\n" in text
    assert 'check_result postgres-18-qualification "$POSTGRES18_RESULT" "$backend_policy"' in text
