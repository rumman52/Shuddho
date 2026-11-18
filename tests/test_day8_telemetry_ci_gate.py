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
