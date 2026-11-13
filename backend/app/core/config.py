"""Runtime settings with safe, local-first defaults."""

from pathlib import Path
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_url() -> str:
    """Choose a per-user database path that is portable across Windows/Linux."""
    aatm_home = Path(os.environ.get("AATM_HOME", Path.home() / ".aatm")).expanduser()
    return f"sqlite:///{(aatm_home / 'aatm.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AATM — AI Agent Team Manager"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = default_database_url()
    host: str = "127.0.0.1"
    port: int = 8000
    adaptive_concurrency: str = Field(default="0", validation_alias="AATM_ADAPTIVE_CONCURRENCY")
    max_concurrency: str = Field(default="1", validation_alias="AATM_MAX_CONCURRENCY")
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    allowed_hosts: list[str] = [
        "localhost",
        "127.0.0.1",
        "[::1]",
        "testserver",
    ]


settings = Settings()
