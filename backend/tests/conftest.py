"""Shared pytest fixtures for unit and API tests.

We use one session-scoped event loop and one session-scoped engine so the
asyncpg connection objects stay attached to a single loop. Per-test
isolation is provided by wrapping each test in a connection-level
transaction that rolls back at teardown (the SAVEPOINT pattern).
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_URL = os.environ.get(
    "TASKS_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/cycle_todo_test",
)

# Ensure app.config.Settings sees the test DB before any module imports it.
os.environ.setdefault("TASKS_DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("TASKS_JWT_SECRET", "test-secret-key-do-not-use-in-prod")

from app.db.base import Base  # noqa: E402

# Import all model modules so Base.metadata is populated.
from app.models import cycle, task, user  # noqa: E402,F401


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    """Session-scoped async engine. NullPool avoids cross-loop connection reuse."""
    eng = create_async_engine(
        TEST_DB_URL,
        echo=False,
        poolclass=NullPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(engine) -> AsyncIterator[AsyncSession]:
    """Per-test session bound to a transaction that rolls back at teardown."""
    connection = await engine.connect()
    transaction = await connection.begin()
    Session = async_sessionmaker(
        bind=connection, expire_on_commit=False, class_=AsyncSession
    )
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture(loop_scope="session")
async def test_user(db):
    from app.core.security import hash_password
    from app.models.user import User

    u = User(email="alice@example.com", hashed_password=hash_password("secret"))
    db.add(u)
    await db.flush()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db):
    from app.core.security import hash_password
    from app.models.user import User

    u = User(email="bob@example.com", hashed_password=hash_password("secret"))
    db.add(u)
    await db.flush()
    await db.refresh(u)
    return u
