"""Bounded inbox views over existing notices; no scheduling or delivery side effects."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


MAX_DIGEST_ITEMS = 10
MAX_INBOX_ITEMS = 100
DIGEST_WINDOW_SECONDS = 6 * 60 * 60
GROUPED_KINDS = {"personal_suggestion", "personal_suggestion_event"}


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    return instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant


def _group_key(item: dict) -> tuple:
    if item["kind"] not in GROUPED_KINDS:
        return (item["workspace_id"], item["kind"], item["id"])
    bucket = int(_instant(item["visible_at"]).timestamp()) // DIGEST_WINDOW_SECONDS
    return (item["workspace_id"], item["kind"], bucket)


def _digest_id(owner: str, key: tuple, items: list[dict]) -> str:
    identity = json.dumps(
        ["notification_digest_v1", owner, key, sorted(item["id"] for item in items)],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def digest_views(owner: str, items: list[dict]) -> list[dict]:
    """Group only the newest bounded inbox snapshot, preserving every input notice."""
    ordered = sorted(items, key=lambda item: (
        _instant(item["visible_at"]), _instant(item["created_at"]), item["id"]
    ), reverse=True)[:MAX_INBOX_ITEMS]
    groups: dict[tuple, list[dict]] = {}
    for item in ordered:
        groups.setdefault(_group_key(item), []).append(item)
    result = []
    for key, members in groups.items():
        for offset in range(0, len(members), MAX_DIGEST_ITEMS):
            chunk = members[offset:offset + MAX_DIGEST_ITEMS]
            count = len(chunk)
            label = "goal suggestions" if chunk[0]["kind"] == "personal_suggestion" else "connected-source updates"
            result.append({
                "id": _digest_id(owner, key, chunk),
                "kind": chunk[0]["kind"],
                "title": chunk[0]["title"] if count == 1 else f"{count} {label}",
                "count": count,
                "unread_count": sum(item["state"] == "delivered" for item in chunk),
                "latest_at": chunk[0]["visible_at"],
                "notifications": [
                    {**{name: value for name, value in item.items() if name != "workspace_id"},
                     "read_digest_id": _digest_id(owner, key, [item])}
                    for item in chunk
                ],
            })
    return sorted(result, key=lambda item: (_instant(item["latest_at"]), item["id"]), reverse=True)
