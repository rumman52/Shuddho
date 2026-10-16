"""Task workflow selection with an explicit old-worker fail-closed version fence.

The reviewed research manifest is still pinned to the existing WorkSkill and
ToolSpec versions. Its *task workflow* identity is separate so older workers
that understand only work_research_v1 reject it rather than running it with
legacy authorization when the reviewed admission flag is disabled.
"""
from __future__ import annotations

from .skills import SKILLS, WorkSkill, skill_for_version

REVIEWED_RESEARCH_WORKFLOW_VERSION = "work_research_reviewed_v1"


def task_skill_for_version(version: str) -> WorkSkill:
    if version == REVIEWED_RESEARCH_WORKFLOW_VERSION:
        return SKILLS["research"]
    return skill_for_version(version)
