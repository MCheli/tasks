"""OAuth 2.1 authorization server for the MCP connector, backed by Postgres.

claude.ai registers itself (RFC 7591), sends the user to /authorize with PKCE, and we send the
user on to Google. Google comes back to the app's existing callback (the redirect URI the Tasks
OAuth client already has registered) with our signed `state`; the callback recognises an MCP
state and hands it to `complete_google_sign_in`, which checks the verified email against
TASKS_MCP_ALLOWED_EMAILS and the app's users, issues a one-time code, and redirects to
claude.ai. /token then exchanges the code (PKCE verified by the SDK) for opaque tokens.

Bearer tokens accepted on /mcp: the opaque access tokens issued here, and the app's own API
keys (tsk_...), so scheduled jobs can use the tools without OAuth.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
import jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.mcp import db as mcp_db
from app.models.api_key import ApiKey
from app.models.mcp_oauth import OAuthClient, OAuthCode, hash_token
from app.models.mcp_oauth import OAuthToken as OAuthTokenRow
from app.models.user import User

logger = logging.getLogger("tasks.mcp.oauth")

SCOPE = "tasks"
CODE_TTL_SECONDS = 5 * 60
STATE_TTL_SECONDS = 10 * 60
STATE_TYP = "tasks-mcp-authorize"
ACCESS_PREFIX = "mcpa_"
REFRESH_PREFIX = "mcpr_"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class TasksAccessToken(AccessToken):
    """The SDK's AccessToken plus the user the tools act for and a label for note authors."""

    user_id: UUID
    label: str


def resource_url() -> str:
    return f"{str(settings.PUBLIC_URL).rstrip('/')}/mcp"


def _now() -> datetime:
    return datetime.now(UTC)


def redirect_allowed(uri: str) -> bool:
    """Whether a connector may have its codes sent to `uri` (TASKS_MCP_REDIRECT_HOSTS)."""
    try:
        parts = urlsplit(uri)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if host not in settings.mcp_redirect_hosts:
        return False
    if host in LOOPBACK_HOSTS:
        return parts.scheme in ("http", "https")
    return parts.scheme == "https"


# ---------------------------------------------------------------------------
# Google leg: our signed state carries the pending authorization request
# ---------------------------------------------------------------------------


def encode_state(client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "typ": STATE_TYP,
            "iat": now,
            "exp": now + STATE_TTL_SECONDS,
            "nonce": secrets.token_urlsafe(16),
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "explicit": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "state": params.state,
            "scopes": params.scopes or [SCOPE],
            "resource": params.resource,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_state(state: str | None) -> dict | None:
    """The pending request if `state` is one of ours (and unexpired), else None."""
    if not state or state.count(".") != 2:
        return None
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except (jwt.PyJWTError, ValueError):
        return None
    if payload.get("typ") != STATE_TYP:
        return None
    return payload


def google_authorize_url(state: str) -> str:
    return (
        GOOGLE_AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "response_type": "code",
                "scope": "openid email",
                "state": state,
                # Pick the account each time instead of silently reusing one.
                "prompt": "select_account",
            }
        )
    )


async def fetch_google_identity(code: str) -> dict:
    """Exchange Google's code and return its userinfo (sub, email, email_verified, ...).

    Patched in tests. Raises httpx errors or ValueError on anything unexpected.
    """
    async with httpx.AsyncClient(timeout=15) as http:
        token_resp = await http.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("Google token response had no access_token")
        info = await http.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        info.raise_for_status()
        return info.json()


def _redirect_with(base: str, **params: str | None) -> str:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{base}{'&' if '?' in base else '?'}{query}"


