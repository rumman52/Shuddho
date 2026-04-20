from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}
RUNTIME_COLUMNS = (
    "word",
    "normalized_word",
    "source",
    "is_trusted",
    "is_common",
    "is_active",
    "layer",
    "include_in_runtime",
    "include_as_candidate",
    "review_state",
)
REVIEW_COLUMNS = (
    "word",
    "normalized_word",
    "source",
    "layer",
    "review_state",
    "reason",
)
ENTITY_SOURCE_MARKERS = ("wikidata", "geonames", "entity", "person", "place", "organization", "named")


@dataclass(frozen=True)
class RuntimeLexiconBuildPaths:
    clean_csv_path: Path
    review_csv_path: Path
    summary_path: Path
    provenance_path: Path
    runtime_dir: Path

    @classmethod
    def defaults(cls, repo_root: Path | None = None) -> "RuntimeLexiconBuildPaths":
        root = repo_root or Path(__file__).resolve().parents[1]
        return cls(
            clean_csv_path=root / "data" / "imports" / "lexicon" / "words_clean.csv",
            review_csv_path=root / "data" / "imports" / "lexicon" / "words_review_flagged.csv",
            summary_path=root / "data" / "imports" / "lexicon" / "cleaning_summary.txt",
            provenance_path=root / "data" / "imports" / "lexicon" / "provenance.json",
            runtime_dir=root / "data" / "runtime" / "lexicon",
        )


@dataclass(frozen=True)
class RuntimeLexiconBuildResult:
    runtime_words_path: Path
    runtime_metadata_path: Path
    runtime_review_path: Path
    runtime_reject_path: Path
    accepted_word_count: int
    candidate_word_count: int
    correction_map_count: int
    layer_counts: dict[str, int]


