"""API tests for /api/auth/* endpoints."""

from __future__ import annotations


async def test_login_success_sets_cookie(client, test_user):
    resp = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == test_user.email
    assert "session" in resp.cookies


async def test_login_wrong_password(client, test_user):
    resp = await client.post(
        "/api/auth/login",
        json={"email": test_user.email, "password": "nope"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_unknown_email(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


async def test_login_validation_error(client):
    resp = await client.post("/api/auth/login", json={"email": "not-an-email", "password": ""})
    assert resp.status_code in (400, 422)


async def test_me_requires_auth(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(authed_client, test_user):
    resp = await authed_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == test_user.email


async def test_logout_clears_cookie(authed_client):
    resp = await authed_client.post("/api/auth/logout")
    assert resp.status_code == 204
    # Subsequent /me should be 401.
    me_resp = await authed_client.get("/api/auth/me")
    assert me_resp.status_code == 401


async def test_google_login_returns_503_when_unconfigured(client):
    resp = await client.get("/api/auth/google/login")
    assert resp.status_code == 503


async def test_google_status_reports_unconfigured(client):
    resp = await client.get("/api/auth/google/status")
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}
