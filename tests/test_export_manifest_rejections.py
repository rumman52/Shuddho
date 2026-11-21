"""Ensure report/email exports reject malformed manifests before publication.

The renderer-output boundary and persisted-checkpoint boundary are distinct:
invalid renderer output must never reach storage, while a corrupted manifest
after a valid native export must never become published task artifacts.
"""
from __future__ import annotations

import asyncio
import io
import json
from copy import deepcopy
from html import escape

from docx import Document
from pypdf import PdfReader
from weasyprint import HTML

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


@pytest.mark.parametrize("mutation", ("omit_sources", "replace_digest", "inject_foreign"))
def test_export_rejects_manifest_provenance_not_matching_authorized_draft_sources(
    container, monkeypatch, mutation
):
    """A native renderer cannot rewrite the trusted provenance of a task."""
    owner, task = _new_report_task(container)

    def rewritten_manifest_renderer(package, sources, **options):
        assert sources and sources[0]["id"] == "notes"
        outputs = render_in_subprocess(package, sources, **options)
        rewritten = []
        for filename, content_type, body in outputs:
            if filename == "source-manifest.json":
                manifest = json.loads(body.decode("utf-8"))
                if mutation == "omit_sources":
                    manifest["sources"] = []
                elif mutation == "replace_digest":
                    manifest["sources"][0]["sha256"] = "0" * 64
                else:
                    manifest["sources"].append({
                        "id": "foreign-source", "label": "Not selected",
                        "sha256": "f" * 64,
                    })
                body = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
            rewritten.append((filename, content_type, body))
        return rewritten

    storage_puts = _track_storage_puts(container, monkeypatch)
    runner = DocumentRunner(container, FakeModel(), renderer=rewritten_manifest_renderer)

    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))

    assert error.value.code == "export_invalid"
    assert storage_puts == []
    _assert_failed_without_published_artifacts(container, owner, task["id"])


def test_complete_rejects_provenance_snapshot_changed_after_valid_native_export(
    container, monkeypatch
):
    """Readback must still bind the files to the draft's current source snapshot."""
    owner, task = _new_report_task(container)
    storage_puts = _track_storage_puts(container, monkeypatch)
    original_step = container.repository.step
    draft_reads = 0

    def changed_draft_snapshot(task_id, phase):
        nonlocal draft_reads
        checkpoint = original_step(task_id, phase)
        if phase == "draft" and checkpoint is not None:
            draft_reads += 1
            if draft_reads == 2:
                # Keep trusted IDs intact: the existing reference-set check
                # must pass so the source hash mismatch reaches readback.
                altered = [{**source, "sha256": "0" * 64} for source in checkpoint["sources"]]
                return {**checkpoint, "sources": altered}
        return checkpoint

    monkeypatch.setattr(container.repository, "step", changed_draft_snapshot)
    runner = DocumentRunner(container, FakeModel())

    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))

    assert draft_reads == 2
    assert error.value.code == "artifact_invalid"
    assert len(storage_puts) == 4
    _assert_failed_without_published_artifacts(container, owner, task["id"])


@pytest.mark.parametrize("tamper", ("missing_claim", "missing_section_reference", "missing_source_entry"))
def test_day6_export_rejects_valid_docx_with_unapproved_report_content(
    container, monkeypatch, tamper
):
    """A perfectly valid Office file must not silently replace the reviewed draft."""
    owner, task = _new_report_task(container)

    def renderer(package, sources, **options):
        outputs = render_in_subprocess(package, sources, **options)
        changed = []
        for filename, content_type, body in outputs:
            if filename == "report.docx":
                document = Document(io.BytesIO(body))
                matches = 0
                for paragraph in document.paragraphs:
                    value = paragraph.text.strip()
                    if tamper == "missing_claim" and "The team completed 12 reviews." in value:
                        paragraph.text = "The team skipped every review."
                        matches += 1
                    elif tamper == "missing_section_reference" and value == "[notes]":
                        paragraph.text = "[unselected-source]"
                        matches += 1
                    elif (tamper == "missing_source_entry" and value.startswith("[notes]")
                          and value != "[notes]"):
                        paragraph.text = "[unselected-source] Unauthorized material"
                        matches += 1
                assert matches > 0, "The source fixture did not contain the material to corrupt"
                data = io.BytesIO()
                document.save(data)
                body = data.getvalue()
                assert Document(io.BytesIO(body)).paragraphs
            changed.append((filename, content_type, body))
        return changed

    puts = _track_storage_puts(container, monkeypatch)
    runner = DocumentRunner(container, FakeModel(), renderer=renderer)
    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))
    assert error.value.code == "export_invalid"
    assert puts == []
    _assert_failed_without_published_artifacts(container, owner, task["id"])


