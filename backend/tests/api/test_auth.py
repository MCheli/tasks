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


async def test_google_login_returns_503_when_unconfigured(client, monkeypatch):
    # Force the configured-check to fail, simulating an env without creds.
    from app.core import oauth as oauth_module

    monkeypatch.setattr(oauth_module, "is_google_configured", lambda: False)
    monkeypatch.setattr(oauth_module, "oauth_client", lambda: None)
    resp = await client.get("/api/auth/google/login")
    assert resp.status_code == 503


async def test_google_status_reports_unconfigured(client, monkeypatch):
    from app.core import oauth as oauth_module

    monkeypatch.setattr(oauth_module, "is_google_configured", lambda: False)
    # The auth router imports `is_google_configured` directly, so patch it
    # on the router module too.
    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "is_google_configured", lambda: False)
    resp = await client.get("/api/auth/google/status")
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}


async def test_google_status_reports_configured_with_creds(client, monkeypatch):
    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "is_google_configured", lambda: True)
    resp = await client.get("/api/auth/google/status")
    assert resp.status_code == 200
    assert resp.json() == {"configured": True}


async def test_google_login_redirects_when_configured(client, monkeypatch):
    """Hitting /google/login with creds present should 302 to accounts.google.com."""
    from app.core import oauth as oauth_module
    from app.routers import auth as auth_router

    monkeypatch.setattr(oauth_module, "is_google_configured", lambda: True)
    monkeypatch.setattr(auth_router, "is_google_configured", lambda: True)
    # Don't actually hit Google — just confirm the router doesn't reject the
    # request before reaching the OAuth client. We rely on the configured
    # creds in .env (added during the Google OAuth setup step).
    resp = await client.get("/api/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers.get("location", "")
