from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from services.coworker.actions import _bounded_provider_receipt


def test_phase4_consequential_provider_receipts_are_bounded_and_serializable():
    assert _bounded_provider_receipt({"provider_id": "confirmed-1"}) is True
    assert _bounded_provider_receipt({}) is False
    assert _bounded_provider_receipt({"bad": {1, 2, 3}}) is False
    assert _bounded_provider_receipt({"value": "x" * 70000}) is False
