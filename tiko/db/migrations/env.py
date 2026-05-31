"""Alembic environment for Tiko database migrations."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from tiko.core.config import get_settings
from tiko.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def resolve_database_url() -> str:
    """Resolve the migration database URL.

    Returns:
        SQLAlchemy database URL for the current migration command.
    """

    attribute_url = config.attributes.get("database_url")
    if isinstance(attribute_url, str) and attribute_url:
        return attribute_url
    cli_url = context.get_x_argument(as_dictionary=True).get("database_url")
    if cli_url:
        return cli_url
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    fallback_url = config.get_main_option("sqlalchemy.url")
    if not fallback_url:
        raise ValueError("Alembic sqlalchemy.url is not configured.")
    return fallback_url


def run_migrations_offline() -> None:
    """Run migrations without an active DBAPI connection."""

    context.configure(
        url=resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with an active DBAPI connection."""

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = resolve_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
