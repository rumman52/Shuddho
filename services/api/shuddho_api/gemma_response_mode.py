from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class GemmaResponseMode:
    requested: str
    effective: str
    warnings: tuple[str, ...] = ()


def resolve_gemma_response_mode(environ: Mapping[str, str]) -> GemmaResponseMode:
    """Resolve the wire contract once, overriding unsafe production drift.

    Legacy modes are deliberately gated for local compatibility tests. Merely
    setting the old response-mode variable is not enough to enable them.
    """
    requested = (environ.get("SHUDDHO_GEMMA_RESPONSE_MODE") or "function_call").strip().lower()
    allow_legacy = (environ.get("SHUDDHO_ALLOW_LEGACY_GEMMA_RESPONSE_MODE") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if requested == "function_call":
        return GemmaResponseMode(requested, "function_call")
    if requested in {"json_mime", "json_schema"} and allow_legacy:
        return GemmaResponseMode(requested, requested, ("gemma_legacy_response_mode_enabled",))
    warning = "gemma_legacy_response_mode_overridden" if requested in {"json_mime", "json_schema"} else "gemma_invalid_response_mode_overridden"
    return GemmaResponseMode(requested or "function_call", "function_call", (warning,))
