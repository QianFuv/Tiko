"""SQLAlchemy engine and session helpers."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from tiko.db.models import Base


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL.

    Args:
        database_url: SQLAlchemy database URL.

    Returns:
        Configured SQLAlchemy engine.
    """

    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to an engine.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Session factory configured for explicit commits.
    """

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_all_tables(engine: Engine) -> None:
    """Create all ORM tables for the current metadata.

    Args:
        engine: SQLAlchemy engine.
    """

    Base.metadata.create_all(engine)