@pytest.mark.parametrize("tamper", ("wrong_title", "wrong_claim", "wrong_references"))
def test_day6_export_rejects_readable_but_unrelated_pdf(
    container, monkeypatch, tamper
):
    """PDF parseability is insufficient when the approved source/fact differs."""
    owner, task = _new_report_task(container)

    def renderer(package, sources, **options):
        outputs = render_in_subprocess(package, sources, **options)
        report = package.report
        heading = report.sections[0].heading
        if tamper == "wrong_title":
            title = "A different customer and report"
            claim = report.summary
            source_id = "notes"
        elif tamper == "wrong_claim":
            title = report.title
            claim = "The team has not completed any reviews."
            source_id = "notes"
        else:
            title = report.title
            claim = report.summary
            source_id = "foreign-source"
        html = (
            f"<h1>{escape(title)}</h1><p>{escape(claim)}</p>"
            f"<h2>{escape(heading)}</h2><p>{escape(claim)}</p>"
            f"<p>[{escape(source_id)}]</p><p>[{escape(source_id)}] Provided notes</p>"
        )
        pdf = HTML(string=html).write_pdf()
        assert PdfReader(io.BytesIO(pdf)).pages[0].extract_text().strip()
        return [
            (filename, content_type, pdf if filename == "report.pdf" else body)
            for filename, content_type, body in outputs
        ]

    puts = _track_storage_puts(container, monkeypatch)
    runner = DocumentRunner(container, FakeModel(), renderer=renderer)
    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))
    assert error.value.code == "export_invalid"
    assert puts == []
    _assert_failed_without_published_artifacts(container, owner, task["id"])


@pytest.mark.parametrize("tamper", ("changed_claim", "changed_reference"))
def test_day6_complete_rejects_native_artifacts_when_reviewed_draft_changes_after_export(
    container, monkeypatch, tamper
):
    """The final private-object readback must use the current persisted draft, not just a SHA."""
    owner, task = _new_report_task(container)
    puts = _track_storage_puts(container, monkeypatch)
    original_step = container.repository.step
    draft_reads = 0

    def changed_reviewed_draft(task_id, phase):
        nonlocal draft_reads
        checkpoint = original_step(task_id, phase)
        if phase != "draft" or checkpoint is None:
            return checkpoint
        draft_reads += 1
        if draft_reads != 2:
            return checkpoint
        changed = deepcopy(checkpoint)
        if tamper == "changed_claim":
            changed["draft"]["report"]["summary"] = "No reviews were completed."
            changed["draft"]["report"]["sections"][0]["paragraphs"][0] = "No reviews were completed."
        else:
            # Keep the same authorized source snapshot: only the reviewed
            # section's intended citation changes after native export.
            changed["draft"]["report"]["sections"][0]["source_ids"] = []
        return changed

    monkeypatch.setattr(container.repository, "step", changed_reviewed_draft)
    runner = DocumentRunner(container, FakeModel())
    with pytest.raises(CoworkerError) as error:
        asyncio.run(runner.run_for_test(task["id"]))
    assert draft_reads == 2
    assert error.value.code == "artifact_invalid"
    assert len(puts) == 4
    _assert_failed_without_published_artifacts(container, owner, task["id"])


def test_day6_research_native_docx_must_contain_exact_selected_finding_and_quote():
    """A source-backed research DOCX cannot replace its finding or cited quote."""
    from coworker_samples import work_draft
    from services.coworker.exports import validate_day6_exports

    draft = work_draft("research", "en")
    sources = [{
        "id": "web-1", "kind": "web", "label": "Original study",
        "url": "https://example.org/study",
        "retrieved_at": "2026-11-18T02:00:00Z",
        "source_date": None, "sha256": "a" * 64,
    }]
    outputs = render_in_subprocess(draft, sources, skill_id="research")
    validate_day6_exports("research", draft, outputs, expected_sources=sources)
    for tamper in ("finding", "citation"):
        changed = []
        for filename, content_type, body in outputs:
            if filename == "research-report.docx":
                document = Document(io.BytesIO(body))
                matches = 0
                for paragraph in document.paragraphs:
                    if tamper == "finding" and paragraph.text == draft.findings[0].text:
                        paragraph.text = "An entirely different claim."
                        matches += 1
                    elif tamper == "citation" and draft.findings[0].citations[0].quote in paragraph.text:
                        paragraph.text = "Evidence [1]: An invented quotation"
                        matches += 1
                assert matches > 0
                data = io.BytesIO()
                document.save(data)
                body = data.getvalue()
            changed.append((filename, content_type, body))
        with pytest.raises(ValueError, match="DOCX"):
            validate_day6_exports("research", draft, changed, expected_sources=sources)
