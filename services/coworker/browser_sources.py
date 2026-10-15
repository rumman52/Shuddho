"""Deterministic, server-owned identity for an Agent browser capture artifact.

A browser command has only one successful terminal receipt. The private blob is
written before the Agent transaction, then its Artifact row is committed with
the ToolReceipt, allowing the existing orphan sweeper to recover failed writes.
No user/model value can select the object key or destination.
"""
from __future__ import annotations

import re
from uuid import NAMESPACE_URL, UUID, uuid5

BROWSER_SOURCE_MEDIA_TYPE = "text/plain; charset=utf-8"


def browser_source_identity(owner: str, command_id: str) -> tuple[str, str, str]:
    # Shuddho account IDs are SHA-256-derived 64-character hex strings,
    # unlike the 36-character UUID browser command IDs.
    if not isinstance(owner, str) or re.fullmatch(r"[0-9a-f]{64}", owner) is None:
        raise ValueError("Invalid owner account ID for private source")
    owner_id = owner
    command = str(UUID(command_id))
    key = f"agent-browser-sources/{owner_id}/{command}/visible-text.txt"
    artifact_id = str(uuid5(NAMESPACE_URL, f"shuddho:agent-browser-source:{owner_id}:{command}"))
    filename = f"browser-source-{command}.txt"
    return artifact_id, key, filename
