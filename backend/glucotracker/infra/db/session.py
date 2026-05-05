"""Database engine and session helpers."""

from collections.abc import AsyncGenerator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from glucotracker.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _sqlite_connect_args(database_url: str) -> dict[str, bool]:
    """Return SQLite-specific connect args when the active URL is SQLite."""
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Enable SQLite foreign-key cascades for every connection."""
    if engine.url.get_backend_name() != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> Engine:
    """Return the configured SQLAlchemy engine."""
    global _engine
    if _engine is None:
        database_url = get_settings().database_url
        _engine = create_engine(
            database_url,
            connect_args=_sqlite_connect_args(database_url),
            future=True,
        )
        _enable_sqlite_foreign_keys(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the configured session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[Session, None]:
    """Yield a database session for FastAPI dependencies."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Dispose cached engine/session state for tests."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
