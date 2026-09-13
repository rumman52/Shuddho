"""Run once per release: python -m services.coworker.migrate."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    config.attributes["database_url"] = database_url
    return config


def upgrade(database_url: str):
    command.upgrade(migration_config(database_url), "head")


if __name__ == "__main__":
    url = os.getenv("SHUDDHO_COWORKER_DATABASE_URL", "")
    if not url:
        raise SystemExit("Set SHUDDHO_COWORKER_DATABASE_URL in the backend environment.")
    upgrade(url)
    print("Coworker database migrations applied.")
