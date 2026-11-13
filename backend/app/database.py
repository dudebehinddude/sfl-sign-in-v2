from collections.abc import Generator

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

engine = create_engine(
    get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=10
)


@event.listens_for(engine, "connect")
def configure_connection(connection, _record):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('TimeZone', %s, false)", (get_settings().lab_timezone,))
    connection.commit()


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session


def init_db() -> None:
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    from .models import ScopeRevision

    with Session(engine) as session:
        for scope in ["public", "staff"]:
            if session.get(ScopeRevision, scope) is None:
                session.add(ScopeRevision(scope=scope))
        # Apply DB-side updated_at for all mutable entities, including SQL workbench edits.
        session.execute(
            text("""CREATE OR REPLACE FUNCTION sfl_touch_updated_at() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = clock_timestamp(); RETURN NEW; END $$""")
        )
        for table in SQLModel.metadata.sorted_tables:
            if "updated_at" in table.c:
                quoted = engine.dialect.identifier_preparer.quote(table.name)
                session.execute(text(f"DROP TRIGGER IF EXISTS touch_updated_at ON {quoted}"))
                session.execute(
                    text(
                        f"CREATE TRIGGER touch_updated_at BEFORE UPDATE ON {quoted} FOR EACH ROW EXECUTE FUNCTION sfl_touch_updated_at()"
                    )
                )
        session.commit()


def lab_lock(session: Session) -> None:
    # All kiosk/visit/keyholder mutations use the same transaction-level lab lock.
    # Network work is never performed while it is held.
    session.execute(text("SELECT pg_advisory_xact_lock(73190517)"))