async def complete_google_sign_in(
    db: AsyncSession, pending: dict, code: str | None, error: str | None
) -> str:
    """Finish the authorization: returns the URL to send the browser to (claude.ai's callback).

    Only a verified Google email on the allowlist that is also an existing user gets a code.
    Nothing here creates users. Failures redirect to the client with access_denied, never with
    the email or the reason in detail.
    """
    client_redirect = pending["redirect_uri"]
    client_state = pending.get("state")

    def denied(reason: str) -> str:
        logger.warning("MCP connector sign-in refused: %s", reason)
        return _redirect_with(client_redirect, error="access_denied", state=client_state)

    if error or not code:
        return denied(f"Google returned {error or 'no code'}")
    try:
        info = await fetch_google_identity(code)
    except Exception as exc:  # noqa: BLE001
        return denied(f"Google exchange failed: {type(exc).__name__}")

    email = str(info.get("email") or "").lower()
    sub = info.get("sub")
    if not email or not sub or info.get("email_verified") not in (True, "true"):
        return denied("unverified or missing email")
    if email not in settings.mcp_allowed_emails:
        return denied("account not on the allowlist")
    user = await db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        return denied("allowlisted account is not a user of the app")

    raw_code = secrets.token_urlsafe(32)
    db.add(
        OAuthCode(
            code_hash=hash_token(raw_code),
            client_id=pending["client_id"],
            user_id=user.id,
            redirect_uri=client_redirect,
            redirect_uri_provided_explicitly=bool(pending.get("explicit")),
            code_challenge=pending["code_challenge"],
            scopes=" ".join(pending.get("scopes") or [SCOPE]),
            resource=pending.get("resource"),
            expires_at=_now() + timedelta(seconds=CODE_TTL_SECONDS),
        )
    )
    await db.flush()
    logger.info("MCP connector sign-in granted for client %s", pending["client_id"])
    return _redirect_with(client_redirect, code=raw_code, state=client_state)


# ---------------------------------------------------------------------------
# The SDK provider
# ---------------------------------------------------------------------------


