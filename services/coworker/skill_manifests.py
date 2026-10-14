"""CW-11: inert, code-reviewed skill manifest identities (no dynamic tool grants).

This module only validates reviewed references to existing WorkSkill and
ToolSpec contracts. It never installs a skill, registers a tool, persists a
grant, selects a provider, or changes runtime dispatch.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .agent_tools import TOOLS, ToolSpec
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
_PILOT_LIMITS = SkillResourceLimits(
    max_tool_calls=1, max_wall_seconds=240, max_output_bytes=65536,
)


def pilot_skill_manifest() -> CoworkerSkillManifest:
    skill = SKILLS[_PILOT_NAME]
    spec = TOOLS[_PILOT_TOOLS[0]]
    return CoworkerSkillManifest(
        name=skill.id,
        version=skill.version,
        instruction_sha256=_reviewed_instruction_identity(skill),
        input_schema_sha256=_schema_identity(spec, output=False),
        output_schema_sha256=_schema_identity(spec, output=True),
        tool_names=_PILOT_TOOLS,
        resource_limits=_PILOT_LIMITS,
        rollback_version=skill.version,
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
        if type(manifest.resource_limits) is not SkillResourceLimits:
            raise ValueError("manifest resource limits must be immutable")
        if any(
            type(value) is not int or value <= 0
            for value in asdict(manifest.resource_limits).values()
        ):
            raise ValueError("manifest limits must be positive integers")
        expected = pilot_skill_manifest()
        if type(manifest.name) is not str or type(manifest.version) is not str:
            raise ValueError("manifest name/version must be plain strings")
        if manifest != expected:
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
                or manifest.resource_limits.max_wall_seconds > spec.timeout_seconds
                or manifest.resource_limits.max_output_bytes > spec.max_result_bytes
            ):
                raise ValueError("pilot tool exceeds code-owned resource or authority")
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CoworkerError(
            "skill_manifest_unreviewed",
            "This skill manifest is not a supported, reviewed, server-owned version.",
            409,
        ) from None
