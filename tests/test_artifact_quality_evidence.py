from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.artifact_quality_evidence import (
    ArtifactQualityEvidenceError,
    compile_artifact_quality_evidence,
    validate_artifact_quality_evidence,
)


RELEASE_ID = "coworker-cohort-001"
REVISION = "1" * 40


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollout(tmp_path: Path) -> Path:
    return write_json(
        tmp_path / "rollout.json",
        {
            "release_id": RELEASE_ID,
            "capabilities": {"artifact_services": True},
        },
    )


def native_value() -> dict:
    return {
        "schema_version": 2,
        "generated_at": "2026-09-30T08:00:00+00:00",
        "source_revision": REVISION,
        "languages": ["ar", "bn", "en", "zh"],
        "formats": ["pptx", "xlsx"],
        "rendered": [
            "presentation-ar.pdf",
            "presentation-bn.pdf",
            "presentation-en.pdf",
            "presentation-zh-dense.pdf",
            "spreadsheet-ar.pdf",
            "spreadsheet-bn.pdf",
            "spreadsheet-en.pdf",
            "spreadsheet-zh-long.pdf",
        ],
        "formula_edits": {
            "changed": {"cost": 87.5, "total": 103.5, "recalculated": True},
            "zero": {"cost": 0, "total": 16, "recalculated": True},
            "missing": {"cost": None, "total": None, "recalculated": True},
            "negative": {"cost": -37.5, "total": -21.5, "recalculated": True},
        },
    }


def review_value(native_path: Path) -> dict:
    return {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "generated_at": "2026-09-30T08:05:00+00:00",
        "source_revision": REVISION,
        "native_results_sha256": file_hash(native_path),
        "reviewer_reference": "artifact-review-123",
        "languages": ["ar", "bn", "en", "zh"],
        "formats": ["pptx", "xlsx"],
        "checks": {
            "editable_open": True,
            "text_visible": True,
            "rtl_layout": True,
            "chart_pagination": True,
            "spreadsheet_recalculation": True,
            "visual_overflow": True,
            "human_semantic_review": True,
        },
        "failures": [],
    }


def compiled(tmp_path: Path):
    rollout_path = rollout(tmp_path)
    native_path = write_json(tmp_path / "native.json", native_value())
    review_path = write_json(tmp_path / "review.json", review_value(native_path))
    value = compile_artifact_quality_evidence(
        rollout_path=rollout_path,
        native_results_path=native_path,
        human_review_path=review_path,
    )
    return rollout_path, native_path, review_path, value


def test_compiler_binds_rollout_native_review_and_revision(tmp_path):
    rollout_path, native_path, review_path, value = compiled(tmp_path)
    assert value["gate_decision"] == "PASS"
    assert value["source_revision"] == REVISION
    assert value["rollout_manifest_sha256"] == file_hash(rollout_path)
    assert value["native_results_sha256"] == file_hash(native_path)
    assert value["human_review_sha256"] == file_hash(review_path)
    validate_artifact_quality_evidence(
        value,
        release_id=RELEASE_ID,
        rollout_sha256=file_hash(rollout_path),
        expected_source_revision=REVISION,
    )


@pytest.mark.parametrize(
    "case",
    ["render", "formula", "review", "native_hash", "revision"],
)
def test_compiler_fails_closed_on_artifact_evidence_drift(tmp_path, case):
    rollout_path = rollout(tmp_path)
    native = native_value()
    if case == "render":
        native["rendered"].pop()
    if case == "formula":
        native["formula_edits"]["changed"]["total"] = 999
    native_path = write_json(tmp_path / "native.json", native)
    review = review_value(native_path)
    if case == "review":
        review["checks"]["human_semantic_review"] = False
    if case == "native_hash":
        review["native_results_sha256"] = "a" * 64
    if case == "revision":
        review["source_revision"] = "2" * 40
    review_path = write_json(tmp_path / "review.json", review)
    with pytest.raises(ArtifactQualityEvidenceError):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )


def test_validator_rejects_rollout_and_source_revision_drift(tmp_path):
    rollout_path, _native, _review, value = compiled(tmp_path)
    with pytest.raises(ArtifactQualityEvidenceError, match="rollout"):
        validate_artifact_quality_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256="b" * 64,
        )
    with pytest.raises(ArtifactQualityEvidenceError, match="source revision"):
        validate_artifact_quality_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=file_hash(rollout_path),
            expected_source_revision="2" * 40,
        )


def test_compiler_rejects_artifact_disabled_rollout(tmp_path):
    rollout_path = write_json(
        tmp_path / "rollout.json",
        {
            "release_id": RELEASE_ID,
            "capabilities": {"artifact_services": False},
        },
    )
    native_path = write_json(tmp_path / "native.json", native_value())
    review_path = write_json(tmp_path / "review.json", review_value(native_path))
    with pytest.raises(
        ArtifactQualityEvidenceError,
        match="artifact_services=true",
    ):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )
