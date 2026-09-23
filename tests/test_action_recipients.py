from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from pydantic import ValidationError
from sqlalchemy import select

from action_samples import action_request, connected, enable_actions
from test_coworker import account, container, signed_client
from services.coworker.errors import CoworkerError
from services.coworker.models import ActionRecipient, AuditEvent
from services.coworker.recipient_schemas import RecipientUpsert


def enable_recipients(container, *, maximum=100):
    enable_actions(container)
    settings = replace(
        container.settings,
        action_recipients_enabled=True,
        max_action_recipients=maximum,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.recipients.settings = settings
    return settings


def test_recipient_schema_normalizes_without_accepting_display_names():
    value = RecipientUpsert(name="  Finance   Team  ", email="ALICE@Example.ORG")
    assert value.name == "Finance Team"
    assert value.email == "ALICE@example.org"
    with pytest.raises(ValidationError):
        RecipientUpsert(name="Finance", email="Alice <alice@example.org>")
    with pytest.raises(ValidationError):
        RecipientUpsert(name="\x00Finance", email="alice@example.org")


def test_recipient_flag_requires_actions(container):
    with pytest.raises(ValueError, match="Action recipients require"):
        replace(container.settings, action_recipients_enabled=True).validate()
    with pytest.raises(CoworkerError) as disabled:
        container.recipients.create(
            account(container),
            RecipientUpsert(name="Finance", email="finance@example.org"),
        )
    assert disabled.value.code == "action_recipients_disabled"


def test_owner_scoped_crud_conflicts_limits_and_audit(container):
    enable_recipients(container, maximum=2)
    owner = account(container)
    other = account(container, "bob")

    first = container.recipients.create(
        owner,
        RecipientUpsert(name="Finance", email="finance@example.org"),
    )
    assert container.recipients.list(other) == []
    assert [item["id"] for item in container.recipients.list(owner)] == [first["id"]]

    with pytest.raises(CoworkerError) as duplicate_name:
        container.recipients.create(
            owner,
            RecipientUpsert(name="finance", email="other@example.org"),
        )
    assert duplicate_name.value.code == "action_recipient_conflict"

    second = container.recipients.create(
        owner,
        RecipientUpsert(name="Legal", email="legal@example.org"),
    )
    with pytest.raises(CoworkerError) as limit:
        container.recipients.create(
            owner,
            RecipientUpsert(name="People", email="people@example.org"),
        )
    assert limit.value.code == "action_recipient_limit"

    updated = container.recipients.update(
        owner,
        first["id"],
        RecipientUpsert(name="Finance Ops", email="finance-ops@example.org"),
    )
    assert updated["email"] == "finance-ops@example.org"
    with pytest.raises(CoworkerError):
        container.recipients.update(
            other,
            first["id"],
            RecipientUpsert(name="Stolen", email="stolen@example.org"),
        )

    settings = replace(container.settings, action_recipients_enabled=False)
    container.settings = settings
    container.recipients.settings = settings
    assert len(container.recipients.list(owner)) == 2
    assert container.recipients.delete(owner, second["id"])["deleted"] is True

    with container.repository.sessions() as db:
        actions = list(db.scalars(select(AuditEvent.action).where(
            AuditEvent.owner_id == owner,
            AuditEvent.resource_id == first["id"],
        )).all())
        assert set(actions) == {"action_recipient.created", "action_recipient.updated"}


def test_saved_recipient_never_mutates_existing_action_preview(container):
    enable_recipients(container)
    owner = account(container)
    saved = container.recipients.create(
        owner,
        RecipientUpsert(name="Finance", email="finance@example.org"),
    )
    connection = connected(container.actions.repo, owner, "email")
    request = action_request(connection)
    request.payload.to = [saved["email"]]
    action = container.actions.repo.prepare(owner, request, str(uuid4()))

    container.recipients.update(
        owner,
        saved["id"],
        RecipientUpsert(name="Finance", email="new-finance@example.org"),
    )
    stored = container.actions.repo.get(owner, action["id"])
    assert stored["preview"]["payload"]["to"] == ["finance@example.org"]


def test_recipient_api_is_authenticated_and_owner_scoped(container, signed_client):
    enable_recipients(container)
    client, headers = signed_client

    assert client.get("/api/v1/action-recipients").status_code == 401
    created = client.post(
        "/api/v1/action-recipients",
        headers=headers("alice"),
        json={"name": "Finance", "email": "finance@example.org"},
    )
    assert created.status_code == 201
    recipient_id = created.json()["id"]

    own = client.get("/api/v1/action-recipients", headers=headers("alice"))
    other = client.get("/api/v1/action-recipients", headers=headers("bob"))
    assert own.status_code == 200 and own.json()["enabled"] is True
    assert [item["email"] for item in own.json()["recipients"]] == ["finance@example.org"]
    assert other.status_code == 200 and other.json()["recipients"] == []

    assert client.put(
        f"/api/v1/action-recipients/{recipient_id}",
        headers=headers("bob"),
        json={"name": "Wrong", "email": "wrong@example.org"},
    ).status_code == 404
    assert client.delete(
        f"/api/v1/action-recipients/{recipient_id}",
        headers=headers("alice"),
    ).status_code == 200


def test_account_erasure_removes_saved_recipients(container):
    enable_recipients(container)
    owner = account(container)
    saved = container.recipients.create(
        owner,
        RecipientUpsert(name="Finance", email="finance@example.org"),
    )
    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.get(ActionRecipient, saved["id"]) is None
