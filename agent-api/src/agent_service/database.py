"""Async SQLAlchemy database setup."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def _migrate_add_column(conn, table: str, column: str, col_type: str) -> None:
    """Add a column to an existing table if it doesn't exist (SQLite compatible)."""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    if column not in columns:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        logger.info("Migration: added column %s.%s", table, column)


async def init_db(database_url: str) -> None:
    """Create engine, session factory, and all tables."""
    global engine, async_session_factory

    engine = create_async_engine(database_url, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        from agent_service.models import Conversation, Message, TokenUsage  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)

        # Migrations for existing databases
        await _migrate_add_column(conn, "conversations", "preset", "TEXT")
        await _migrate_add_column(conn, "conversations", "enable_teams", "BOOLEAN DEFAULT 0")
        await _migrate_add_column(conn, "conversations", "enable_tracing", "BOOLEAN DEFAULT 0")
        await _migrate_add_column(conn, "conversations", "enable_approval", "BOOLEAN DEFAULT 0")
        await _migrate_add_column(conn, "conversations", "enable_plan_mode", "BOOLEAN DEFAULT 0")
        await _migrate_add_column(conn, "conversations", "enable_thinking", "BOOLEAN DEFAULT 0")
        await _migrate_add_column(conn, "conversations", "thinking_effort", "TEXT DEFAULT 'high'")


async def get_session() -> AsyncSession:
    if async_session_factory is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    async with async_session_factory() as session:
        yield session


async def close_db() -> None:
    global engine
    if engine:
        await engine.dispose()
        engine = None
