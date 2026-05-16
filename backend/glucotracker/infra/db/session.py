"""Database engine and session helpers."""

from collections.abc import AsyncGenerator
from threading import Lock
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from glucotracker.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_sqlite_write_lock = Lock()


class GlucotrackerSession(Session):
    """Session with read-only guardrails and serialized SQLite writes."""

    _SQLITE_LOCK_INFO_KEY = "_glucotracker_sqlite_write_lock"
    _RAW_SQL_WRITE_PREFIXES = (
        "ALTER",
        "CREATE",
        "DELETE",
        "DROP",
        "INSERT",
        "REPLACE",
        "UPDATE",
        "VACUUM",
    )

    def _is_sqlite(self) -> bool:
        return self.get_bind().dialect.name == "sqlite"

    def _ensure_writable(self, operation: str) -> None:
        if self.info.get("read_only"):
            msg = f"Read-only database session cannot {operation}."
            raise RuntimeError(msg)

    def _has_pending_unit_of_work(self) -> bool:
        return bool(self.new or self.dirty or self.deleted)

    def _is_write_statement(self, statement: Any) -> bool:
        if getattr(statement, "is_dml", False) or getattr(statement, "is_ddl", False):
            return True

        raw_sql = getattr(statement, "text", None)
        if not isinstance(raw_sql, str):
            return False

        return raw_sql.lstrip().upper().startswith(self._RAW_SQL_WRITE_PREFIXES)

    def _acquire_sqlite_write_lock(self) -> None:
        if not self._is_sqlite() or self.info.get(self._SQLITE_LOCK_INFO_KEY):
            return
        _sqlite_write_lock.acquire()
        self.info[self._SQLITE_LOCK_INFO_KEY] = True

    def _release_sqlite_write_lock(self) -> None:
        if not self.info.pop(self._SQLITE_LOCK_INFO_KEY, False):
            return
        _sqlite_write_lock.release()

    def flush(self, objects: Any = None) -> None:
        """Flush pending ORM writes under the process-wide SQLite write lock."""
        self._ensure_writable("flush")
        had_lock = bool(self.info.get(self._SQLITE_LOCK_INFO_KEY))
        if objects is not None or self._has_pending_unit_of_work():
            self._acquire_sqlite_write_lock()
        try:
            super().flush(objects)
        except Exception:
            if not had_lock:
                self._release_sqlite_write_lock()
            raise

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute raw/Core SQL while guarding and serializing write statements."""
        write_statement = self._is_write_statement(statement)
        had_lock = bool(self.info.get(self._SQLITE_LOCK_INFO_KEY))
        if write_statement:
            self._ensure_writable("execute write statements")
            self._acquire_sqlite_write_lock()
        try:
            return super().execute(statement, *args, **kwargs)
        except Exception:
            if write_statement and not had_lock:
                self._release_sqlite_write_lock()
            raise

    def commit(self) -> None:
        """Commit writes under the process-wide SQLite write lock."""
        self._ensure_writable("commit")
        try:
            super().commit()
        finally:
            self._release_sqlite_write_lock()

    def rollback(self) -> None:
        """Rollback the transaction and release any held SQLite write lock."""
        try:
            super().rollback()
        finally:
            self._release_sqlite_write_lock()

    def close(self) -> None:
        """Close the session and release any held SQLite write lock."""
        try:
            super().close()
        finally:
            self._release_sqlite_write_lock()


def _sqlite_connect_args(database_url: str) -> dict[str, object]:
    """Return SQLite-specific connect args when the active URL is SQLite."""
    if database_url.startswith("sqlite"):
        return {
            "check_same_thread": False,
            "timeout": 30,
        }
    return {}


def _engine_kwargs(database_url: str) -> dict[str, object]:
    """Return engine options for the configured database backend."""
    if database_url.startswith("sqlite"):
        return {"poolclass": NullPool}
    if database_url.startswith("postgresql"):
        return {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
        }
    return {}


def _connect_args(database_url: str) -> dict[str, object]:
    """Return backend-specific SQLAlchemy connection args."""
    if database_url.startswith("postgresql"):
        return {"options": "-c timezone=utc"}
    return _sqlite_connect_args(database_url)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Enable SQLite foreign-key cascades for every connection."""
    if engine.url.get_backend_name() != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_engine() -> Engine:
    """Return the configured SQLAlchemy engine."""
    global _engine
    if _engine is None:
        database_url = get_settings().database_url
        _engine = create_engine(
            database_url,
            connect_args=_connect_args(database_url),
            future=True,
            **_engine_kwargs(database_url),
        )
        _enable_sqlite_foreign_keys(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the configured session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=GlucotrackerSession,
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
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_read_session() -> AsyncGenerator[Session, None]:
    """Yield a read-only database session for GET endpoints."""
    session = get_session_factory()()
    session.info["read_only"] = True
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.rollback()
        session.close()


def reset_engine_for_tests() -> None:
    """Dispose cached engine/session state for tests."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
