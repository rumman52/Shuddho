"""Guard against divergent Alembic heads in the Coworker schema."""
from __future__ import annotations

from alembic.script import ScriptDirectory

from services.coworker.migrate import migration_config


def test_coworker_migrations_have_a_single_head_with_both_0071_parents():
    script = ScriptDirectory.from_config(migration_config("sqlite://"))
    assert script.get_heads() == ["0072_merge_0071_heads"]
    assert script.get_current_head() == "0072_merge_0071_heads"
    merge = script.get_revision("0072_merge_0071_heads")
    assert set(merge.down_revision) == {"0071", "0071_project_scoped_goals"}
