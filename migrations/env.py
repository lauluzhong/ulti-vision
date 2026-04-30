"""Alembic environment — targets sva.db.Base.metadata and reads DATABASE_URL from settings."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sva.config import settings
from sva.db import Base

config = context.config

# Override the ini-file sqlalchemy.url with the live settings value.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _ensure_alembic_version_table_supports_long_ids(connection) -> None:
    """Pre-create alembic_version with a wider column.

    Our revision IDs (e.g. '0002_phase2_sources_and_rights_acks') exceed
    Alembic's default version_num varchar(32). Pre-creating the table with
    varchar(255) sidesteps the limit. CREATE IF NOT EXISTS makes this a no-op
    on subsequent runs.
    """
    from sqlalchemy import text as sa_text

    connection.execute(
        sa_text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num varchar(255) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
            ")"
        )
    )


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _ensure_alembic_version_table_supports_long_ids(connection)
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
