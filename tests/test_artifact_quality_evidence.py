from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.artifact_quality_evidence import (
    ArtifactQualityEvidenceError,
    artifact_set_sha256,
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


def artifact_files(tmp_path: Path) -> dict[str, str]:
    names = [
        "originals/presentation-en.pptx",
        "originals/spreadsheet-en.xlsx",
        "originals/presentation-bn.pptx",
        "originals/spreadsheet-bn.xlsx",
        "originals/presentation-ar.pptx",
        "originals/spreadsheet-ar.xlsx",
        "originals/presentation-zh-dense.pptx",
        "originals/spreadsheet-zh-long.xlsx",
        "recalculated/changed.xlsx",
        "recalculated/zero.xlsx",
        "recalculated/missing.xlsx",
        "recalculated/negative.xlsx",
    ]
    rendered = [
        "presentation-ar.pdf",
        "presentation-bn.pdf",
        "presentation-en.pdf",
        "presentation-zh-dense.pdf",
        "spreadsheet-ar.pdf",
        "spreadsheet-bn.pdf",
        "spreadsheet-en.pdf",
        "spreadsheet-zh-long.pdf",
    ]
    names += [f"rendered/{name}" for name in rendered]
    names += [f"rendered/{Path(name).stem}-1.png" for name in rendered]
    result = {}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("artifact:" + name).encode("utf-8"))
        result[name] = file_hash(path)
    return result


def native_value(tmp_path: Path) -> dict:
    artifacts = artifact_files(tmp_path)
    return {
        "schema_version": 3,
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
        "artifacts_sha256": artifacts,
        "artifact_set_sha256": artifact_set_sha256(artifacts),
        "formula_edits": {
            "changed": {"cost": 87.5, "total": 103.5, "recalculated": True},
            "zero": {"cost": 0, "total": 16, "recalculated": True},
            "missing": {"cost": None, "total": None, "recalculated": True},
            "negative": {"cost": -37.5, "total": -21.5, "recalculated": True},
        },
    }


def review_value(native_path: Path, native: dict) -> dict:
    return {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "generated_at": "2026-09-30T08:05:00+00:00",
        "source_revision": REVISION,
        "native_results_sha256": file_hash(native_path),
        "artifact_set_sha256": native["artifact_set_sha256"],
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
    native = native_value(tmp_path)
    native_path = write_json(tmp_path / "native.json", native)
    review_path = write_json(tmp_path / "review.json", review_value(native_path, native))
    value = compile_artifact_quality_evidence(
        rollout_path=rollout_path,
        native_results_path=native_path,
        human_review_path=review_path,
    )
    return rollout_path, native_path, review_path, value


def test_compiler_binds_rollout_native_review_artifacts_and_revision(tmp_path):
    rollout_path, native_path, review_path, value = compiled(tmp_path)
    native = json.loads(native_path.read_text(encoding="utf-8"))
    assert value["gate_decision"] == "PASS"
    assert value["source_revision"] == REVISION
    assert value["rollout_manifest_sha256"] == file_hash(rollout_path)
    assert value["native_results_sha256"] == file_hash(native_path)
    assert value["artifact_set_sha256"] == native["artifact_set_sha256"]
    assert value["human_review_sha256"] == file_hash(review_path)
    validate_artifact_quality_evidence(
        value,
        release_id=RELEASE_ID,
        rollout_sha256=file_hash(rollout_path),
        expected_source_revision=REVISION,
    )


@pytest.mark.parametrize(
    "case",
    ["render", "formula", "review", "native_hash", "artifact_set", "revision"],
)
def test_compiler_fails_closed_on_artifact_evidence_drift(tmp_path, case):
    rollout_path = rollout(tmp_path)
    native = native_value(tmp_path)
    if case == "render":
        native["rendered"].pop()
    if case == "formula":
        native["formula_edits"]["changed"]["total"] = 999
    native_path = write_json(tmp_path / "native.json", native)
    review = review_value(native_path, native)
    if case == "review":
        review["checks"]["human_semantic_review"] = False
    if case == "native_hash":
        review["native_results_sha256"] = "a" * 64
    if case == "artifact_set":
        review["artifact_set_sha256"] = "d" * 64
    if case == "revision":
        review["source_revision"] = "2" * 40
    review_path = write_json(tmp_path / "review.json", review)
    with pytest.raises(ArtifactQualityEvidenceError):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )


def test_compiler_rejects_substituted_artifact_bytes(tmp_path):
    rollout_path = rollout(tmp_path)
    native = native_value(tmp_path)
    native_path = write_json(tmp_path / "native.json", native)
    review_path = write_json(tmp_path / "review.json", review_value(native_path, native))
    (tmp_path / "originals/presentation-en.pptx").write_bytes(b"substituted")
    with pytest.raises(ArtifactQualityEvidenceError, match="artifact bytes"):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )


def test_compiler_rejects_future_native_and_review_times(tmp_path):
    rollout_path = rollout(tmp_path)
    native = native_value(tmp_path)
    native["generated_at"] = "2099-01-01T00:00:00+00:00"
    native_path = write_json(tmp_path / "native-future.json", native)
    review_path = write_json(tmp_path / "review-future.json", review_value(native_path, native))
    with pytest.raises(ArtifactQualityEvidenceError, match="future"):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )

    native = native_value(tmp_path)
    native_path = write_json(tmp_path / "native.json", native)
    review = review_value(native_path, native)
    review["generated_at"] = "2099-01-01T00:00:00+00:00"
    review_path = write_json(tmp_path / "review.json", review)
    with pytest.raises(ArtifactQualityEvidenceError, match="future"):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )


def test_validator_rejects_rollout_source_revision_and_future_drift(tmp_path):
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
    value["generated_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ArtifactQualityEvidenceError, match="future"):
        validate_artifact_quality_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=file_hash(rollout_path),
        )


def test_compiler_rejects_artifact_disabled_rollout(tmp_path):
    rollout_path = write_json(
        tmp_path / "rollout.json",
        {
            "release_id": RELEASE_ID,
            "capabilities": {"artifact_services": False},
        },
    )
    native = native_value(tmp_path)
    native_path = write_json(tmp_path / "native.json", native)
    review_path = write_json(tmp_path / "review.json", review_value(native_path, native))
    with pytest.raises(
        ArtifactQualityEvidenceError,
        match="artifact_services=true",
    ):
        compile_artifact_quality_evidence(
            rollout_path=rollout_path,
            native_results_path=native_path,
            human_review_path=review_path,
        )
