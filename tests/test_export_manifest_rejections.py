"""Ensure report/email exports cannot publish incomplete file inventories.

These are local negative regressions. The renderer integration suite separately
checks real DOCX/PDF bytes and the required owner-scoped artifact retrieval.
"""
from __future__ import annotations

import asyncio
import pytest

from test_coworker import account, container, new_task, FakeModel
from services.coworker.runner import DocumentRunner
from services.coworker.errors import CoworkerError


@pytest.mark.parametrize("malformation", ("missing", "duplicate", "unexpected"))
def test_export_missing_duplicate_or_unexpected_file_never_publishes(container, malformation):
    owner = account(container)
    task = new_task(container, owner)
    outputs = [
        ("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"synthetic report"),
        ("report.pdf", "application/pdf", b"synthetic pdf"),
        ("email-draft.txt", "text/plain", b"synthetic unsent email"),
        ("source-manifest.json", "application/json", b'{"sources": []}'),
    ]
    if malformation == "missing":
        outputs.pop()
    elif malformation == "duplicate":
        outputs[-1] = outputs[0]
    else:
        outputs[-1] = ("unexpected.txt", "text/plain", b"unapproved artifact")

    async def scenario():
        runner = DocumentRunner(container, FakeModel(), renderer=lambda *_args, **_kwargs: outputs)
        await runner.phase(task["id"], "extract")
        await runner.phase(task["id"], "draft")
        await runner.phase(task["id"], "export")
        with pytest.raises(CoworkerError, match="generated files were incomplete"):
            await runner.phase(task["id"], "complete")
        current = container.repository.get_task(owner, task["id"])
        assert current["state"] == "running"
        assert current["artifacts"] == []

    asyncio.run(scenario())
