from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def session_factory(url: str):
    options = {"pool_pre_ping": True, "hide_parameters": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
    else:
        options.update(pool_size=5, max_overflow=5, pool_timeout=10, connect_args={
            "connect_timeout": 5,
        })
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    else:
        @event.listens_for(engine, "connect")
        def postgres_session(connection, _):
            # Some managed poolers drop startup options. Apply persistent
            # settings before the first transaction and dialect inspection.
            autocommit = connection.autocommit
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET SESSION search_path TO shuddho_coworker")
                    cursor.execute("SET SESSION statement_timeout TO '15s'")
                    cursor.execute("SET SESSION lock_timeout TO '5s'")
            finally:
                connection.autocommit = autocommit
    return sessionmaker(engine, expire_on_commit=False)
