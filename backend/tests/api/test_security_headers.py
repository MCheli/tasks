"""Security headers on responses, and session cookie renewal."""

from __future__ import annotations

from datetime import timedelta

from app.core import security
from app.core.headers import CONTENT_SECURITY_POLICY, PERMISSIONS_POLICY


async def test_api_responses_carry_csp(client):
    resp = await client.get("/api/health")
    assert resp.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert resp.headers["permissions-policy"] == PERMISSIONS_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY


async def test_swagger_ui_has_no_csp(client):
    # Swagger UI pulls its assets from a CDN; a same-origin CSP would blank the page.
    resp = await client.get("/api/docs")
    assert "content-security-policy" not in resp.headers


async def test_due_session_cookie_is_renewed(client, test_user, monkeypatch):
    monkeypatch.setattr(security.settings, "JWT_EXPIRE_DAYS", 1)
    real_datetime = security.datetime

    class _HalfADayAgo(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) - timedelta(hours=13)

    with monkeypatch.context() as m:
        m.setattr(security, "datetime", _HalfADayAgo)
        login = await client.post(
            "/api/auth/login", json={"email": test_user.email, "password": "secret"}
        )
    first = login.cookies["session"]

    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    renewed = resp.cookies.get("session")
    assert renewed
    assert security.decode_session_token(renewed).user_id == test_user.id
    assert security.decode_session_token(first).auth_time == (
        security.decode_session_token(renewed).auth_time
    )


async def test_fresh_session_cookie_is_left_alone(authed_client):
    resp = await authed_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert "session" not in resp.cookies
