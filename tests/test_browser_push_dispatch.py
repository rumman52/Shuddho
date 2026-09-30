from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("temporalio")

from services.coworker.worker import Dispatcher


def test_browser_push_dispatch_is_bounded_and_concurrent():
    barrier = threading.Barrier(2)
    delivered = []

    class Notifications:
        def claim_browser_push_deliveries(self, limit):
            assert limit == 2
            return ["push-a", "push-b"]

        def deliver_browser_push(self, delivery_id):
            barrier.wait(timeout=1)
            delivered.append(delivery_id)

    dispatcher = Dispatcher.__new__(Dispatcher)
    dispatcher.container = SimpleNamespace(
        settings=SimpleNamespace(
            browser_push_enabled=True,
            browser_push_max_in_flight=2,
        )
    )
    asyncio.run(asyncio.wait_for(
        dispatcher.dispatch_browser_push(Notifications()),
        timeout=2,
    ))
    assert sorted(delivered) == ["push-a", "push-b"]


def test_browser_push_dispatch_skips_when_killed():
    class Notifications:
        def claim_browser_push_deliveries(self, _limit):
            raise AssertionError("kill switch must prevent claims")

    dispatcher = Dispatcher.__new__(Dispatcher)
    dispatcher.container = SimpleNamespace(
        settings=SimpleNamespace(
            browser_push_enabled=False,
            browser_push_max_in_flight=2,
        )
    )
    asyncio.run(dispatcher.dispatch_browser_push(Notifications()))
