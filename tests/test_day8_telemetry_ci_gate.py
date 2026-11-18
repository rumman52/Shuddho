"""The privacy regression must run under the mandatory Day 8 Coworker CI gate."""
from pathlib import Path


def test_day8_telemetry_privacy_is_part_of_mandatory_suite() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = workflow.split(
        "      - name: Verify Day 8 economics comparisons and telemetry without skips\n", 1,
    )[1].split("      - name: Keep Day 8 economics evidence\n", 1)[0]
    assert "tests/test_core_agent_observability.py tests/test_day8_telemetry_privacy.py" in step
    assert "--required-module tests.test_core_agent_observability" in step
    assert "--required-module tests.test_day8_telemetry_privacy" in step
