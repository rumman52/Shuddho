from alembic import context
from sqlalchemy import text

from services.coworker.database import session_factory
from services.coworker.models import Base

config = context.config
engine = session_factory(config.attributes["database_url"]).kw["bind"]

with engine.connect() as connection:
    if connection.dialect.name == "postgresql":
        # Keep account tables outside Supabase's default public Data API schema.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS shuddho_coworker"))
        connection.execute(text("REVOKE ALL ON SCHEMA shuddho_coworker FROM PUBLIC"))
        connection.commit()
    context.configure(
        connection=connection, target_metadata=Base.metadata,
        version_table="cw_alembic_version", compare_type=True,
        include_object=lambda obj, name, type_, reflected, compare_to: type_ != "table" or name.startswith("cw_"),
    )
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
