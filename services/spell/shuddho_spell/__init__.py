from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import SpellCandidate, SpellEngine

__all__ = ["SpellCandidate", "SpellEngine"]


def __getattr__(name: str) -> object:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from .engine import SpellCandidate, SpellEngine

    exports = {
        "SpellCandidate": SpellCandidate,
        "SpellEngine": SpellEngine,
    }
    return exports[name]
