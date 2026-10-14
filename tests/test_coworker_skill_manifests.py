"""CW-11 reviewed pilot manifest contract; no skill installs or provider calls."""
from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import BaseModel

from services.coworker.agent_tools import TOOLS
from services.coworker.errors import CoworkerError
from services.coworker.skill_manifests import (
    CoworkerSkillManifest,
    SkillResourceLimits,
    pilot_skill_manifest,
    validate_manifest,
)
from services.coworker.skills import SKILLS, skill_for_version


GRANT = frozenset({"research.search"})


def denied(proposal, allowed_tools=GRANT):
    with pytest.raises(CoworkerError) as failure:
        validate_manifest(proposal, allowed_tools)
    assert failure.value.code == "skill_manifest_unreviewed"


def test_reviewed_research_manifest_is_versioned_inert_and_uses_code_owned_tool():
    manifest = pilot_skill_manifest()
    assert manifest.name == "research"
    assert manifest.version == skill_for_version("work_research_v1").version
    assert manifest.tool_names == ("research.search",)
    assert manifest.resource_limits.max_tool_calls == 1
    assert manifest.resource_limits.max_wall_seconds == 481  # 2 x 240s + backoff
    assert manifest.rollback_version == manifest.version
    assert len(manifest.review_sha256()) == 64
    validate_manifest(manifest, GRANT)
    # A read-only validator never enables a disabled runtime tool.
    assert TOOLS["research.search"].skill_id == manifest.name


def test_unreviewed_tools_and_permission_expansion_fail_before_any_grant():
    manifest = pilot_skill_manifest()
    denied(manifest, frozenset())
    denied(replace(manifest, tool_names=("email.send",)), frozenset({"email.send"}))
    denied(replace(manifest, tool_names=("research.search", "browser.read")),
           frozenset({"research.search", "browser.read"}))
    denied(replace(manifest, tool_names=("unknown.provider",)),
           frozenset({"unknown.provider"}))
    denied(replace(manifest, tool_names=("research.search", "research.search")))
    denied(manifest, {"research.search"})


@pytest.mark.parametrize("change", [
    {"version": "work_research_v2"},
    {"name": "email"},
    {"instruction_sha256": "f" * 64},
    {"input_schema_sha256": "f" * 64},
    {"output_schema_sha256": "f" * 64},
    {"tool_contract_sha256": "f" * 64},
    {"rollback_version": "obsolete"},
])
def test_changed_version_or_instruction_or_schema_hash_invalidates_review(change):
    approved = pilot_skill_manifest()
    assert approved.review_sha256() != replace(approved, **change).review_sha256()
    denied(replace(approved, **change))


def test_live_instruction_change_revokes_existing_review(monkeypatch):
    manifest = pilot_skill_manifest()
    monkeypatch.setitem(
        SKILLS, "research",
        replace(SKILLS["research"], guidance=SKILLS["research"].guidance + " changed"),
    )
    denied(manifest)


def test_live_tool_schema_change_revokes_existing_review(monkeypatch):
    class ChangedInput(BaseModel):
        different_field: str

    manifest = pilot_skill_manifest()
    monkeypatch.setitem(
        TOOLS, "research.search",
        replace(TOOLS["research.search"], input_model=ChangedInput),
    )
    denied(manifest)


@pytest.mark.parametrize("limits", [
    SkillResourceLimits(max_tool_calls=2, max_wall_seconds=240, max_output_bytes=65536),
    SkillResourceLimits(max_tool_calls=1, max_wall_seconds=241, max_output_bytes=65536),
    SkillResourceLimits(max_tool_calls=1, max_wall_seconds=480, max_output_bytes=65536),
    SkillResourceLimits(max_tool_calls=1, max_wall_seconds=501, max_output_bytes=65536),
    SkillResourceLimits(max_tool_calls=1, max_wall_seconds=240, max_output_bytes=65537),
    SkillResourceLimits(max_tool_calls=True, max_wall_seconds=240, max_output_bytes=65536),
])
def test_changed_or_coerced_resource_limits_require_fresh_code_review(limits):
    denied(replace(pilot_skill_manifest(), resource_limits=limits))


def test_subclass_and_changed_nested_runtime_type_cannot_be_reviewed():
    class UnreviewedManifest(CoworkerSkillManifest):
        pass

    expected = pilot_skill_manifest()
    disguised = UnreviewedManifest(**vars(expected))
    denied(disguised)
    denied(replace(expected, resource_limits=vars(expected.resource_limits)))


def test_exact_legacy_skill_version_remains_available_without_dynamic_installation():
    manifest = pilot_skill_manifest()
    assert skill_for_version(manifest.rollback_version).id == manifest.name
    denied(replace(manifest, version="work_research_v99"))


def test_existing_review_does_not_inherit_new_tool_permissions(monkeypatch):
    manifest = pilot_skill_manifest()
    spec = TOOLS["research.search"]
    monkeypatch.setitem(
        TOOLS, "research.search",
        replace(spec, permissions=spec.permissions + ("connected_email:write",)),
    )
    # Even though the caller still passes the same tool name, the reviewed
    # contract fingerprint now differs from the code-owned registry.
    denied(manifest)


class AlwaysEqualString(str):
    def __eq__(self, _other):
        return True


@pytest.mark.parametrize("field", [
    "instruction_sha256", "input_schema_sha256", "output_schema_sha256",
    "tool_contract_sha256", "rollback_version", "version", "name",
])
def test_identity_subclasses_cannot_override_reviewed_equality(field):
    approved = pilot_skill_manifest()
    suspect = replace(approved, **{
        field: AlwaysEqualString(str(getattr(approved, field))),
    })
    denied(suspect)


def test_unreviewed_copied_extra_state_cannot_be_hidden():
    manifest = pilot_skill_manifest()
    object.__setattr__(manifest, "secret_provider_override", "connected_email")
    try:
        denied(manifest)
    finally:
        object.__delattr__(manifest, "secret_provider_override")


def test_pinned_source_digest_cannot_be_regenerated_on_code_change(monkeypatch):
    from services.coworker import skill_manifests as reviewed

    approved = pilot_skill_manifest()
    changed = (
        (reviewed.WorkSkill, "0" * 40),
        *reviewed._REVIEWED_SOURCE_BLOBS[1:],
    )
    monkeypatch.setattr(reviewed, "_REVIEWED_SOURCE_BLOBS", changed)
    denied(approved)


def test_retry_duration_cannot_be_underreported_as_one_attempt():
    approved = pilot_skill_manifest()
    assert TOOLS["research.search"].retry_policy.max_attempts == 2
    assert TOOLS["research.search"].timeout_seconds == 240
    shortened = replace(approved, resource_limits=replace(
        approved.resource_limits, max_wall_seconds=240,
    ))
    denied(shortened)
