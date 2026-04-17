from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = REPO_ROOT / "test-artifacts"
TEST_TMP_ROOT.mkdir(exist_ok=True)


@pytest.fixture
def tmp_path() -> Path:
    temp_dir = TEST_TMP_ROOT / f"tmp-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
