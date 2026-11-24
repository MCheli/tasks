"""The c3d4e5f6a7b8 migration: existing rows become owner='human', counts don't change.

Runs Alembic for real against the test database: empty it, upgrade to the previous head,
insert a user with tasks in both lists the way the old schema stored them, upgrade to head,
check. The metadata schema is recreated afterwards for the other tests.
"""

from __future__ import annotations

import os

import anyio
import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.db.base import Base

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _alembic() -> Config:
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    return cfg


async def _run(fn):
    # env.py calls asyncio.run(); give it a thread of its own, outside pytest's loop.
    await anyio.to_thread.run_sync(fn)


@pytest.mark.usefixtures("engine")
async def test_migration_marks_existing_tasks_human_and_keeps_counts(engine):
    cfg = _alembic()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    await _run(lambda: command.upgrade(cfg, "a1b2c3d4e5f6"))

    async with engine.begin() as conn:
        cols = {
            r[0]
            for r in await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='tasks'")
            )
        }
        assert "owner" not in cols
        await conn.execute(
            text(
                "INSERT INTO users (id, email, created_at, updated_at) VALUES "
                "('11111111-1111-1111-1111-111111111111', 'old@example.com', now(), now())"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO cycles (id, user_id, category, started_at, created_at) VALUES "
                "('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'personal', now(), now()), "
                "('33333333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'professional', now(), now())"
            )
        )
        for i, (cycle, status) in enumerate(
            [
                ("22222222-2222-2222-2222-222222222222", "open"),
                ("22222222-2222-2222-2222-222222222222", "completed"),
                ("33333333-3333-3333-3333-333333333333", "open"),
            ]
        ):
            await conn.execute(
                text(
                    "INSERT INTO tasks (id, persistent_task_id, display_id, user_id, cycle_id, title, "
                    "status, position, created_at, updated_at) VALUES (gen_random_uuid(), "
                    f"gen_random_uuid(), {i + 1}, '11111111-1111-1111-1111-111111111111', '{cycle}', "
                    f"'t{i}', '{status}', {i}, now(), now())"
                )
            )
        before = (
            await conn.execute(
                text(
                    "SELECT c.category, count(*) FROM tasks t JOIN cycles c ON c.id=t.cycle_id "
                    "GROUP BY c.category ORDER BY c.category"
                )
            )
        ).all()
    assert [(c, int(n)) for c, n in before] == [("personal", 2), ("professional", 1)]

    await _run(lambda: command.upgrade(cfg, "head"))

    async with engine.begin() as conn:
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        assert version == "c3d4e5f6a7b8"
        after = (
            await conn.execute(
                text(
                    "SELECT c.category, count(*) FROM tasks t JOIN cycles c ON c.id=t.cycle_id "
                    "GROUP BY c.category ORDER BY c.category"
                )
            )
        ).all()
        assert [(c, int(n)) for c, n in after] == [("personal", 2), ("professional", 1)]
        owners = (await conn.execute(text("SELECT DISTINCT owner FROM tasks"))).scalars().all()
        assert owners == ["human"]
        nulls = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM tasks WHERE source IS NOT NULL OR agent_status IS NOT NULL"
                )
            )
        ).scalar()
        assert nulls == 0
        tables = {
            r[0]
            for r in await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert {"task_notes", "mcp_oauth_clients", "mcp_oauth_codes", "mcp_oauth_tokens"} <= tables
        # The ORM mapping matches the migrated schema.
        await conn.execute(
            text(
                "INSERT INTO tasks (id, persistent_task_id, display_id, user_id, cycle_id, title, status, position, owner, source, agent_status) VALUES (gen_random_uuid(), gen_random_uuid(), 9, '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'a', 'open', 9, 'agent', 'sweep', 'blocked')"
            )
        )
        bad = text(
            "INSERT INTO tasks (id, persistent_task_id, display_id, user_id, cycle_id, title, status, position, owner) VALUES (gen_random_uuid(), gen_random_uuid(), 10, '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'a', 'open', 10, 'robot')"
        )
        with pytest.raises(Exception, match="ck_tasks_owner"):
            await conn.execute(bad)

    # Downgrade is clean too, then restore the metadata schema for the rest of the suite.
    await _run(lambda: command.downgrade(cfg, "a1b2c3d4e5f6"))
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
