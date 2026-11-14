"""Apply migrations as the schema owner or check them as a runtime user."""
import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from services.coworker.config import _normalize_database_url
from services.coworker.database import session_factory


class DatabaseReadinessError(RuntimeError):
    pass


def migration_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    config.attributes["database_url"] = database_url
    return config


def upgrade(database_url: str):
    command.upgrade(migration_config(database_url), "head")


def check(database_url: str) -> None:
    expected = set(ScriptDirectory.from_config(migration_config(database_url)).get_heads())
    engine = session_factory(database_url).kw["bind"]
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                if connection.scalar(text("SELECT current_schema()")) != "shuddho_coworker":
                    raise DatabaseReadinessError("The private Coworker schema is unavailable.")
            context = MigrationContext.configure(
                connection, opts={"version_table": "cw_alembic_version"},
            )
            if set(context.get_current_heads()) != expected:
                raise DatabaseReadinessError("Coworker database is not at the required migration revision.")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify the migration head without writing.")
    args = parser.parse_args()
    url = _normalize_database_url(
        os.getenv("SHUDDHO_COWORKER_DATABASE_URL", ""),
        os.getenv("SHUDDHO_COWORKER_ENV", "production"),
    )
    if not url:
        raise SystemExit("Set SHUDDHO_COWORKER_DATABASE_URL in the backend environment.")
    if args.check:
        try:
            check(url)
        except DatabaseReadinessError as error:
            raise SystemExit(str(error)) from None
        except Exception as error:
            raise SystemExit(f"Coworker database readiness failed ({type(error).__name__}).") from None
        print("Coworker database migration revision verified.")
    else:
        upgrade(url)
        print("Coworker database migrations applied.")


if __name__ == "__main__":
    main()
