from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def session_factory(url: str):
    options = {"pool_pre_ping": True, "hide_parameters": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
    else:
        options.update(pool_size=5, max_overflow=5, pool_timeout=10, connect_args={
            "connect_timeout": 5, "options": "-c search_path=shuddho_coworker -c statement_timeout=15000 -c lock_timeout=5000",
        })
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return sessionmaker(engine, expire_on_commit=False)
