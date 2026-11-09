"""The Coworker Alembic graph must resolve to one linear head."""
from alembic.script import ScriptDirectory

from services.coworker.migrate import migration_config


def test_coworker_migration_graph_has_one_resolvable_head():
    script = ScriptDirectory.from_config(migration_config("sqlite://"))

    assert script.get_heads() == ["0068_fly_repository_coding"]
    assert script.get_revision("0068_fly_repository_coding").down_revision == "0067"
    assert script.get_revision("0067").down_revision == "0066"
