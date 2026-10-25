"""A-03 Temporal history replay contract tests.

The legacy workflow below is frozen from workflow.py at source revision
b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d. Histories generated here are
synthetic compatibility fixtures, not production history exports.
"""
import asyncio
import hashlib
import json
import os
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("temporalio", reason="Install the coworker extra for Temporal replay tests")
pytestmark = [
    pytest.mark.coworker_integration,
    pytest.mark.skipif(
        os.getenv("SHUDDHO_TEMPORAL_TESTS") != "true",
        reason="Set SHUDDHO_TEMPORAL_TESTS=true to run the Temporal test server",
    ),
]

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from services.coworker.workflow import WorkServicesWorkflow
from scripts.temporal_history_replay import ReplayManifestError, replay_manifest
from scripts import temporal_history_replay as replay_runner


LEGACY_SOURCE_REVISION = "b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d"
TASK_QUEUE = "shuddho-a03-legacy-history-replay"


@workflow.defn(name="shuddho_work_services_v1")
class LegacyWorkServicesWorkflow:
    """Frozen success/error command sequence for the pre-existing workflow type."""

    @workflow.run
    async def run(self, task_id: str):
        try:
            for phase in ("extract", "draft", "export", "complete"):
                await workflow.execute_activity(
                    "shuddho_work_phase_v1",
                    {"task_id": task_id, "phase": phase},
                    start_to_close_timeout=timedelta(seconds=180),
                    schedule_to_close_timeout=timedelta(minutes=6),
                    heartbeat_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=3),
                        maximum_attempts=2,
                    ),
                )
        except ActivityError as error:
            cause = error.cause
            code = cause.type if isinstance(cause, ApplicationError) else "workflow_failed"
            message = (
                str(cause.message)
                if isinstance(cause, ApplicationError)
                else "This task could not finish. Please try again."
            )
            await workflow.execute_activity(
                "shuddho_document_failed_v1",
                {"task_id": task_id, "code": code, "message": message},
                start_to_close_timeout=timedelta(seconds=20),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )


@activity.defn
async def shuddho_work_phase_v1(value: dict) -> None:
    if value["task_id"].endswith("-failure") and value["phase"] == "draft":
        raise ApplicationError("synthetic legacy activity failure", type="legacy_phase_failure")


@activity.defn
async def shuddho_document_failed_v1(_value: dict) -> None:
    return None


def _manifest_entry(case_id: str, workflow_id: str, path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "case_id": case_id,
        "workflow_type": "shuddho_work_services_v1",
        "workflow_id": workflow_id,
        "path": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_frozen_legacy_success_and_handled_failure_histories_replay(tmp_path):
    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            entries = []
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[LegacyWorkServicesWorkflow],
                activities=[shuddho_work_phase_v1, shuddho_document_failed_v1],
            ):
                for case_id, task_id in (
                    ("legacy-success", "a03-task-success"),
                    ("legacy-handled-failure", "a03-task-failure"),
                ):
                    workflow_id = f"a03-{case_id}"
                    handle = await env.client.start_workflow(
                        LegacyWorkServicesWorkflow.run,
                        task_id,
                        id=workflow_id,
                        task_queue=TASK_QUEUE,
                    )
                    await handle.result()
                    history_json = (await handle.fetch_history()).to_json()
                    history_path = tmp_path / f"{case_id}.json"
                    history_path.write_text(history_json, encoding="utf-8")
                    entries.append(_manifest_entry(case_id, workflow_id, history_path))

            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source_revision": LEGACY_SOURCE_REVISION,
                        "histories": entries,
                    }
                ),
                encoding="utf-8",
            )
            artifact_dir_value = os.getenv("SHUDDHO_TEMPORAL_HISTORY_ARTIFACT_DIR")
            if artifact_dir_value:
                artifact_dir = Path(artifact_dir_value)
                artifact_dir.mkdir(parents=True, exist_ok=True)
                for entry in entries:
                    shutil.copyfile(tmp_path / entry["path"], artifact_dir / entry["path"])
                shutil.copyfile(manifest_path, artifact_dir / "manifest.json")
            result = await replay_manifest(manifest_path)
            assert result["status"] == "passed"
            assert result["source_revision"] == LEGACY_SOURCE_REVISION
            assert [row["case_id"] for row in result["results"]] == [
                "legacy-success",
                "legacy-handled-failure",
            ]
            assert all(row["status"] == "replayed" for row in result["results"])

    asyncio.run(scenario())


def test_manifest_rejects_aggregate_history_bytes_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_runner, "MAX_TOTAL_HISTORY_BYTES", 9, raising=False)

    class FakeWorkflowHistory:
        @staticmethod
        def from_json(workflow_id, raw_json):
            return {"workflow_id": workflow_id, "raw_json": raw_json}

    monkeypatch.setattr(replay_runner, "WorkflowHistory", FakeWorkflowHistory)

    entries = []
    for case_id, content in (("history-one", b"12345"), ("history-two", b"67890")):
        history_path = tmp_path / f"{case_id}.json"
        history_path.write_bytes(content)
        entries.append(_manifest_entry(case_id, f"a03-{case_id}", history_path))

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": LEGACY_SOURCE_REVISION,
                "histories": entries,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReplayManifestError, match="total history size"):
        replay_runner._load_manifest(manifest_path)


def test_replay_manifest_rejects_unknown_workflow_type(tmp_path):
    history_path = tmp_path / "history.json"
    history_path.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": LEGACY_SOURCE_REVISION,
                "histories": [
                    {
                        "case_id": "unknown",
                        "workflow_type": "unregistered_workflow",
                        "workflow_id": "a03-unknown",
                        "path": history_path.name,
                        "sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReplayManifestError, match="unsupported workflow type"):
        asyncio.run(replay_manifest(manifest_path))


def test_replay_manifest_rejects_path_traversal(tmp_path):
    outside_path = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside_path.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": LEGACY_SOURCE_REVISION,
                "histories": [
                    {
                        "case_id": "escape",
                        "workflow_type": "shuddho_work_services_v1",
                        "workflow_id": "a03-escape",
                        "path": f"../{outside_path.name}",
                        "sha256": hashlib.sha256(outside_path.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReplayManifestError, match="relative to the manifest directory"):
        asyncio.run(replay_manifest(manifest_path))


def test_replay_manifest_rejects_history_checksum_mismatch(tmp_path):
    history_path = tmp_path / "history.json"
    history_path.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": LEGACY_SOURCE_REVISION,
                "histories": [
                    {
                        "case_id": "tampered",
                        "workflow_type": "shuddho_work_services_v1",
                        "workflow_id": "a03-tampered",
                        "path": history_path.name,
                        "sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReplayManifestError, match="SHA-256 mismatch"):
        asyncio.run(replay_manifest(manifest_path))
