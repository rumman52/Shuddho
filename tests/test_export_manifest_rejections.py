"""Exercise both native export and persisted-manifest rejection boundaries."""
from __future__ import annotations

import asyncio

import pytest

from services.coworker.errors import CoworkerError
from services.coworker.models import Step
from services.coworker.runner import DocumentRunner
from test_coworker import FakeModel, account, container, new_task


def _runner_with_output_transform(container, transform):
    runner = DocumentRunner(container, FakeModel())
    original_renderer = runner.renderer

    def render(draft, sources, **options):
        outputs = list(original_renderer(draft, sources, **options))
        return transform(outputs)

    runner.renderer = render
    return runner


async def _assert_export_rejected_before_publication(runner, container, owner, task_id):
    await runner.phase(task_id, "extract")
    await runner.phase(task_id, "draft")

    with pytest.raises(CoworkerError) as rejected:
        await runner.phase(task_id, "export")
    assert rejected.value.code == "export_invalid"

    current = container.repository.get_task(owner, task_id)
    assert current["state"] == "running"
    assert current["artifacts"] == []
    assert container.repository.step(task_id, "export") is None
    prefix = f"{owner}/outputs/{task_id}/"
    assert container.storage.inventory(prefix=prefix) == []


@pytest.mark.parametrize("malformation", ("missing", "duplicate", "unexpected"))
def test_export_rejects_malformed_native_inventory_before_publication(container, malformation):
    owner = account(container)
    task = new_task(container, owner)

    def transform(outputs):
        if malformation == "missing":
            return outputs[:-1]
        if malformation == "duplicate":
            return [*outputs[:-1], outputs[0]]
        return [
            *outputs[:-1],
            ("unexpected.txt", "text/plain; charset=utf-8", b"unapproved artifact"),
        ]

    runner = _runner_with_output_transform(container, transform)
    asyncio.run(_assert_export_rejected_before_publication(runner, container, owner, task["id"]))


@pytest.mark.parametrize("native_filename", ("report.docx", "report.pdf"))
def test_export_rejects_unreadable_native_bytes_before_publication(container, native_filename):
    owner = account(container)
    task = new_task(container, owner)

    def transform(outputs):
        return [
            (
                filename,
                content_type,
                b"not a readable native document" if filename == native_filename else body,
            )
            for filename, content_type, body in outputs
        ]

    runner = _runner_with_output_transform(container, transform)
    asyncio.run(_assert_export_rejected_before_publication(runner, container, owner, task["id"]))


@pytest.mark.parametrize("malformation", ("missing", "duplicate", "unexpected"))
def test_complete_rejects_missing_duplicate_or_unexpected_persisted_manifest_entry(
    container, malformation
):
    owner = account(container)
    task = new_task(container, owner)

    async def scenario():
        runner = DocumentRunner(container, FakeModel())
        await runner.phase(task["id"], "extract")
        await runner.phase(task["id"], "draft")
        await runner.phase(task["id"], "export")

        persisted = container.repository.step(task["id"], "export")
        assert persisted is not None
        artifacts = [dict(item) for item in persisted["artifacts"]]
        assert len(artifacts) == 4

        prefix = f"{owner}/outputs/{task['id']}/"
        assert len(container.storage.inventory(prefix=prefix)) == 4

        if malformation == "missing":
            artifacts.pop()
        elif malformation == "duplicate":
            artifacts[-1] = dict(artifacts[0])
        else:
            artifacts[-1] = {**artifacts[-1], "filename": "unexpected.txt"}

        # Simulate out-of-band corruption of the persisted export checkpoint.
        # The immutable repository API is intentionally not used to rewrite it.
        with container.repository.sessions.begin() as session:
            checkpoint = session.get(Step, (task["id"], "export"))
            assert checkpoint is not None
            output = dict(checkpoint.output)
            output["artifacts"] = artifacts
            checkpoint.output = output

        assert container.repository.step(task["id"], "export")["artifacts"] == artifacts

        with pytest.raises(CoworkerError) as rejected:
            await runner.phase(task["id"], "complete")
        assert rejected.value.code == "export_invalid"

        current = container.repository.get_task(owner, task["id"])
        assert current["state"] == "running"
        assert current["artifacts"] == []
        # The four valid objects remain private; none is published as an Artifact.
        assert len(container.storage.inventory(prefix=prefix)) == 4

    asyncio.run(scenario())
