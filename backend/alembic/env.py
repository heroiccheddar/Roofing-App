"""Alembic environment configuration for async migrations."""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

# SQLAlchemy Cython extensions deadlock on Python 3.14 Windows (import lock bug)
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

# psycopg requires SelectorEventLoop on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load .env from backend directory
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Import Base and all models for autogenerate support
from app.database import Base
from app.models import (
    StormEvent,
    CensusTract,
    LeadZone,
    CanvassSession,
    ModelCalibration,
    RooferAccount,
    AlertLog,
    ZoneFeedback,
)

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set SQLAlchemy URL from environment variable
# Ensure the psycopg driver is specified for Neon connections
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Normalize to psycopg driver if plain postgresql:// is provided
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    # psycopg uses libpq-style 'sslmode' — convert 'ssl' if present
    database_url = database_url.replace("ssl=require", "sslmode=require")
    config.set_main_option("sqlalchemy.url", database_url)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with established connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
