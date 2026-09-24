from __future__ import annotations

import pytest

from scripts import staging_live_social_publishing as live


def test_guard_is_explicit(monkeypatch):
    monkeypatch.delenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_SOCIAL_PUBLISHING",
        raising=False,
    )
    with pytest.raises(live.SocialPublishingValidationFailure):
        live.require_guard()
    monkeypatch.setenv(
        "SHUDDHO_STAGING_ALLOW_LIVE_SOCIAL_PUBLISHING",
        "true",
    )
    live.require_guard()


def test_connection_requires_one_active_linkedin_social_account():
    value = live.connection_for([{
        "id": "connection",
        "provider": "linkedin",
        "capability": "social",
        "active": True,
        "email": "urn:li:person:member_123",
    }])
    assert value["id"] == "connection"
    with pytest.raises(live.SocialPublishingValidationFailure):
        live.connection_for([])


def prepared_action():
    connection = {"id": "connection"}
    preview = {
        "provider": "linkedin",
        "connection_id": "connection",
        "account": "urn:li:person:member_123",
        "payload": {
            "kind": "social_publish_linkedin",
            "text": "Synthetic staging post #Shuddho",
        },
        "social_publishing": {
            "provider": "linkedin",
            "author": "connected_personal_member",
            "visibility": "public",
            "media": "none",
            "scheduling": "none",
            "social_read": "none",
            "agent_authority": "none",
        },
    }
    preview["approval_scope"] = {
        "contract": "shuddho.consequential-action",
        "contract_version": 5,
        "provider": "linkedin",
        "capability": "social",
        "account": "urn:li:person:member_123",
        "destinations": {},
        "policy": {"social_publishing": preview["social_publishing"]},
    }
    prepared = {
        "id": "11111111-1111-1111-1111-111111111111",
        "state": "awaiting_approval",
        "approved_at": None,
        "receipt": None,
        "preview": preview,
        "preview_hash": live.digest(preview),
    }
    return connection, prepared


def test_prepared_post_binds_exact_member_text_and_bounded_policy():
    connection, prepared = prepared_action()
    live.validate_prepared(
        prepared,
        connection,
        "Synthetic staging post #Shuddho",
    )
    changed = dict(prepared)
    changed_preview = dict(prepared["preview"])
    changed_preview["social_publishing"] = dict(
        prepared["preview"]["social_publishing"],
        social_read="allowed",
    )
    changed["preview"] = changed_preview
    changed["preview_hash"] = live.digest(changed_preview)
    with pytest.raises(live.SocialPublishingValidationFailure):
        live.validate_prepared(
            changed,
            connection,
            "Synthetic staging post #Shuddho",
        )


def test_completed_post_requires_single_execution_and_provider_receipt():
    _, prepared = prepared_action()
    completed = {
        **prepared,
        "state": "succeeded",
        "audit": [
            {"action": "action.prepared"},
            {"action": "action.approved"},
            {"action": "action.execution_started"},
            {"action": "action.succeeded"},
        ],
        "receipt": {
            "provider": "linkedin",
            "provider_id": "urn:li:share:12345",
            "status": "post_published",
            "author": "urn:li:person:member_123",
            "visibility": "PUBLIC",
        },
    }
    live.validate_completion(completed, prepared)
    completed["receipt"] = dict(
        completed["receipt"],
        author="urn:li:person:other",
    )
    with pytest.raises(live.SocialPublishingValidationFailure):
        live.validate_completion(completed, prepared)
