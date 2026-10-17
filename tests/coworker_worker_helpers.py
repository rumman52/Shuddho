"""Helpers for tests that exercise the registered worker dispatch boundary."""
from __future__ import annotations

import asyncio


async def dispatch_tick(container, client):
    """Run one dispatcher tick as a real registered worker and close its lifecycle."""
    worker_id = await asyncio.to_thread(
        container.repository.register_worker,
        task_queue=container.settings.task_queue,
        source_revision=container.settings.source_revision,
    )
    state = await asyncio.to_thread(container.repository.heartbeat_worker, worker_id)
    if state != "running":
        raise AssertionError(f"test dispatcher worker did not become running: {state}")
    try:
        from services.coworker.worker import Dispatcher
        await Dispatcher(container, client, worker_id).tick()
    finally:
        await asyncio.to_thread(container.repository.mark_worker_drained, worker_id)


async def run_dispatcher(container, client, stop):
    """Run the dispatcher loop under a registered identity until stop is signalled."""
    worker_id = await asyncio.to_thread(
        container.repository.register_worker,
        task_queue=container.settings.task_queue,
        source_revision=container.settings.source_revision,
    )
    state = await asyncio.to_thread(container.repository.heartbeat_worker, worker_id)
    if state != "running":
        raise AssertionError(f"test dispatcher worker did not become running: {state}")
    try:
        from services.coworker.worker import Dispatcher
        await Dispatcher(container, client, worker_id).run(stop)
    finally:
        await asyncio.to_thread(container.repository.mark_worker_drained, worker_id)
