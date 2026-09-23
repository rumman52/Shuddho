from __future__ import annotations

import pytest

from scripts import staging_live_action_recipients as live


def test_directory_and_exact_recipient_validation():
    rows = live.validate_directory({"enabled": True, "recipients": []})
    assert rows == []

    value = {
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Finance",
        "email": "finance@example.test",
        "created_at": "2026-09-24T00:00:00+00:00",
        "updated_at": "2026-09-24T00:00:00+00:00",
    }
    assert live.validate_recipient(
        value,
        name="Finance",
        email="finance@example.test",
    ) == value["id"]

    changed = dict(value, email="other@example.test")
    with pytest.raises(live.RecipientValidationFailure):
        live.validate_recipient(
            changed,
            name="Finance",
            email="finance@example.test",
        )


def test_owner_isolation_absence_check():
    rows = [{"id": "a", "email": "a@example.test"}]
    live.require_absent(rows, recipient_id="b", emails={"b@example.test"})
    with pytest.raises(live.RecipientValidationFailure):
        live.require_absent(rows, recipient_id="a", emails={"b@example.test"})
    with pytest.raises(live.RecipientValidationFailure):
        live.require_absent(rows, recipient_id="b", emails={"a@example.test"})


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_RECIPIENTS", raising=False)
    with pytest.raises(live.RecipientValidationFailure):
        live.require_guard()
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_LIVE_ACTION_RECIPIENTS", "true")
    live.require_guard()
