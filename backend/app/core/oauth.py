"""Google OAuth scaffolding.

Wiring is deferred until Mark sets up Google Cloud Console credentials.
The router exposes /auth/google/login and /auth/google/callback so the
frontend can render a (disabled) Google button without hitting 404s.
"""
from __future__ import annotations

from app.config import settings


def is_google_configured() -> bool:
    """Return True only when both client_id and client_secret are present."""
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


# TODO(mark): once Google Cloud Console is set up, finish:
#   1. Build authlib client with settings.GOOGLE_CLIENT_ID/SECRET.
#   2. Implement google_login_redirect(state) → returns Google consent URL.
#   3. Implement google_callback_exchange(code, state) → exchanges code for
#      Google id_token, extracts `sub` and `email`, upserts a User row.
