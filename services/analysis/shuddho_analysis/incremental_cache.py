from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class ContentHashCache(Generic[T]):
    def __init__(self, *, ttl_seconds: float = 20.0, max_entries: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def build_key(self, *, namespace: str, payload: object) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default)
        return f"{namespace}:{serialized}"

    def get(self, key: str) -> T | None:
        self._purge_expired()
        entry = self._entries.get(key)
        if entry is None:
            return None
        created_at, value = entry
        if time.monotonic() - created_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return _clone(value)

    def set(self, key: str, value: T) -> T:
        self._purge_expired()
        self._entries[key] = (time.monotonic(), _clone(value))
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return _clone(value)

    def get_or_create(self, key: str, factory: Callable[[], T]) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        return self.set(key, factory())

    def _purge_expired(self) -> None:
        if not self._entries:
            return
        now = time.monotonic()
        expired_keys = [
            key
            for key, (created_at, _) in self._entries.items()
            if now - created_at > self.ttl_seconds
        ]
        for key in expired_keys:
            self._entries.pop(key, None)


def _clone(value: T) -> T:
    model_copy = getattr(value, "model_copy", None)
    if callable(model_copy):
        return model_copy(deep=True)
    if isinstance(value, list):
        return [ _clone(item) for item in value ]  # type: ignore[return-value]
    if isinstance(value, dict):
        return {key: _clone(item) for key, item in value.items()}  # type: ignore[return-value]
    return value


def _json_default(value: object) -> object:
    if hasattr(value, "model_dump"):
        return getattr(value, "model_dump")()
    if hasattr(value, "value"):
        return getattr(value, "value")
    return str(value)
