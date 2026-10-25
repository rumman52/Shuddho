"""Fail-closed replay runner for version-bound Temporal history manifests.

The manifest binds each history to a source revision, workflow type, workflow ID,
relative file path, and SHA-256. Raw histories and exception messages are never
printed. This tool proves repository-level replay only; it does not certify a
production history corpus or an old/new database rollback.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from services.coworker.workflow import (
    AgentWorkflow,
    AgentWorkflowV2,
    AgentWorkflowV3,
    ApprovedActionWorkflow,
    AutomationOccurrenceWorkflow,
    ReportEmailWorkflow,
    ResearchWorkflow,
    WorkServicesWorkflow,
)


MAX_MANIFEST_BYTES = 1024 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024
MAX_TOTAL_HISTORY_BYTES = 256 * 1024 * 1024
MAX_HISTORIES = 500
_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")

# Fixed code-owned registry: a manifest can select a known workflow, never import code.
WORKFLOW_REGISTRY = {
    "shuddho_agent_run_v1": AgentWorkflow,
    "shuddho_agent_run_v2": AgentWorkflowV2,
    "shuddho_agent_run_v3": AgentWorkflowV3,
    "shuddho_automation_occurrence_v1": AutomationOccurrenceWorkflow,
    "shuddho_approved_action_v1": ApprovedActionWorkflow,
    "shuddho_report_email_v1": ReportEmailWorkflow,
    "shuddho_work_services_v1": WorkServicesWorkflow,
    "shuddho_research_v1": ResearchWorkflow,
}


class ReplayManifestError(ValueError):
    """The manifest or one of its bound history files is invalid."""


def _load_manifest(manifest_path: str | Path) -> tuple[str, list[dict]]:
    try:
        resolved_manifest = Path(manifest_path).resolve(strict=True)
    except (OSError, RuntimeError):
        raise ReplayManifestError("manifest path is not a readable file") from None
    if not resolved_manifest.is_file():
        raise ReplayManifestError("manifest path is not a readable file")
    try:
        if resolved_manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ReplayManifestError("manifest exceeds the size limit")
        raw_manifest = resolved_manifest.read_bytes()
        data = json.loads(raw_manifest.decode("utf-8"))
    except ReplayManifestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ReplayManifestError("manifest is not valid UTF-8 JSON") from None

    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ReplayManifestError("unsupported manifest schema")
    source_revision = data.get("source_revision")
    if not isinstance(source_revision, str) or not _SHA_RE.fullmatch(source_revision):
        raise ReplayManifestError("source_revision must be a 40-character Git SHA")
    entries = data.get("histories")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_HISTORIES:
        raise ReplayManifestError("histories must contain between 1 and 500 entries")

    root = resolved_manifest.parent.resolve(strict=True)
    seen_case_ids: set[str] = set()
    seen_workflow_ids: set[str] = set()
    total_history_bytes = 0
    prepared: list[dict] = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise ReplayManifestError("history entry is not an object")
        case_id = entry.get("case_id")
        if not isinstance(case_id, str) or not _CASE_ID_RE.fullmatch(case_id) or case_id in seen_case_ids:
            raise ReplayManifestError("case_id is invalid or duplicated")
        seen_case_ids.add(case_id)

        workflow_type = entry.get("workflow_type")
        workflow_class = WORKFLOW_REGISTRY.get(workflow_type) if isinstance(workflow_type, str) else None
        if workflow_class is None:
            raise ReplayManifestError("unsupported workflow type")

        workflow_id = entry.get("workflow_id")
        if not isinstance(workflow_id, str) or not workflow_id.strip() or len(workflow_id) > 1000 or "\x00" in workflow_id:
            raise ReplayManifestError("workflow_id is invalid")
        if workflow_id in seen_workflow_ids:
            raise ReplayManifestError("workflow_id is duplicated")
        seen_workflow_ids.add(workflow_id)

        relative_name = entry.get("path")
        if (
            not isinstance(relative_name, str)
            or not relative_name
            or len(relative_name) > 1024
            or relative_name.startswith("/")
            or "\\" in relative_name
            or any(part in {"", ".", ".."} for part in relative_name.split("/"))
        ):
            raise ReplayManifestError("history path must be relative to the manifest directory")
        try:
            history_path = (root / Path(*relative_name.split("/"))).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ReplayManifestError("history path must be relative to the manifest directory") from None
        if not history_path.is_relative_to(root) or not history_path.is_file():
            raise ReplayManifestError("history path must be relative to the manifest directory")

        try:
            history_size = history_path.stat().st_size
            if history_size > MAX_HISTORY_BYTES:
                raise ReplayManifestError("history exceeds the size limit")

            remaining_total_bytes = MAX_TOTAL_HISTORY_BYTES - total_history_bytes
            if history_size > remaining_total_bytes:
                raise ReplayManifestError("total history size exceeds the size limit")

            # Bound the actual read as well as the stat check to avoid an oversized
            # replacement/growth between stat() and read_bytes().
            with history_path.open("rb") as history_file:
                raw_history = history_file.read(
                    min(MAX_HISTORY_BYTES, remaining_total_bytes) + 1
                )
            if len(raw_history) > MAX_HISTORY_BYTES:
                raise ReplayManifestError("history exceeds the size limit")
            if len(raw_history) > remaining_total_bytes:
                raise ReplayManifestError("total history size exceeds the size limit")
            if len(raw_history) != history_size:
                raise ReplayManifestError("history changed while reading")
            total_history_bytes += len(raw_history)
        except ReplayManifestError:
            raise
        except OSError:
            raise ReplayManifestError("history file is not readable") from None

        expected_digest = entry.get("sha256")
        if not isinstance(expected_digest, str) or not _DIGEST_RE.fullmatch(expected_digest):
            raise ReplayManifestError("history SHA-256 is invalid")
        actual_digest = hashlib.sha256(raw_history).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ReplayManifestError("history SHA-256 mismatch")

        try:
            history = WorkflowHistory.from_json(workflow_id, raw_history.decode("utf-8"))
        except Exception:
            raise ReplayManifestError("history is not valid Temporal history JSON") from None

        prepared.append(
            {
                "case_id": case_id,
                "workflow_type": workflow_type,
                "workflow_class": workflow_class,
                "history": history,
            }
        )

    return source_revision, prepared


async def replay_manifest(manifest_path: str | Path) -> dict:
    """Replay every bound history and return a sanitized machine-readable summary."""
    source_revision, entries = _load_manifest(manifest_path)
    results = []
    for entry in entries:
        try:
            replay_result = await Replayer(workflows=[entry["workflow_class"]]).replay_workflow(
                entry["history"]
            )
            failure = replay_result.replay_failure
            if failure is None:
                results.append(
                    {
                        "case_id": entry["case_id"],
                        "workflow_type": entry["workflow_type"],
                        "status": "replayed",
                    }
                )
            else:
                results.append(
                    {
                        "case_id": entry["case_id"],
                        "workflow_type": entry["workflow_type"],
                        "status": "failed",
                        "error_type": type(failure).__name__,
                    }
                )
        except Exception as error:
            results.append(
                {
                    "case_id": entry["case_id"],
                    "workflow_type": entry["workflow_type"],
                    "status": "failed",
                    "error_type": type(error).__name__,
                }
            )

    return {
        "schema_version": 1,
        "source_revision": source_revision,
        "history_count": len(results),
        "status": "passed" if all(row["status"] == "replayed" for row in results) else "failed",
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Version-bound JSON manifest for Temporal history files")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(replay_manifest(args.manifest))
    except ReplayManifestError as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
