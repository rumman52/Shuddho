"""Ensure report/email exports reject malformed manifests before publication.

The renderer-output boundary and persisted-checkpoint boundary are distinct:
invalid renderer output must never reach storage, while a corrupted manifest
after a valid native export must never become published task artifacts.
"""
from __future__ import annotations

import asyncio

import pytest

from test_coworker import account, container, new_task, FakeModel
from services.coworker.errors import CoworkerError
from services.coworker.exports import render_in_subprocess
from services.coworker.runner import DocumentRunner


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF = "application/pdf"
TEXT = "text/plain; charset=utf-8"
JSON = "application/json"
EXPECTED_FILES = {"report.docx", "report.pdf", "email-draft.txt", "source-manifest.json"}


def _new_report_task(container):
    owner = account(container)
    task = new_task(container, owner, skill_id="report_email", output_language="en")
    return owner, task


def _track_storage_puts(container, monkeypatch):
    calls = []
    original_put = container.storage.put

    def tracked_put(key, body, content_type):
        calls.append((key, content_type, len(body)))
        return original_put(key, body, content_type)

    # Keep the real local object-store operation; observe only its boundary.
    monkeypatch.setattr(container.storage, "put", tracked_put)
    return calls


def _assert_failed_without_published_artifacts(container, owner, task_id):
    current = container.repository.get_task(owner, task_id)
    assert current["state"] == "failed"
    assert current["artifacts"] == []


@pytest.mark.parametrize("malformation", ("missing", "duplicate", "unexpected"))
def test_export_missing_duplicate_or_unexpected_renderer_file_set_never_publishes(
    container, monkeypatch, malformation
):
    owner, task = _new_report_task(container)
    outputs = [
        ("report.docx", DOCX, b"synthetic renderer bytes"),
        ("report.pdf", PDF, b"synthetic renderer bytes"),
        ("email-draft.txt", TEXT, b"Project update\n\nThe team completed 12 reviews."),
        ("source-manifest.json", JSON, b'{"sources": []}'),
    ]
    if malformation == "missing":
        outputs.pop()
    elif malformation == "duplicate":
        outputs[-1] = outputs[0]
    else:
        outputs[-1] = ("unexpected.txt", TEXT, b"unapproved artifact")

    storage_puts = _track_storage_puts(container, monkeypatch)
    runner = DocumentRunner(
        container, FakeModel(), renderer=lambda *_args, **_kwargs: outputs
    )

    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))

    assert error.value.code == "export_invalid"
    assert storage_puts == []
    _assert_failed_without_published_artifacts(container, owner, task["id"])


@pytest.mark.parametrize("malformed_filename", ("report.docx", "report.pdf"))
def test_export_malformed_native_bytes_never_reach_storage(
    container, monkeypatch, malformed_filename
):
    owner, task = _new_report_task(container)

    def malformed_native_renderer(package, sources, **options):
        outputs = render_in_subprocess(package, sources, **options)
        return [
            (
                filename,
                content_type,
                b"not a valid native document"
                if filename == malformed_filename
                else body,
            )
            for filename, content_type, body in outputs
        ]

    storage_puts = _track_storage_puts(container, monkeypatch)
    runner = DocumentRunner(
        container, FakeModel(), renderer=malformed_native_renderer
    )

    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))

    assert error.value.code == "export_invalid"
    assert storage_puts == []
    _assert_failed_without_published_artifacts(container, owner, task["id"])


@pytest.mark.parametrize("malformation", ("missing", "duplicate", "unexpected"))
def test_complete_missing_duplicate_or_unexpected_persisted_manifest_never_publishes(
    container, monkeypatch, malformation
):
    owner, task = _new_report_task(container)
    storage_puts = _track_storage_puts(container, monkeypatch)
    original_step = container.repository.step

    def corrupted_export_checkpoint(task_id, phase):
        checkpoint = original_step(task_id, phase)
        if phase != "export" or checkpoint is None:
            return checkpoint

        # Corrupt only the value read by completion; leave the durable checkpoint
        # and the successfully stored native bytes unchanged.
        artifacts = [dict(item) for item in checkpoint["artifacts"]]
        if malformation == "missing":
            artifacts.pop()
        elif malformation == "duplicate":
            artifacts[-1] = dict(artifacts[0])
        else:
            artifacts[-1] = {**artifacts[-1], "filename": "unexpected.txt"}
        return {**checkpoint, "artifacts": artifacts}

    monkeypatch.setattr(container.repository, "step", corrupted_export_checkpoint)
    runner = DocumentRunner(container, FakeModel())

    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))

    assert error.value.code == "export_invalid"
    assert len(storage_puts) == 4
    assert {key.rsplit("/", 1)[-1] for key, _content_type, _size in storage_puts} == EXPECTED_FILES
    _assert_failed_without_published_artifacts(container, owner, task["id"])
