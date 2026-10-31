"""The public demo is read-only, signs visitors in as the persona, and refuses real data."""

from __future__ import annotations

import re

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.demo import (
    ALLOWED_WRITES,
    check_demo_database,
    check_demo_settings,
    make_read_only,
    write_allowed,
)
from app.main import app
from app.models.cycle import Cycle
from app.models.user import User

PERSONA = "claudius@tasks.dev"


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", PERSONA)
    for name in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "TEST_USER_EMAIL",
        "TEST_USER_PASSWORD",
    ):
        monkeypatch.setattr(settings, name, None)


@pytest_asyncio.fixture(loop_scope="session")
async def claudius(db):
    """The demo persona, as the seed creates him."""
    user = User(email=PERSONA, display_name="Claudius Banks")
    db.add(user)
    await db.flush()
    for category in ("personal", "professional"):
        db.add(Cycle(user_id=user.id, category=category))
    await db.flush()
    return user


def _api_routes(routes, prefix=""):
    """(full path, route). Newer FastAPI wraps included routers and keeps the prefix aside."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield prefix + r.path, r
        elif hasattr(r, "original_router"):
            ctx = getattr(r, "include_context", None)
            yield from _api_routes(r.original_router.routes, prefix + getattr(ctx, "prefix", ""))


def _write_routes():
    for path, r in _api_routes(app.routes):
        for m in r.methods - {"GET", "HEAD", "OPTIONS"}:
            yield m, re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", path)


def test_only_signing_in_and_out_may_write():
    assert write_allowed("GET", "/api/cycles/current")
    assert write_allowed("POST", "/api/auth/demo")
    assert write_allowed("POST", "/api/auth/logout")
    assert not write_allowed("POST", "/api/auth/login")
    assert not write_allowed("POST", "/api/api-keys")
    assert not write_allowed("POST", "/api/tasks")
    assert not write_allowed("PATCH", "/api/tasks/x")
    assert not write_allowed("POST", "/api/auth/demo/extra")


async def test_every_write_route_is_refused_in_demo_mode(client, demo):
    routes = sorted(set(_write_routes()))
    allowed = [(m, p) for m, p in routes if any(a.match(p) for a in ALLOWED_WRITES)]
    assert allowed == [("POST", "/api/auth/demo"), ("POST", "/api/auth/logout")]
    refused = [(m, p) for m, p in routes if (m, p) not in allowed]
    # login, api keys (create, revoke), tasks (create, update, delete, reorder), transition
    assert len(refused) >= 8, refused
    for method, path in refused:
        res = await client.request(method, path, json={})
        assert res.status_code == 403, (method, path, res.status_code)
        assert res.json()["demo"] is True, (method, path)


async def test_reads_work_and_pages_are_not_indexed(client, db, demo, claudius):
    assert (await client.post("/api/auth/demo")).status_code == 200
    res = await client.get("/api/cycles/current", params={"category": "personal"})
    assert res.status_code == 200
    assert res.headers["X-Robots-Tag"] == "noindex, nofollow"
    cfg = (await client.get("/api/auth/config")).json()
    assert cfg["demo_mode"] is True and cfg["google_configured"] is False


async def test_demo_never_creates_a_cycle_from_a_get(client, db, demo):
    user = User(email=PERSONA, display_name="Claudius Banks")  # no cycles: mid-rebuild
    db.add(user)
    await db.flush()
    assert (await client.post("/api/auth/demo")).status_code == 200
    res = await client.get("/api/cycles/current", params={"category": "personal"})
    assert res.status_code == 503
    assert await db.scalar(select(Cycle).where(Cycle.user_id == user.id)) is None


async def test_outside_demo_mode_nothing_changes(authed_client):
    res = await authed_client.post("/api/tasks", json={"category": "personal", "title": "x"})
    assert res.status_code == 201
    assert "X-Robots-Tag" not in res.headers
    assert (await authed_client.post("/api/auth/demo")).status_code == 404
    cfg = (await authed_client.get("/api/auth/config")).json()
    assert cfg["demo_mode"] is False and cfg["demo_url"] is None


async def test_the_real_deployment_links_to_the_demo(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_URL", "https://tasks-demo.example.com")
    cfg = (await client.get("/api/auth/config")).json()
    assert cfg["demo_url"] == "https://tasks-demo.example.com"


async def test_demo_sign_in_issues_a_session_for_the_persona(client, db, demo):
    res = await client.post("/api/auth/demo")
    assert res.status_code == 503  # no persona yet: the nightly rebuild is running
    db.add(User(email=PERSONA, display_name="Claudius Banks"))
    await db.flush()
    res = await client.post("/api/auth/demo")
    assert res.status_code == 200, res.text
    assert res.json()["user"]["display_name"] == "Claudius Banks"
    assert "session" in res.cookies
    me = await client.get("/api/auth/me")
    assert me.json()["email"] == PERSONA


async def test_demo_refuses_api_keys_and_password_login(client, db, demo, claudius):
    assert (await client.post("/api/auth/demo")).status_code == 200
    assert (await client.post("/api/api-keys", json={"name": "x"})).status_code == 403
    assert (await client.get("/api/api-keys")).status_code == 200
    res = await client.post("/api/auth/login", json={"email": PERSONA, "password": "x"})
    assert res.status_code == 403


async def test_demo_refuses_a_database_with_real_users(db):
    db.add(User(email=PERSONA, display_name="Claudius Banks"))
    await db.flush()
    await check_demo_database(db)  # personas only: fine
    db.add(User(email="someone@example.com"))
    await db.flush()
    with pytest.raises(RuntimeError, match="real users"):
        await check_demo_database(db)


def test_demo_refuses_sso_and_password_secrets(demo, monkeypatch):
    check_demo_settings()
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "GOCSPX-x")
    with pytest.raises(RuntimeError, match="Google"):
        check_demo_settings()
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "TEST_USER_PASSWORD", "hunter2")
    with pytest.raises(RuntimeError, match="password user"):
        check_demo_settings()
    monkeypatch.setattr(settings, "TEST_USER_PASSWORD", None)
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "mark@example.com")
    with pytest.raises(RuntimeError, match="persona"):
        check_demo_settings()


async def test_a_read_only_session_cannot_write_in_postgres(engine):
    """The second layer: even if a write got past the middleware, Postgres refuses it."""
    async with engine.connect() as conn:
        session = AsyncSession(bind=conn)
        await make_read_only(session)
        assert (await session.execute(text("SELECT count(*) FROM users"))).scalar() >= 0
        session.add(User(email="sneaky@tasks.dev"))
        with pytest.raises(DBAPIError, match="read-only transaction"):
            await session.flush()
        await session.rollback()
        await session.close()
