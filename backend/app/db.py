"""SQLAlchemy engine and session helpers."""

from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base for persistent application models."""


def build_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    engine_options: dict[str, object] = {"pool_pre_ping": True}

    if database_url.startswith("sqlite:"):
        connect_args["check_same_thread"] = False
        # Wait rather than failing at once when another connection is writing.
        # The executor polls for cancellation while the orchestrator holds a
        # read transaction, and an operator's cancel write must eventually land.
        connect_args["timeout"] = 15
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            engine_options["poolclass"] = StaticPool
        elif database_url.startswith("sqlite:///"):
            # Resolve and create the parent directory for file-backed databases.
            raw_path = database_url.removeprefix("sqlite:///")
            db_path = Path(raw_path).expanduser()
            if not db_path.is_absolute():
                db_path = Path.cwd() / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_path.as_posix()}"

    engine = create_engine(database_url, connect_args=connect_args, **engine_options)
    if database_url.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # Write-ahead logging lets a reader and a writer proceed at the same
            # time. Without it, SQLite's rollback journal blocks the cancel
            # request for as long as the orchestrator's read transaction is open,
            # which made "cancel a running task" fail with "database is locked".
            # WAL is persistent per database file, harmless to re-apply, and the
            # in-memory database ignores it.
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
            except Exception:
                # Older/embedded builds without WAL still work; they just keep
                # the previous locking behaviour.
                pass
            cursor.close()
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield one request-scoped DB session and always close it."""
    db = factory()
    try:
        yield db
    finally:
        db.close()


def safe_close(db: Session) -> None:
    """Close a session, rolling back first so a failed transaction cannot linger.

    Without the rollback, a session that hit a database error keeps its broken
    transaction and connection state. The next request that reuses a pooled
    connection can then fail for reasons unrelated to its own work. Rolling back
    before closing guarantees each request starts from a clean state.
    """
    try:
        if db.in_transaction():
            db.rollback()
    except Exception:  # pragma: no cover - a broken connection is already unusable
        pass
    finally:
        db.close()
