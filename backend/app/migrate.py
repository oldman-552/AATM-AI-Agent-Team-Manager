"""Run versioned database migrations on the app's configured SQLAlchemy engine."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def upgrade_database(engine: Engine, database_url: str) -> None:
    """Apply Alembic migrations using the same engine as the application.

    Sharing the connection also makes in-memory SQLite migrations behave like
    file-backed databases in tests.
    """
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
