"""Deterministic identity for a built Coworker runtime, not a release approval."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from importlib import metadata
from pathlib import Path

_MAX_BUILD_INPUT_BYTES = 32 * 1024 * 1024


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    # O_NONBLOCK prevents a substituted FIFO from hanging before fstat.
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise ValueError("secure build input reading is unavailable")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_BUILD_INPUT_BYTES:
                raise ValueError("build input must be a bounded regular file")
            digest = hashlib.sha256()
            total = 0
            while chunk := os.read(fd, 65536):
                total += len(chunk)
                if total > _MAX_BUILD_INPUT_BYTES:
                    raise ValueError("build input exceeds size limit")
                digest.update(chunk)
            after = os.fstat(fd)
            current = path.lstat()
            def signature(s):
                return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(current) or total != before.st_size:
                raise ValueError("build input changed during fingerprinting")
            return digest.hexdigest()
        finally:
            os.close(fd)
    except OSError as exc:
        raise ValueError("build input is missing, inaccessible, or a symlink") from exc


def _identity_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or value != value.strip() or any(not c.isprintable() for c in value):
        raise ValueError(f"invalid {label}")
    return value


def _distribution_inventory(distributions) -> list[list[str]]:
    if distributions is None:
        distributions = ((dist.metadata.get("Name"), dist.version) for dist in metadata.distributions())
    inventory: dict[str, str] = {}
    for name, version in distributions:
        name = _identity_text(name, "distribution name")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name):
            raise ValueError("invalid distribution name")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        version = _identity_text(version, "distribution version")
        if normalized in inventory and inventory[normalized] != version:
            raise ValueError("conflicting distribution versions")
        inventory[normalized] = version
    return [[name, version] for name, version in sorted(inventory.items())]


def compute_build_digest(*, root: Path | None = None, source_revision: str,
                         distributions=None, python_implementation: str | None = None,
                         python_version: str | None = None, platform_identity: str | None = None) -> str:
    """Bind the source claim, lock/project bytes and observed Python installation.

    This is a deterministic metadata fingerprint, not a signature or an OCI digest.
    """
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("invalid source revision")
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    return canonical_sha256({
        "fingerprint_version": 1,
        "source_revision": source_revision,
        "pyproject_sha256": _file_digest(root / "pyproject.toml"),
        "lock_sha256": _file_digest(root / "uv.lock"),
        "distributions": _distribution_inventory(distributions),
        "python_implementation": _identity_text(platform.python_implementation() if python_implementation is None else python_implementation, "Python implementation"),
        "python_version": _identity_text(platform.python_version() if python_version is None else python_version, "Python version"),
        "platform_identity": _identity_text(f"{platform.system().lower()}-{platform.machine().lower()}" if platform_identity is None else platform_identity, "platform identity"),
    })
