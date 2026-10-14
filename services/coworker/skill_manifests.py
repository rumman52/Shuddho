"""CW-11: inert, code-reviewed skill manifest identities (no dynamic tool grants).

This module only validates reviewed references to existing WorkSkill and
ToolSpec contracts. It never installs a skill, registers a tool, persists a
grant, selects a provider, or changes runtime dispatch.
"""
from __future__ import annotations

import hashlib
import inspect
from importlib import metadata
import json
import math
import re
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .agent_tools import TOOLS, ToolSpec
from .agent_schemas import ResearchToolInput
from .errors import CoworkerError
from .skills import SKILLS, WorkSkill


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SkillResourceLimits:
    max_tool_calls: int
    max_wall_seconds: int
    max_output_bytes: int


@dataclass(frozen=True)
class CoworkerSkillManifest:
    name: str
    version: str
    instruction_sha256: str
    input_schema_sha256: str
    output_schema_sha256: str
    tool_contract_sha256: str
    tool_names: tuple[str, ...]
    resource_limits: SkillResourceLimits
    rollback_version: str

    def review_sha256(self) -> str:
        return _digest(asdict(self))


def _reviewed_instruction_identity(skill: WorkSkill) -> str:
    return _digest({
        "id": skill.id, "version": skill.version,
        "instruction": skill.instruction, "guidance": skill.guidance,
    })


def _schema_identity(tool: ToolSpec, *, output: bool) -> str:
    model = tool.output_model if output else tool.input_model
    return _digest({
        "tool": tool.name, "version": tool.version,
        "schema": model.model_json_schema(),
    })


# Pilot only. All authority still comes from the existing server registry
# and runtime feature flags; the reviewed manifest grants nothing itself.
_PILOT_NAME = "research"
_PILOT_TOOLS = ("research.search",)
# Two 240-second attempts plus 0.25s backoff; frozen scalar review
# ceilings. Materialize a new limits object for every manifest, rather
# than sharing a frozen-dataclass instance that object.__setattr__ can alter.
def _pilot_limits() -> SkillResourceLimits:
    return SkillResourceLimits(
        max_tool_calls=1, max_wall_seconds=481, max_output_bytes=65536,
    )


def _current_pilot_skill_manifest() -> CoworkerSkillManifest:
    skill = SKILLS[_PILOT_NAME]
    spec = TOOLS[_PILOT_TOOLS[0]]
    return CoworkerSkillManifest(
        name=skill.id,
        version=skill.version,
        instruction_sha256=_reviewed_instruction_identity(skill),
        input_schema_sha256=_schema_identity(spec, output=False),
        output_schema_sha256=_schema_identity(spec, output=True),
        # Includes permissions, consequences, retry, risk, budgets and
        # registered schema versions; any code-owned policy expansion
        # invalidates a stored review rather than silently inheriting it.
        tool_contract_sha256=_digest(spec.public()),
        tool_names=_PILOT_TOOLS,
        resource_limits=_pilot_limits(),
        rollback_version=skill.version,
    )


# Explicitly reviewed source snapshots, pinned to GitHub blob identities
# from baseline 3505c502. Updating WorkSkill, tools or input schemas
# REQUIRES reviewing and changing this file (not regenerating on startup).
# The model_json_schema() generator is dependency-sensitive. Pin the exact
# reviewed generator package versions in both the environment and lockfile.
# Whole-file byte checks are unsuitable because uv may rewrite unrelated
# lockfile metadata during installation; a generator upgrade must still deny.
_REVIEWED_SCHEMA_GENERATORS = (
    ("pydantic", "2.12.5"),
    ("pydantic-core", "2.41.5"),
    ("typing-extensions", "4.15.0"),
    ("typing-inspection", "0.4.2"),
)
_REVIEWED_SOURCE_BLOBS = (
    (WorkSkill, "035293bd732a78daba8d7a96dbce48260f6c26d8"),
    (ToolSpec, "72ba55683daf74f582b51e21649e1ec94070f4c8"),
    (ResearchToolInput, "6d1933313e7a5abef1a6a35c36742623154f1a76"),
)


def _require_reviewed_source_blobs() -> None:
    for code_type, reviewed_blob in _REVIEWED_SOURCE_BLOBS:
        path = inspect.getsourcefile(code_type)
        if not path:
            raise ValueError("No audited code-owned source available")
        data = Path(path).read_bytes()
        git_blob = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        if git_blob != reviewed_blob:
            raise ValueError("Skill/tool/schema source changed without review")

    # A different Pydantic implementation can produce different JSON Schema
    # with identical WorkSkill/ToolSpec source. Reject drift before trusting
    # the import-time reviewed manifest as a fixed policy snapshot.
    lockfile = Path(__file__).resolve().parents[2] / "uv.lock"
    try:
        lock = tomllib.loads(lockfile.read_text(encoding="utf-8"))
        versions = {
            item["name"]: item["version"]
            for item in lock["package"]
            if type(item) is dict
            and type(item.get("name")) is str
            and type(item.get("version")) is str
        }
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Audited schema generator lockfile unavailable") from None
    for distribution, expected_version in _REVIEWED_SCHEMA_GENERATORS:
        if versions.get(distribution) != expected_version:
            raise ValueError("Skill schema generator lock version changed without review")
        try:
            version = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            raise ValueError("Audited schema generator dependency unavailable") from None
        if version != expected_version:
            raise ValueError("Skill schema generator version changed without review")


