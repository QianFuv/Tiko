"""Tests for Alembic database migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tiko.db.models import Base
from tiko.db.session import create_database_engine


def create_alembic_config(database_url: str) -> Config:
    """Create an Alembic config bound to a test database URL.

    Args:
        database_url: SQLAlchemy database URL.

    Returns:
        Alembic configuration.
    """

    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def create_sqlite_url(tmp_path: Path) -> str:
    """Build a SQLAlchemy URL for a temporary SQLite database.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        SQLite database URL.
    """

    database_path = tmp_path / "migrations.sqlite"
    return f"sqlite+pysqlite:///{database_path.as_posix()}"


def test_alembic_upgrade_head_creates_current_metadata_tables(tmp_path: Path) -> None:
    """Verify Alembic creates the ORM table set."""

    database_url = create_sqlite_url(tmp_path)

    command.upgrade(create_alembic_config(database_url), "head")
    engine = create_database_engine(database_url)
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert table_names == set(Base.metadata.tables) | {"alembic_version"}
