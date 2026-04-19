"""Fixtures specific to API-level tests."""
from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user  # noqa: F401  (for type clarity)
from app.db.session import get_db
from app.main import app


@pytest_asyncio.fixture(loop_scope="session")
async def client(db):
    """An httpx AsyncClient bound to the FastAPI app, sharing the test DB session.

    Override `get_db` so every request inside a test sees the same transaction
    that the test fixtures already populated.
    """

    async def _override_db():
        # IMPORTANT: do NOT commit inside this override; the outer fixture
        # rolls back the transaction at end-of-test. We yield the session
        # without commit/rollback semantics here.
        yield db

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def authed_client(client, test_user):
    """Client with a session cookie set for `test_user` (password: 'secret')."""
    resp = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "secret"},
    )
    assert resp.status_code == 200, resp.text
    return client
