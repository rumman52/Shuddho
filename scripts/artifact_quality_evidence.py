from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class ArtifactQualityEvidenceError(RuntimeError):
    pass


EXPECTED_LANGUAGES = ["ar", "bn", "en", "zh"]
EXPECTED_FORMATS = ["pptx", "xlsx"]
EXPECTED_RENDERED = {
    "presentation-en.pdf",
    "spreadsheet-en.pdf",
    "presentation-bn.pdf",
    "spreadsheet-bn.pdf",
    "presentation-ar.pdf",
    "spreadsheet-ar.pdf",
    "presentation-zh-dense.pdf",
    "spreadsheet-zh-long.pdf",
}
EXPECTED_FORMULA_OUTCOMES = {
    "changed": {"cost": 87.5, "total": 103.5},
    "zero": {"cost": 0, "total": 16},
    "missing": {"cost": None, "total": None},
    "negative": {"cost": -37.5, "total": -21.5},
}
REVIEW_CHECKS = {
    "editable_open",
    "text_visible",
    "rtl_layout",
    "chart_pagination",
    "spreadsheet_recalculation",
    "visual_overflow",
    "human_semantic_review",
}
EVIDENCE_KEYS = {
    "schema_version",
    "mode",
    "release_id",
    "generated_at",
    "source_revision",
    "rollout_manifest_sha256",
    "native_results_sha256",
    "human_review_sha256",
    "languages",
    "formats",
    "gate_decision",
    "failures",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ArtifactQualityEvidenceError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ArtifactQualityEvidenceError(f"{label} must contain a JSON object.")
    return value


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ArtifactQualityEvidenceError(f"{label} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ArtifactQualityEvidenceError(f"{label} must be an ISO-8601 timestamp.") from None
    if parsed.tzinfo is None:
        raise ArtifactQualityEvidenceError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ArtifactQualityEvidenceError(f"{label} must be a lowercase SHA-256.")
    return value


def require_revision(value: object, label: str = "source_revision") -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ArtifactQualityEvidenceError(
            f"{label} must be a full lowercase 40-character Git SHA-1."
        )
    return value


def _exact_string_list(value: object, expected: list[str], label: str) -> None:
    if not isinstance(value, list) or value != expected:
        raise ArtifactQualityEvidenceError(
            f"{label} must exactly match the documented ordered set."
        )


def validate_native_results(
    value: dict,
    *,
    expected_source_revision: str | None = None,
) -> datetime:
    expected_keys = {
        "schema_version",
        "generated_at",
        "source_revision",
        "languages",
        "formats",
        "rendered",
        "formula_edits",
    }
    if set(value) != expected_keys:
        raise ArtifactQualityEvidenceError(
            "Native Office results have an unexpected schema."
        )
    if value["schema_version"] != 2:
        raise ArtifactQualityEvidenceError(
            "Native Office results must use schema_version=2."
        )
    generated = parse_time(value["generated_at"], "native.generated_at")
    revision = require_revision(value["source_revision"], "native.source_revision")
    if expected_source_revision is not None and revision != expected_source_revision:
        raise ArtifactQualityEvidenceError(
            "Native Office results source revision does not match."
        )
    _exact_string_list(value["languages"], EXPECTED_LANGUAGES, "native.languages")
    _exact_string_list(value["formats"], EXPECTED_FORMATS, "native.formats")
    rendered = value["rendered"]
    if (
        not isinstance(rendered, list)
        or len(rendered) != len(set(rendered))
        or set(rendered) != EXPECTED_RENDERED
    ):
        raise ArtifactQualityEvidenceError(
            "Native Office results do not contain the exact required render set."
        )
    formula_edits = value["formula_edits"]
    if (
        not isinstance(formula_edits, dict)
        or set(formula_edits) != set(EXPECTED_FORMULA_OUTCOMES)
    ):
        raise ArtifactQualityEvidenceError(
            "Native Office results do not contain the exact recalculation cases."
        )
    for name, expected in EXPECTED_FORMULA_OUTCOMES.items():
        result = formula_edits[name]
        if (
            not isinstance(result, dict)
            or set(result) != {"cost", "total", "recalculated"}
            or result.get("recalculated") is not True
            or result.get("cost") != expected["cost"]
            or result.get("total") != expected["total"]
        ):
            raise ArtifactQualityEvidenceError(
                f"Native Office recalculation case {name!r} did not match the expected outcome."
            )
    return generated


def validate_human_review(
    value: dict,
    *,
    release_id: str,
    native_results_sha256: str,
    source_revision: str,
    native_generated_at: datetime,
) -> datetime:
    expected_keys = {
        "schema_version",
        "release_id",
        "generated_at",
        "source_revision",
        "native_results_sha256",
        "reviewer_reference",
        "languages",
        "formats",
        "checks",
        "failures",
    }
    if set(value) != expected_keys:
        raise ArtifactQualityEvidenceError(
            "Artifact human review has an unexpected schema."
        )
    if value["schema_version"] != 1:
        raise ArtifactQualityEvidenceError(
            "Artifact human review must use schema_version=1."
        )
    if value["release_id"] != release_id:
        raise ArtifactQualityEvidenceError(
            "Artifact human review release_id does not match."
        )
    review_time = parse_time(value["generated_at"], "review.generated_at")
    if review_time < native_generated_at:
        raise ArtifactQualityEvidenceError(
            "Artifact human review cannot predate the native Office results."
        )
    if require_revision(value["source_revision"], "review.source_revision") != source_revision:
        raise ArtifactQualityEvidenceError(
            "Artifact human review source revision does not match native results."
        )
    if (
        require_sha256(
            value["native_results_sha256"],
            "review.native_results_sha256",
        )
        != native_results_sha256
    ):
        raise ArtifactQualityEvidenceError(
            "Artifact human review does not bind the supplied native results."
        )
    reviewer = value["reviewer_reference"]
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 500:
        raise ArtifactQualityEvidenceError(
            "Artifact human review requires a bounded reviewer_reference."
        )
    _exact_string_list(value["languages"], EXPECTED_LANGUAGES, "review.languages")
    _exact_string_list(value["formats"], EXPECTED_FORMATS, "review.formats")
    checks = value["checks"]
    if (
        not isinstance(checks, dict)
        or set(checks) != REVIEW_CHECKS
        or any(result is not True for result in checks.values())
    ):
        raise ArtifactQualityEvidenceError(
            "Every documented artifact human-review check must pass."
        )
    if value["failures"] != []:
        raise ArtifactQualityEvidenceError(
            "Artifact human review contains unresolved failures."
        )
    return review_time


def compile_artifact_quality_evidence(
    *,
    rollout_path: Path,
    native_results_path: Path,
    human_review_path: Path,
) -> dict:
    rollout = load_json(rollout_path, "rollout manifest")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ArtifactQualityEvidenceError(
            "Rollout manifest release_id is required."
        )
    capabilities = rollout.get("capabilities")
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("artifact_services") is not True
    ):
        raise ArtifactQualityEvidenceError(
            "Artifact quality evidence is valid only for a rollout with artifact_services=true."
        )
    native = load_json(native_results_path, "native Office results")
    native_time = validate_native_results(native)
    source_revision = require_revision(
        native["source_revision"],
        "native.source_revision",
    )
    native_hash = sha256_file(native_results_path)
    review = load_json(human_review_path, "artifact human review")
    review_time = validate_human_review(
        review,
        release_id=release_id,
        native_results_sha256=native_hash,
        source_revision=source_revision,
        native_generated_at=native_time,
    )
    return {
        "schema_version": 1,
        "mode": "artifact_quality",
        "release_id": release_id,
        "generated_at": max(datetime.now(timezone.utc), review_time).isoformat(),
        "source_revision": source_revision,
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "native_results_sha256": native_hash,
        "human_review_sha256": sha256_file(human_review_path),
        "languages": list(EXPECTED_LANGUAGES),
        "formats": list(EXPECTED_FORMATS),
        "gate_decision": "PASS",
        "failures": [],
    }


def validate_artifact_quality_evidence(
    value: dict,
    *,
    release_id: str,
    rollout_sha256: str,
    expected_source_revision: str | None = None,
) -> datetime:
    if not isinstance(value, dict) or set(value) != EVIDENCE_KEYS:
        raise ArtifactQualityEvidenceError(
            "Artifact quality evidence has an unexpected schema."
        )
    if value["schema_version"] != 1 or value["mode"] != "artifact_quality":
        raise ArtifactQualityEvidenceError(
            "Artifact quality evidence has an unsupported schema or mode."
        )
    if value["release_id"] != release_id:
        raise ArtifactQualityEvidenceError(
            "Artifact quality evidence release_id does not match."
        )
    require_sha256(rollout_sha256, "Expected rollout manifest SHA-256")
    if value["rollout_manifest_sha256"] != rollout_sha256:
        raise ArtifactQualityEvidenceError(
            "Artifact quality evidence does not bind the current rollout manifest."
        )
    revision = require_revision(value["source_revision"])
    if expected_source_revision is not None and revision != expected_source_revision:
        raise ArtifactQualityEvidenceError(
            "Artifact quality source revision does not match the live planner evidence."
        )
    require_sha256(
        value["native_results_sha256"],
        "artifact.native_results_sha256",
    )
    require_sha256(
        value["human_review_sha256"],
        "artifact.human_review_sha256",
    )
    _exact_string_list(value["languages"], EXPECTED_LANGUAGES, "artifact.languages")
    _exact_string_list(value["formats"], EXPECTED_FORMATS, "artifact.formats")
    if value["gate_decision"] != "PASS" or value["failures"] != []:
        raise ArtifactQualityEvidenceError(
            "Artifact quality evidence did not pass cleanly."
        )
    return parse_time(value["generated_at"], "artifact.generated_at")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile rollout-bound PA-11 artifact-quality evidence from native "
            "Office QA and an explicit human review."
        )
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--native-results", type=Path, required=True)
    parser.add_argument("--human-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compile_artifact_quality_evidence(
            rollout_path=args.rollout,
            native_results_path=args.native_results,
            human_review_path=args.human_review,
        )
    except ArtifactQualityEvidenceError as error:
        raise SystemExit(str(error)) from None
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