# This object is constructed once from the separately reviewed source
# snapshot and must not dynamically change when policy changes at runtime.
_REVIEWED_PILOT_MANIFEST = _current_pilot_skill_manifest()


def pilot_skill_manifest() -> CoworkerSkillManifest:
    _require_reviewed_source_blobs()
    # Never expose the reference object or its nested limits to the caller.
    return replace(
        _REVIEWED_PILOT_MANIFEST, resource_limits=_pilot_limits(),
    )


def validate_manifest(
    manifest: CoworkerSkillManifest, allowed_tools: frozenset[str],
) -> None:
    """Reject unreviewed versions, changed hashes, new tools and wider budgets.

    A passed validation proves only that this inert manifest still matches the
    code-reviewed pilot. It does not prove a live capability is enabled, a
    permission is granted, a model output is safe, or production is qualified.
    """
    try:
        if type(manifest) is not CoworkerSkillManifest:
            raise ValueError("unrecognized manifest type")
        if set(vars(manifest)) != set(CoworkerSkillManifest.__dataclass_fields__):
            raise ValueError("manifest contains undeclared state")
        for field in (
            "name", "version", "instruction_sha256",
            "input_schema_sha256", "output_schema_sha256",
            "tool_contract_sha256", "rollback_version",
        ):
            if type(getattr(manifest, field)) is not str:
                raise ValueError("manifest contains untrusted identity subclasses")
        for field in (
            "instruction_sha256", "input_schema_sha256",
            "output_schema_sha256", "tool_contract_sha256",
        ):
            if re.fullmatch(r"[0-9a-f]{64}", getattr(manifest, field)) is None:
                raise ValueError("manifest contains malformed reviewed hash")
        if type(allowed_tools) is not frozenset or any(
            type(name) is not str for name in allowed_tools
        ):
            raise ValueError("unrecognized server-owned tool grant")
        if (
            type(manifest.tool_names) is not tuple
            or not manifest.tool_names
            or any(type(name) is not str for name in manifest.tool_names)
            or len(set(manifest.tool_names)) != len(manifest.tool_names)
        ):
            raise ValueError("manifest contains unexpected tool identities")
        if (
            type(manifest.resource_limits) is not SkillResourceLimits
            or set(vars(manifest.resource_limits))
            != set(SkillResourceLimits.__dataclass_fields__)
        ):
            raise ValueError("manifest resource limits must be immutable")
        if any(
            type(value) is not int or value <= 0
            for value in asdict(manifest.resource_limits).values()
        ):
            raise ValueError("manifest limits must be positive integers")
        # Never infer approved limits from a caller-owned or mutable nested
        # object, even if it can compare equal to the reviewed manifest.
        if (
            manifest.resource_limits.max_tool_calls != 1
            or manifest.resource_limits.max_wall_seconds != 481
            or manifest.resource_limits.max_output_bytes != 65536
        ):
            raise ValueError("manifest limits exceed fixed reviewed ceiling")
        expected = pilot_skill_manifest()
        # Recompute from live code only to catch runtime monkeypatching.
        # Never use that recomputation as the "reviewed" manifest.
        if _current_pilot_skill_manifest() != expected or manifest != expected:
            raise ValueError("manifest is not the code-reviewed version")
        if not set(manifest.tool_names).issubset(allowed_tools):
            raise ValueError("manifest exceeds caller's server-owned grant")
        for name in manifest.tool_names:
            spec = TOOLS.get(name)
            if (
                spec is None
                or spec.skill_id != manifest.name
                or spec.consequential
                or spec.approval_required
                or spec.kind != "task"
                or manifest.resource_limits.max_wall_seconds
                < math.ceil(
                    spec.timeout_seconds * spec.retry_policy.max_attempts
                    + spec.retry_policy.initial_backoff_seconds
                    * max(0, spec.retry_policy.max_attempts - 1)
                )
                or manifest.resource_limits.max_wall_seconds > 500
                or manifest.resource_limits.max_output_bytes > spec.max_result_bytes
            ):
                raise ValueError("pilot tool exceeds code-owned resource or authority")
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        raise CoworkerError(
            "skill_manifest_unreviewed",
            "This skill manifest is not a supported, reviewed, server-owned version.",
            409,
        ) from None
