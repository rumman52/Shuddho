"""Fail CI on empty, skipped, errored or failed mandatory JUnit suites."""
from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def check_report(path: Path, required_module: str | None = None) -> tuple[int, int]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    rejected = sum(any(case.find(tag) is not None for tag in ("skipped", "failure", "error")) for case in cases)
    if not cases or rejected:
        raise ValueError(f"Mandatory tests rejected: collected={len(cases)}, skipped/failed/errored={rejected}")
    if required_module and not any(case.get("classname") == required_module for case in cases):
        raise ValueError(f"No tests collected from required module: {required_module}")
    return len(cases), rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--required-module")
    args = parser.parse_args()
    try:
        count, _ = check_report(args.report, args.required_module)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Mandatory tests passed: {count} collected, zero skips/failures/errors")


if __name__ == "__main__":
    main()
