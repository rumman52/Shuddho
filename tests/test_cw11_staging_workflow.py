"""Static safety contracts for the protected CW-11 staging workflow.

These checks intentionally use only the standard library so they run in the
lightweight test-and-build job as well as the full coworker job.
"""
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "cw11-staging-evidence.yml"
)


def _job_section(source: str, job: str, next_job: str | None = None) -> str:
    start = source.index(f"  {job}:")
    if next_job is None:
        return source[start:]
    end = source.index(f"  {next_job}:", start + len(f"  {job}:"))
    return source[start:end]


def test_bad_confirmation_fails_before_staging_environment_or_secrets():
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    confirmation = _job_section(source, "confirm-staging", "evidence")
    evidence = _job_section(source, "evidence")

    # A job-level 'if' silently skips the only job on a typo; GitHub can then
    # show a successful workflow with no evidence. The guard must instead fail.
    assert "if: ${{ inputs.confirm == 'CW11-STAGING' }}" not in source
    assert 'CONFIRM: ${{ inputs.confirm }}' in confirmation
    assert '[[ "${CONFIRM}" != "CW11-STAGING" ]]' in confirmation
    assert "environment:" not in confirmation
    assert "secrets." not in confirmation
    assert "needs: confirm-staging" in evidence
    assert "environment:\n      name: staging" in evidence


def test_live_worker_drain_gate_precedes_schema_mutation_and_evidence():
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    evidence = _job_section(source, "evidence")

    live_gate = evidence.index("- name: Verify live Render mixed-version drain state")
    migration = evidence.index("- name: Apply pending staging migrations")
    collector = evidence.index("- name: Collect CW-11 staging evidence")
    artifact = evidence.index("- name: Upload evidence artifact")

    assert live_gate < migration < collector < artifact