def build_runtime_lexicon(paths: RuntimeLexiconBuildPaths | None = None) -> RuntimeLexiconBuildResult:
    resolved_paths = paths or RuntimeLexiconBuildPaths.defaults()
    provenance = _load_json_object(resolved_paths.provenance_path)

    resolved_paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_words_path = resolved_paths.runtime_dir / "runtime_words.csv"
    runtime_review_path = resolved_paths.runtime_dir / "runtime_review.csv"
    runtime_reject_path = resolved_paths.runtime_dir / "runtime_reject.csv"
    runtime_metadata_path = resolved_paths.runtime_dir / "runtime_metadata.json"

    accepted_words: list[str] = []
    candidate_words: list[str] = []
    correction_map_count = 0
    seen_accepted: set[str] = set()
    seen_candidates: set[str] = set()
    layer_counts = {
        "core_formal_words": 0,
        "accepted_variants": 0,
        "named_entities": 0,
        "colloquial_or_dialect_review": 0,
        "reject_list": 0,
    }

    with (
        resolved_paths.clean_csv_path.open("r", encoding="utf-8-sig", newline="") as clean_handle,
        runtime_words_path.open("w", encoding="utf-8", newline="") as runtime_handle,
        runtime_review_path.open("w", encoding="utf-8", newline="") as review_handle,
        runtime_reject_path.open("w", encoding="utf-8", newline="") as reject_handle,
    ):
        clean_reader = csv.DictReader(clean_handle)
        runtime_writer = csv.DictWriter(runtime_handle, fieldnames=RUNTIME_COLUMNS)
        review_writer = csv.DictWriter(review_handle, fieldnames=REVIEW_COLUMNS)
        reject_writer = csv.DictWriter(reject_handle, fieldnames=REVIEW_COLUMNS)
        runtime_writer.writeheader()
        review_writer.writeheader()
        reject_writer.writeheader()

        for row_index, row in enumerate(clean_reader, start=1):
            word = _require_text(row, "word", resolved_paths.clean_csv_path, row_index)
            normalized_word = _require_text(row, "normalized_word", resolved_paths.clean_csv_path, row_index)
            source = _require_text(row, "source", resolved_paths.clean_csv_path, row_index)
            is_trusted = _parse_bool(row.get("is_trusted"), "is_trusted", resolved_paths.clean_csv_path, row_index)
            is_common = _parse_bool(row.get("is_common"), "is_common", resolved_paths.clean_csv_path, row_index)
            is_active = _parse_bool(row.get("is_active"), "is_active", resolved_paths.clean_csv_path, row_index)

            layer, review_state, include_in_runtime, include_as_candidate = _classify_row(
                word=word,
                normalized_word=normalized_word,
                source=source,
                is_trusted=is_trusted,
                is_common=is_common,
                is_active=is_active,
            )
            layer_counts[layer] += 1

            if include_in_runtime:
                runtime_writer.writerow(
                    {
                        "word": word,
                        "normalized_word": normalized_word,
                        "source": source,
                        "is_trusted": int(is_trusted),
                        "is_common": int(is_common),
                        "is_active": int(is_active),
                        "layer": layer,
                        "include_in_runtime": 1,
                        "include_as_candidate": int(include_as_candidate),
                        "review_state": review_state,
                    }
                )
                if normalized_word not in seen_accepted:
                    seen_accepted.add(normalized_word)
                    accepted_words.append(normalized_word)
                if include_as_candidate and normalized_word not in seen_candidates:
                    seen_candidates.add(normalized_word)
                    candidate_words.append(normalized_word)
                if word != normalized_word:
                    correction_map_count += 1
                continue

            target_writer = reject_writer if layer == "reject_list" else review_writer
            target_writer.writerow(
                {
                    "word": word,
                    "normalized_word": normalized_word,
                    "source": source,
                    "layer": layer,
                    "review_state": review_state,
                    "reason": review_state,
                }
            )

    with (
        resolved_paths.review_csv_path.open("r", encoding="utf-8-sig", newline="") as flagged_handle,
        runtime_review_path.open("a", encoding="utf-8", newline="") as review_handle,
    ):
        flagged_reader = csv.DictReader(flagged_handle)
        review_writer = csv.DictWriter(review_handle, fieldnames=REVIEW_COLUMNS)
        for row_index, row in enumerate(flagged_reader, start=1):
            original_word = _require_text(row, "original_word", resolved_paths.review_csv_path, row_index)
            normalized_word = _require_text(row, "normalized_word", resolved_paths.review_csv_path, row_index)
            reasons = _require_text(row, "reasons", resolved_paths.review_csv_path, row_index)
            review_writer.writerow(
                {
                    "word": original_word,
                    "normalized_word": normalized_word,
                    "source": resolved_paths.review_csv_path.name,
                    "layer": "colloquial_or_dialect_review",
                    "review_state": "flagged_import_review",
                    "reason": reasons,
                }
            )

    metadata = {
        "format": "shuddho-runtime-lexicon-v1",
        "policy_version": provenance.get("policy_version", "shuddho-lexicon-policy-v1"),
        "runtime_source": runtime_words_path.name,
        "runtime_source_of_truth": "built_runtime_csv",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "clean_csv_path": str(resolved_paths.clean_csv_path),
            "review_csv_path": str(resolved_paths.review_csv_path),
            "summary_path": str(resolved_paths.summary_path),
            "provenance_path": str(resolved_paths.provenance_path),
        },
        "input_checksums": {
            "clean_csv": _checksum_path(resolved_paths.clean_csv_path),
            "review_csv": _checksum_path(resolved_paths.review_csv_path),
            "summary": _checksum_path(resolved_paths.summary_path),
            "provenance": _checksum_path(resolved_paths.provenance_path),
        },
        "outputs": {
            "runtime_words_path": str(runtime_words_path),
            "runtime_review_path": str(runtime_review_path),
            "runtime_reject_path": str(runtime_reject_path),
        },
        "counts": {
            "accepted_word_count": len(accepted_words),
            "candidate_word_count": len(candidate_words),
            "correction_map_count": correction_map_count,
            "layer_counts": layer_counts,
        },
        "layers": {
            "core_formal_words": "trusted, active, common rows with canonical forms",
            "accepted_variants": "trusted, active rows that map a surface form to a canonical form",
            "named_entities": "trusted, active rows from explicit named-entity style sources",
            "colloquial_or_dialect_review": "trusted but non-common rows kept out of runtime until reviewed",
            "reject_list": "inactive or untrusted rows excluded from runtime",
            "user_dictionary": "runtime request-layer vocabulary merged per user, not baked into the shared artifact",
        },
        "user_dictionary_supported": True,
        "provenance": provenance,
    }
    runtime_metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    return RuntimeLexiconBuildResult(
        runtime_words_path=runtime_words_path,
        runtime_metadata_path=runtime_metadata_path,
        runtime_review_path=runtime_review_path,
        runtime_reject_path=runtime_reject_path,
        accepted_word_count=len(accepted_words),
        candidate_word_count=len(candidate_words),
        correction_map_count=correction_map_count,
        layer_counts=layer_counts,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Shuddho runtime lexicon from governed import files.")
    parser.add_argument(
        "--runtime-dir",
        help="Optional override for the runtime output directory.",
    )
    args = parser.parse_args()

    default_paths = RuntimeLexiconBuildPaths.defaults()
    build_paths = default_paths
    if args.runtime_dir:
        build_paths = RuntimeLexiconBuildPaths(
            clean_csv_path=default_paths.clean_csv_path,
            review_csv_path=default_paths.review_csv_path,
            summary_path=default_paths.summary_path,
            provenance_path=default_paths.provenance_path,
            runtime_dir=Path(args.runtime_dir),
        )

    result = build_runtime_lexicon(build_paths)
    print(
        json.dumps(
            {
                "runtime_words_path": str(result.runtime_words_path),
                "runtime_metadata_path": str(result.runtime_metadata_path),
                "runtime_review_path": str(result.runtime_review_path),
                "runtime_reject_path": str(result.runtime_reject_path),
                "accepted_word_count": result.accepted_word_count,
                "candidate_word_count": result.candidate_word_count,
                "correction_map_count": result.correction_map_count,
                "layer_counts": result.layer_counts,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _classify_row(
    *,
    word: str,
    normalized_word: str,
    source: str,
    is_trusted: bool,
    is_common: bool,
    is_active: bool,
) -> tuple[str, str, bool, bool]:
    if not is_active:
        return "reject_list", "inactive_import_row", False, False
    if not is_trusted:
        return "reject_list", "untrusted_import_row", False, False
    if _looks_named_entity_source(source):
        return "named_entities", "named_entity_source", True, True
    if word != normalized_word:
        return "accepted_variants", "normalized_surface_variant", True, True
    if is_common:
        return "core_formal_words", "common_runtime_word", True, True
    return "colloquial_or_dialect_review", "trusted_non_common_requires_review", False, False


def _looks_named_entity_source(source: str) -> bool:
    normalized = source.strip().lower()
    return any(marker in normalized for marker in ENTITY_SOURCE_MARKERS)


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _checksum_path(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _require_text(row: dict[str, str | None], key: str, csv_path: Path, row_index: int) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{csv_path} row {row_index} has an empty {key!r} value.")
    return value


def _parse_bool(value: str | None, key: str, csv_path: Path, row_index: int) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{csv_path} row {row_index} has an invalid boolean value for {key!r}: {value!r}")


if __name__ == "__main__":
    main()
