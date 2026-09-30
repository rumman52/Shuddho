from __future__ import annotations

import pytest

pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from services.coworker.config import Settings
from services.coworker.web_push import WebPushSender, b64url_encode, validate_push_endpoint


def test_web_push_rejects_arbitrary_egress_and_invalid_ports():
    with pytest.raises(ValueError):
        validate_push_endpoint("https://example.com/push")
    with pytest.raises(ValueError):
        validate_push_endpoint("https://fcm.googleapis.com:bad/push")
    assert validate_push_endpoint("https://fcm.googleapis.com/fcm/send/abc").startswith("https://")


def test_web_push_payload_uses_single_bounded_aes128gcm_record(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'push.sqlite3'}",
        auth_issuer="https://identity.example.test/auth/v1",
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        personal_goals_enabled=True,
        agent_runtime_enabled=True,
        automations_enabled=True,
        browser_push_enabled=True,
        web_push_vapid_private_key=b64url_encode((1).to_bytes(32, "big")),
        web_push_vapid_subject="mailto:ops@example.test",
        web_push_encryption_key=b64url_encode(b"e" * 32),
    )
    ua_private = ec.generate_private_key(ec.SECP256R1())
    ua_public = ua_private.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    payload = WebPushSender._encrypt_payload(
        b64url_encode(ua_public),
        b64url_encode(b"a" * 16),
        b'{"body":"generic"}',
    )
    assert len(payload) <= 4096
    assert int.from_bytes(payload[16:20], "big") == 4096
    assert payload[20] == 65
    assert payload[21] == 4
    assert len(payload[21:86]) == 65
