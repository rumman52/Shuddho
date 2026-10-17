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


def test_staging_secrets_are_scoped_to_the_steps_that_need_them():
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    evidence = _job_section(source, "evidence")
    evidence_header = evidence.split("    steps:", maxsplit=1)[0]
    render_check = evidence.split(
        "- name: Verify live Render mixed-version drain state", maxsplit=1
    )[1].split("- name: Apply pending staging migrations", maxsplit=1)[0]
    migration = evidence.split(
        "- name: Apply pending staging migrations", maxsplit=1
    )[1].split("- name: Collect CW-11 staging evidence", maxsplit=1)[0]
    collector = evidence.split("- name: Collect CW-11 staging evidence", maxsplit=1)[1]

    # Do not expose credentials to checkout, dependency installation, or
    # unrelated steps in the protected environment job.
    assert "secrets." not in evidence_header
    assert "RENDER_API_KEY: ${{ secrets.RENDER_API_KEY }}" in render_check
    assert "SHUDDHO_COWORKER_DATABASE_URL: ${{ secrets.SHUDDHO_STAGING_DATABASE_URL }}" in migration
    assert "SHUDDHO_COWORKER_DATABASE_URL: ${{ secrets.SHUDDHO_STAGING_DATABASE_URL }}" in collector
    assert "SHUDDHO_AUTH_ISSUER: ${{ secrets.SHUDDHO_STAGING_AUTH_ISSUER }}" in collector
    assert "SHUDDHO_AUTH_ISSUER" not in migration


def test_dispatch_inputs_are_passed_through_environment_not_shell_interpolation():
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    render_check = source.split(
        "- name: Verify live Render mixed-version drain state", maxsplit=1
    )[1].split("- name: Apply pending staging migrations", maxsplit=1)[0]
    collector = source.split("- name: Collect CW-11 staging evidence", maxsplit=1)[1]
    render_script = render_check.split("        run: |", maxsplit=1)[1]
    collector_script = collector.split("        run: |", maxsplit=1)[1]

    assert "OLD_SOURCE_REVISION: ${{ inputs.old_source_revision }}" in render_check
    assert "EXPECTED_PUBLICATION_VERSION: ${{ inputs.expected_publication_version }}" in collector
    assert "OLD_SOURCE_REVISION: ${{ inputs.old_source_revision }}" in collector
    assert "${{ inputs.old_source_revision }}" not in render_script
    assert "${{ inputs.expected_publication_version }}" not in collector_script
    assert "${{ inputs.old_source_revision }}" not in collector_script


def test_live_worker_drain_gate_precedes_schema_mutation_and_evidence():
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    evidence = _job_section(source, "evidence")

    live_gate = evidence.index("- name: Verify live Render mixed-version drain state")
    migration = evidence.index("- name: Apply pending staging migrations")
    collector = evidence.index("- name: Collect CW-11 staging evidence")
    artifact = evidence.index("- name: Upload evidence artifact")

    assert live_gate < migration < collector < artifact
