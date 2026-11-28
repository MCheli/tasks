"""The MCP connector at /mcp: metadata, bearer auth (API key and OAuth), tools, OAuth flow."""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio

from app.mcp import db as mcp_db
from app.mcp import mount, oauth

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"


class _Shared:
    """`async with mcp_db.session() as db` handing out the test transaction's session."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_exc):
        return False


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mcp_transport():
    """The streamable HTTP session manager runs once for the whole test session (it can't be
    restarted), as the app lifespan would do in production.

    anyio task groups must be entered and exited in the same task, and pytest-asyncio runs
    fixture setup and teardown in different ones, so the lifespan lives in its own task.
    """
    import asyncio

    started, stop = asyncio.Event(), asyncio.Event()

    async def _run():
        async with mount.lifespan():
            started.set()
            await stop.wait()

    runner = asyncio.create_task(_run())
    await started.wait()
    yield
    stop.set()
    await runner


@pytest_asyncio.fixture(loop_scope="session")
async def mcp_client(client, db, mcp_transport, monkeypatch):
    monkeypatch.setattr(mcp_db, "session", lambda: _Shared(db))
    return client


@pytest_asyncio.fixture(loop_scope="session")
async def api_key(authed_client):
    r = await authed_client.post("/api/api-keys", json={"name": "chore-tracker"})
    assert r.status_code == 201
    key = r.json()["key"]
    await authed_client.post("/api/auth/logout")
    return key


def _rpc(method: str, params: dict | None = None, id_: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


async def _call(client, token: str, method: str, params: dict | None = None):
    r = await client.post(
        "/mcp",
        json=_rpc(method, params),
        headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "error" not in body, body
    return body["result"]


async def _tool(client, token: str, name: str, arguments: dict | None = None) -> dict:
    result = await _call(client, token, "tools/call", {"name": name, "arguments": arguments or {}})
    assert not result.get("isError"), result
    return result["structuredContent"]


# ---------------------------------------------------------------------------
# Metadata and unauthenticated access
# ---------------------------------------------------------------------------


async def test_protected_resource_metadata(client):
    r = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == "http://localhost:8000/mcp"
    assert body["authorization_servers"] == ["http://localhost:8000"]
    assert body["scopes_supported"] == ["tasks"]
    assert body["bearer_methods_supported"] == ["header"]


async def test_authorization_server_metadata(client):
    r = await client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["issuer"] == "http://localhost:8000"
    assert body["authorization_endpoint"] == "http://localhost:8000/authorize"
    assert body["token_endpoint"] == "http://localhost:8000/token"
    assert body["registration_endpoint"] == "http://localhost:8000/register"
    assert body["revocation_endpoint"] == "http://localhost:8000/revoke"
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert "authorization_code" in body["grant_types_supported"]
    assert "refresh_token" in body["grant_types_supported"]


async def test_unauthenticated_mcp_call_is_401_with_resource_metadata(client):
    r = await client.post("/mcp", json=_rpc("initialize"), headers=MCP_HEADERS)
    assert r.status_code == 401
    www = r.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert (
        'resource_metadata="http://localhost:8000/.well-known/oauth-protected-resource/mcp"' in www
    )


async def test_bogus_bearer_is_401(mcp_client):
    for bad in ("tsk_not-a-real-key", "mcpa_nope", "whatever"):
        r = await mcp_client.post(
            "/mcp",
            json=_rpc("initialize"),
            headers={**MCP_HEADERS, "Authorization": f"Bearer {bad}"},
        )
        assert r.status_code == 401, bad


async def test_session_cookie_does_not_authenticate_mcp(authed_client):
    r = await authed_client.post("/mcp", json=_rpc("initialize"), headers=MCP_HEADERS)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# API key as bearer token: initialize, tools/list, the tools
# ---------------------------------------------------------------------------


async def test_initialize_and_tools_list_with_api_key(mcp_client, api_key):
    init = await _call(
        mcp_client,
        api_key,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    assert init["serverInfo"]["name"] == "tasks"
    assert "tools" in init["capabilities"]

    tools = await _call(mcp_client, api_key, "tools/list")
    names = sorted(t["name"] for t in tools["tools"])
    assert names == sorted(
        [
            "list_tasks",
            "get_task",
            "create_task",
            "update_task",
            "complete_task",
            "reopen_task",
            "add_note",
        ]
    )
    create = next(t for t in tools["tools"] if t["name"] == "create_task")
    assert set(create["inputSchema"]["required"]) == {"title", "list"}
    assert create["inputSchema"]["properties"]["owner"]["default"] == "agent"
    listing = next(t for t in tools["tools"] if t["name"] == "list_tasks")
    assert listing["annotations"]["readOnlyHint"] is True


async def test_agent_task_lifecycle_through_tools(mcp_client, api_key):
    created = await _tool(
        mcp_client,
        api_key,
        "create_task",
        {
            "title": "Connector test (safe to delete)",
            "list": "personal",
            "link": "https://x.test/pr/1",
        },
    )
    assert created["owner"] == "agent"
    assert created["status"] == "open"
    assert created["list"] == "personal"
    assert created["source"] == "chore-tracker"  # the API key's name
    assert created["link"] == "https://x.test/pr/1"
    number = created["number"]

    noted = await _tool(mcp_client, api_key, "add_note", {"task": f"#{number}", "body": "Started"})
    assert noted["note_count"] == 1
    assert noted["notes_log"][0]["author"] == "chore-tracker"
    assert noted["notes_log"][0]["body"] == "Started"

    progressed = await _tool(
        mcp_client, api_key, "update_task", {"task": created["id"], "status": "in_progress"}
    )
    assert progressed["status"] == "in_progress"

    listed = await _tool(
        mcp_client, api_key, "list_tasks", {"owner": "agent", "status": "in_progress"}
    )
    assert listed["count"] == 1
    assert listed["tasks"][0]["id"] == created["id"]

    done = await _tool(
        mcp_client, api_key, "complete_task", {"task": str(number), "note": "Merged"}
    )
    assert done["status"] == "done"
    assert done["completed_at"] is not None
    assert done["note_count"] == 2

    hidden = await _tool(mcp_client, api_key, "list_tasks", {"list": "personal"})
    assert hidden["count"] == 0
    shown = await _tool(
        mcp_client, api_key, "list_tasks", {"list": "personal", "include_done": True}
    )
    assert shown["count"] == 1

    full = await _tool(mcp_client, api_key, "get_task", {"task": created["id"]})
    assert [n["body"] for n in full["notes_log"]] == ["Started", "Merged"]
    assert full["status"] == "done"

    reopened = await _tool(mcp_client, api_key, "reopen_task", {"task": created["id"]})
    assert reopened["status"] == "open"
    assert "completed_at" not in reopened

    # The REST API sees the same item, as a completed-then-reopened agent task.
    detail = await mcp_client.get(f"/api/tasks/{created['id']}", headers={"X-API-Key": api_key})
    assert detail.status_code == 200
    assert detail.json()["task"]["owner"] == "agent"
    assert detail.json()["task"]["status"] == "open"
    assert detail.json()["task"]["agent_status"] == "open"


async def test_tools_can_touch_marks_own_items(mcp_client, api_key):
    created = await _tool(
        mcp_client,
        api_key,
        "create_task",
        {"title": "Buy milk", "list": "personal", "owner": "human"},
    )
    assert created["owner"] == "human"
    assert "source" not in created
    done = await _tool(mcp_client, api_key, "complete_task", {"task": created["id"]})
    assert done["status"] == "completed"
    with pytest.raises(AssertionError):
        await _tool(
            mcp_client, api_key, "update_task", {"task": created["id"], "status": "blocked"}
        )


async def test_tool_errors_are_reported_not_raised(mcp_client, api_key):
    result = await _call(
        mcp_client, api_key, "tools/call", {"name": "get_task", "arguments": {"task": "#99999"}}
    )
    assert result["isError"] is True
    assert "not found" in result["content"][0]["text"].lower()


async def test_api_key_only_sees_its_own_users_tasks(mcp_client, api_key, client, other_user):
    await client.post("/api/auth/login", json={"email": other_user.email, "password": "secret"})
    r = await client.post(
        "/api/tasks", json={"category": "personal", "title": "Bob's", "owner": "agent"}
    )
    bob_task = r.json()["task"]
    await client.post("/api/auth/logout")

    listed = await _tool(mcp_client, api_key, "list_tasks", {"owner": "all"})
    assert listed["count"] == 0
    result = await _call(
        mcp_client,
        api_key,
        "tools/call",
        {"name": "get_task", "arguments": {"task": bob_task["id"]}},
    )
    assert result["isError"] is True


# ---------------------------------------------------------------------------
# The OAuth 2.1 flow claude.ai runs: register, authorize (PKCE), Google, code, token
# ---------------------------------------------------------------------------


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


async def _register(client, auth_method: str = "client_secret_post") -> dict:
    r = await client.post(
        "/register",
        json={
            "client_name": "Claude",
            "redirect_uris": [CLAUDE_CALLBACK],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": auth_method,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _authorize(client, reg: dict, challenge: str) -> str:
    """Run /authorize; return the signed state we handed Google."""
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": CLAUDE_CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "client-state-123",
            "scope": "tasks",
            "resource": "http://localhost:8000/mcp",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    google = urlparse(r.headers["location"])
    assert google.netloc == "accounts.google.com"
    q = parse_qs(google.query)
    assert q["redirect_uri"] == ["http://localhost:8000/api/auth/google/callback"]
    assert q["scope"] == ["openid email"]
    assert q["prompt"] == ["select_account"]
    return q["state"][0]


def _fake_google(monkeypatch, info: dict):
    async def _identity(_code: str) -> dict:
        return info

    monkeypatch.setattr(oauth, "fetch_google_identity", _identity)


async def _google_callback(client, state: str) -> dict:
    r = await client.get(
        "/api/auth/google/callback",
        params={"state": state, "code": "google-code"},
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    target = urlparse(r.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == CLAUDE_CALLBACK
    return {k: v[0] for k, v in parse_qs(target.query).items()}


@pytest_asyncio.fixture(loop_scope="session")
async def google_env(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "tasks-client.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "not-a-real-secret")
    monkeypatch.setattr(
        settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
    )
    monkeypatch.setattr(settings, "MCP_ALLOWED_EMAILS", "alice@example.com")


async def test_dynamic_registration_defaults(mcp_client):
    reg = await _register(mcp_client)
    assert reg["client_id"]
    assert reg["client_secret"]
    assert reg["redirect_uris"] == [CLAUDE_CALLBACK]
    assert reg["scope"] == "tasks"
    assert reg["token_endpoint_auth_method"] == "client_secret_post"


async def test_full_oauth_flow_then_tools(mcp_client, test_user, google_env, monkeypatch):
    reg = await _register(mcp_client)
    verifier, challenge = _pkce()
    state = await _authorize(mcp_client, reg, challenge)
    assert oauth.decode_state(state)["client_id"] == reg["client_id"]

    _fake_google(
        monkeypatch,
        {"sub": "google-sub-1", "email": test_user.email.upper(), "email_verified": True},
    )
    back = await _google_callback(mcp_client, state)
    assert back["state"] == "client-state-123"
    assert "code" in back and "error" not in back

    r = await mcp_client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": back["code"],
            "redirect_uri": CLAUDE_CALLBACK,
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
            "code_verifier": verifier,
            "resource": "http://localhost:8000/mcp",
        },
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["access_token"].startswith("mcpa_")
    assert tokens["refresh_token"].startswith("mcpr_")
    assert tokens["expires_in"] == 3600
    assert tokens["scope"] == "tasks"

    # The code is single use.
    again = await mcp_client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": back["code"],
            "redirect_uri": CLAUDE_CALLBACK,
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
            "code_verifier": verifier,
        },
    )
    assert again.status_code == 400
    assert again.json()["error"] == "invalid_grant"

    # The access token works on /mcp and acts as Alice; notes are signed by the client name.
    tools = await _call(mcp_client, tokens["access_token"], "tools/list")
    assert any(t["name"] == "create_task" for t in tools["tools"])
    created = await _tool(
        mcp_client,
        tokens["access_token"],
        "create_task",
        {"title": "From claude.ai", "list": "personal", "source": "thread-42"},
    )
    assert created["source"] == "thread-42"
    noted = await _tool(
        mcp_client, tokens["access_token"], "add_note", {"task": created["id"], "body": "n"}
    )
    assert noted["notes_log"][0]["author"] == "Claude"

    # Refresh rotates the pair; the old access token stops working.
    r = await mcp_client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
        },
    )
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert fresh["access_token"] != tokens["access_token"]
    old = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/list"),
        headers={**MCP_HEADERS, "Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert old.status_code == 401
    await _call(mcp_client, fresh["access_token"], "tools/list")

    # Revocation.
    r = await mcp_client.post(
        "/revoke",
        data={
            "token": fresh["access_token"],
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
        },
    )
    assert r.status_code == 200, r.text
    revoked = await mcp_client.post(
        "/mcp",
        json=_rpc("tools/list"),
        headers={**MCP_HEADERS, "Authorization": f"Bearer {fresh['access_token']}"},
    )
    assert revoked.status_code == 401


async def test_wrong_pkce_verifier_is_refused(mcp_client, test_user, google_env, monkeypatch):
    reg = await _register(mcp_client)
    _verifier, challenge = _pkce()
    state = await _authorize(mcp_client, reg, challenge)
    _fake_google(monkeypatch, {"sub": "g", "email": test_user.email, "email_verified": True})
    back = await _google_callback(mcp_client, state)
    r = await mcp_client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": back["code"],
            "redirect_uri": CLAUDE_CALLBACK,
            "client_id": reg["client_id"],
            "client_secret": reg["client_secret"],
            "code_verifier": "not-the-verifier-" + "x" * 30,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


@pytest.mark.parametrize(
    "info",
    [
        {"sub": "g", "email": "stranger@example.com", "email_verified": True},  # not allowlisted
        {"sub": "g", "email": "alice@example.com", "email_verified": False},  # unverified
        {"sub": "g", "email_verified": True},  # no email
    ],
)
async def test_google_identity_not_allowed_is_denied(
    mcp_client, test_user, google_env, monkeypatch, info
):
    reg = await _register(mcp_client)
    _verifier, challenge = _pkce()
    state = await _authorize(mcp_client, reg, challenge)
    _fake_google(monkeypatch, info)
    back = await _google_callback(mcp_client, state)
    assert back["error"] == "access_denied"
    assert back["state"] == "client-state-123"
    assert "code" not in back


async def test_allowlisted_email_must_be_an_existing_user(mcp_client, google_env, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MCP_ALLOWED_EMAILS", "nobody@example.com")
    reg = await _register(mcp_client)
    _verifier, challenge = _pkce()
    state = await _authorize(mcp_client, reg, challenge)
    _fake_google(monkeypatch, {"sub": "g", "email": "nobody@example.com", "email_verified": True})
    back = await _google_callback(mcp_client, state)
    assert back["error"] == "access_denied"


async def test_google_error_is_passed_back_as_access_denied(mcp_client, test_user, google_env):
    reg = await _register(mcp_client)
    _verifier, challenge = _pkce()
    state = await _authorize(mcp_client, reg, challenge)
    r = await mcp_client.get(
        "/api/auth/google/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert parse_qs(urlparse(r.headers["location"]).query)["error"] == ["access_denied"]


async def test_authorize_without_allowlist_is_refused(mcp_client, google_env, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MCP_ALLOWED_EMAILS", "")
    reg = await _register(mcp_client)
    _verifier, challenge = _pkce()
    r = await mcp_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": CLAUDE_CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "s",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert parse_qs(urlparse(r.headers["location"]).query)["error"] == ["access_denied"]


async def test_authorize_refuses_unregistered_redirect_uri(mcp_client, google_env):
    reg = await _register(mcp_client)
    _verifier, challenge = _pkce()
    r = await mcp_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": "https://evil.example/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.example/cb",
        "http://claude.ai/api/mcp/auth_callback",
        "https://claude.ai.evil.example/cb",
    ],
)
async def test_registration_refuses_redirect_hosts_not_on_the_list(mcp_client, uri):
    r = await mcp_client.post(
        "/register",
        json={
            "client_name": "Claude",
            "redirect_uris": [CLAUDE_CALLBACK, uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_redirect_uri"


async def test_registration_accepts_the_claude_web_and_app_callbacks(mcp_client):
    r = await mcp_client.post(
        "/register",
        json={
            "client_name": "Claude",
            "redirect_uris": [CLAUDE_CALLBACK, "https://claude.com/api/mcp/auth_callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("uri", ["http://localhost:53682/callback", "http://127.0.0.1:53682/cb"])
async def test_registration_accepts_a_loopback_redirect(mcp_client, uri):
    r = await mcp_client.post(
        "/register",
        json={
            "client_name": "Claude Code",
            "redirect_uris": [uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert r.status_code == 201, r.text


async def test_authorize_refuses_a_redirect_host_taken_off_the_list(
    mcp_client, google_env, monkeypatch
):
    from app.config import settings

    reg = await _register(mcp_client)
    monkeypatch.setattr(settings, "MCP_REDIRECT_HOSTS", "localhost")
    _verifier, challenge = _pkce()
    r = await mcp_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": reg["client_id"],
            "redirect_uri": CLAUDE_CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "s",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 400), r.text
    if r.status_code == 302:
        target = urlparse(r.headers["location"])
        assert target.netloc != "accounts.google.com"
        assert parse_qs(target.query)["error"] == ["invalid_request"]
    else:
        assert r.json()["error"] == "invalid_request"


async def test_mcp_state_does_not_disturb_normal_google_login(client, monkeypatch):
    """A callback without our state goes through the ordinary Authlib path (and fails as before)."""
    from authlib.integrations.base_client.errors import MismatchingStateError

    from tests.api.test_auth import _fake_oauth

    _fake_oauth(monkeypatch, error=MismatchingStateError())
    r = await client.get(
        "/api/auth/google/callback", params={"state": "random", "code": "c"}, follow_redirects=False
    )
    assert r.headers["location"] == "/login?error=google"
