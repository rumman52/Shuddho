"""The privacy regression must run under the mandatory Day 8 Coworker CI gate."""
from pathlib import Path


def test_day8_telemetry_privacy_is_part_of_mandatory_suite() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    # Select the step directly preceding its evidence-upload step. The
    # descriptive name may legitimately change as Day 7/8 gates are added.
    before_upload = workflow.split(
        "      - name: Keep Day 8 economics evidence\n", 1,
    )[0]
    step = before_upload.rsplit("      - name: ", 1)[1]
    assert "Day 8" in step or "Day 7–8" in step
    assert "tests/test_core_agent_observability.py tests/test_day8_telemetry_privacy.py" in step
    assert "--required-module tests.test_core_agent_observability" in step
    assert "--required-module tests.test_day8_telemetry_privacy" in step
    assert "--required-module tests.test_day8_telemetry_ci_gate" in step
    assert "tests/test_staging_pa10_scheduled_profile.py" in step
    assert "--required-module tests.test_staging_pa10_scheduled_profile" in step
    assert "tests/test_automations.py::test_briefing_occurrence_emits_one_completion_notification_only" in step
    assert "--required-module tests.test_automations" in step


def test_only_the_canonical_private_operational_event_module_exists() -> None:
    assert Path("services/coworker/day8_telemetry.py").is_file()
    assert not Path("services/coworker/operational_telemetry.py").exists()


def test_day8_dispatch_observability_is_mandatory() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = workflow.split("      - name: Keep Day 8 economics evidence\n", 1)[0].rsplit("      - name: ", 1)[1]
    for module in ("cohort_dispatch_observability", "cohort_observability_export"):
        assert f"tests/test_{module}.py" in step
        assert f"--required-module tests.test_{module}" in step


def test_day8_provider_capacity_observation_is_mandatory() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = workflow.split("      - name: Keep Day 8 economics evidence\n", 1)[0].rsplit("      - name: ", 1)[1]
    assert "tests/test_provider_capacity_observation.py" in step
    assert "--required-module tests.test_provider_capacity_observation" in step
