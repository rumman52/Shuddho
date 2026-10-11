from pathlib import Path

import pytest

from scripts.mandatory_test_gate import check_report


@pytest.mark.parametrize("case", ["", "<testcase><skipped/></testcase>", "<testcase><failure/></testcase>", "<testcase><error/></testcase>"])
def test_empty_or_unexecuted_safety_suite_is_rejected(tmp_path: Path, case: str):
    report = tmp_path / "result.xml"
    report.write_text(f"<testsuites><testsuite>{case}</testsuite></testsuites>")
    with pytest.raises(ValueError):
        check_report(report)


def test_executed_success_is_accepted(tmp_path: Path):
    report = tmp_path / "result.xml"
    report.write_text('<testsuites><testsuite><testcase name="expiry"/><testcase name="lost_response"/></testsuite></testsuites>')
    assert check_report(report) == (2, 0)


def test_unrelated_success_cannot_replace_mandatory_safety_collection(tmp_path: Path):
    report = tmp_path / "result.xml"
    report.write_text('<testsuite><testcase classname="tests.test_mandatory_test_gate" name="helper"/></testsuite>')
    with pytest.raises(ValueError, match="required module"):
        check_report(report, required_module="tests.test_transaction_chaos_qualification")