class TasksOAuthProvider:
    """OAuthAuthorizationServerProvider over the mcp_oauth_* tables + API-key bearer tokens."""

    # -- clients -----------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with mcp_db.session() as db:
            row = await db.get(OAuthClient, client_id)
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row.info)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in client_info.redirect_uris or []]
        if not uris or not all(redirect_allowed(u) for u in uris):
            raise RegistrationError("invalid_redirect_uri", "Redirect URI host is not allowed")
        async with mcp_db.session() as db:
            db.add(
                OAuthClient(
                    client_id=client_info.client_id,
                    client_name=(client_info.client_name or "")[:200] or None,
                    info=client_info.model_dump(mode="json", exclude_none=True),
                )
            )
            await db.commit()
        logger.info("MCP connector: registered OAuth client %s", client_info.client_id)

    # -- authorize ---------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if not settings.mcp_allowed_emails:
            raise AuthorizeError("access_denied", "Connector sign-in is not enabled on this server")
        if not (
            settings.GOOGLE_CLIENT_ID
            and settings.GOOGLE_CLIENT_SECRET
            and settings.GOOGLE_REDIRECT_URI
        ):
            raise AuthorizeError("temporarily_unavailable", "Google sign-in is not configured")
        # Also checked here for clients registered before the host list existed.
        if not redirect_allowed(str(params.redirect_uri)):
            raise AuthorizeError("invalid_request", "Redirect URI host is not allowed")
        return google_authorize_url(encode_state(client, params))

    # -- codes -------------------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        async with mcp_db.session() as db:
            row = await db.get(OAuthCode, hash_token(authorization_code))
        if row is None or row.used_at is not None or row.client_id != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=row.scopes.split() or [SCOPE],
            expires_at=row.expires_at.timestamp(),
            client_id=row.client_id,
            code_challenge=row.code_challenge,
            redirect_uri=row.redirect_uri,  # type: ignore[arg-type]
            redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
            resource=row.resource,
            subject=str(row.user_id),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        async with mcp_db.session() as db:
            row = await db.get(OAuthCode, hash_token(authorization_code.code))
            if row is None or row.used_at is not None:
                raise TokenError("invalid_grant", "authorization code already used")
            row.used_at = _now()
            tokens = await self._issue(
                db, client.client_id, row.user_id, row.scopes.split() or [SCOPE], row.resource
            )
            await db.commit()
        return tokens

    # -- refresh -----------------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        async with mcp_db.session() as db:
            row = await db.get(OAuthTokenRow, hash_token(refresh_token))
        if row is None or row.kind != "refresh" or row.revoked_at is not None:
            return None
        if row.client_id != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row.client_id,
            scopes=row.scopes.split() or [SCOPE],
            expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
            resource=row.resource,
            subject=str(row.user_id),
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        async with mcp_db.session() as db:
            row = await db.get(OAuthTokenRow, hash_token(refresh_token.token))
            if row is None or row.revoked_at is not None:
                raise TokenError("invalid_grant", "refresh token is no longer valid")
            await self._revoke_pair(db, row.pair_id)  # rotation: the old pair dies
            tokens = await self._issue(db, client.client_id, row.user_id, scopes, row.resource)
            await db.commit()
        return tokens

    # -- verify ------------------------------------------------------------------------

    async def load_access_token(self, token: str) -> TasksAccessToken | None:
        if token.startswith(ApiKey.KEY_PREFIX):
            return await self._from_api_key(token)
        if not token.startswith(ACCESS_PREFIX):
            return None
        async with mcp_db.session() as db:
            row = await db.get(OAuthTokenRow, hash_token(token))
            if row is None or row.kind != "access" or row.revoked_at is not None:
                return None
            if row.expires_at and row.expires_at < _now():
                return None
            client = await db.get(OAuthClient, row.client_id)
            row.last_used_at = _now()
            await db.commit()
        label = (client.client_name if client and client.client_name else "connector").strip()
        return TasksAccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scopes.split() or [SCOPE],
            expires_at=int(row.expires_at.timestamp()) if row.expires_at else None,
            resource=row.resource,
            subject=str(row.user_id),
            user_id=row.user_id,
            label=label,
        )

    async def _from_api_key(self, raw: str) -> TasksAccessToken | None:
        async with mcp_db.session() as db:
            key = await db.scalar(
                select(ApiKey).where(
                    ApiKey.key_hash == ApiKey.hash_key(raw), ApiKey.is_active.is_(True)
                )
            )
            if key is None:
                return None
            key.last_used_at = _now()
            await db.commit()
        return TasksAccessToken(
            token=raw,
            client_id=f"api-key:{key.id}",
            scopes=[SCOPE],
            expires_at=None,
            resource=resource_url(),
            subject=str(key.user_id),
            user_id=key.user_id,
            label=key.name,
        )

    # -- revoke ------------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if token.token.startswith(ApiKey.KEY_PREFIX):
            return  # API keys are revoked in the app's settings, not through the connector
        async with mcp_db.session() as db:
            row = await db.get(OAuthTokenRow, hash_token(token.token))
            if row is not None:
                await self._revoke_pair(db, row.pair_id)
                await db.commit()

    # -- helpers -----------------------------------------------------------------------

    async def _revoke_pair(self, db: AsyncSession, pair_id: UUID) -> None:
        rows = (
            await db.execute(
                select(OAuthTokenRow).where(
                    OAuthTokenRow.pair_id == pair_id, OAuthTokenRow.revoked_at.is_(None)
                )
            )
        ).scalars()
        now = _now()
        for r in rows:
            r.revoked_at = now

    async def _issue(
        self,
        db: AsyncSession,
        client_id: str,
        user_id: UUID,
        scopes: list[str],
        resource: str | None,
    ) -> OAuthToken:
        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        pair_id = uuid4()
        now = _now()
        scope_str = " ".join(scopes or [SCOPE])
        db.add(
            OAuthTokenRow(
                token_hash=hash_token(access),
                kind="access",
                pair_id=pair_id,
                client_id=client_id,
                user_id=user_id,
                scopes=scope_str,
                resource=resource or resource_url(),
                expires_at=now + timedelta(seconds=settings.MCP_ACCESS_TOKEN_SECONDS),
            )
        )
        db.add(
            OAuthTokenRow(
                token_hash=hash_token(refresh),
                kind="refresh",
                pair_id=pair_id,
                client_id=client_id,
                user_id=user_id,
                scopes=scope_str,
                resource=resource or resource_url(),
                expires_at=now + timedelta(days=settings.MCP_REFRESH_TOKEN_DAYS),
            )
        )
        await db.flush()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=settings.MCP_ACCESS_TOKEN_SECONDS,
            scope=scope_str,
            refresh_token=refresh,
        )


provider = TasksOAuthProvider()
