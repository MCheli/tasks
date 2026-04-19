"""Google OAuth client (Authlib-based).

The router calls into this module to start the OAuth redirect and to
exchange the callback `code` for a verified userinfo payload. We only
need email + sub from Google; everything else is ignored.

If TASKS_GOOGLE_CLIENT_ID / SECRET aren't set, `oauth_client()` returns
None and the router routes return 503.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from app.config import settings

# Google's OpenID Connect discovery doc — Authlib reads endpoints from it.
_GOOGLE_CONF_URL = "https://accounts.google.com/.well-known/openid-configuration"

_oauth: OAuth | None = None


def is_google_configured() -> bool:
    """Return True only when both client_id and client_secret are present."""
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def oauth_client() -> OAuth | None:
    """Lazily build (and memoize) the Authlib OAuth registry.

    Returns None if Google credentials are missing.
    """
    global _oauth
    if not is_google_configured():
        return None
    if _oauth is not None:
        return _oauth

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url=_GOOGLE_CONF_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    _oauth = oauth
    return _oauth
