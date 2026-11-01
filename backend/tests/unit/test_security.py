"""Unit tests for password hashing and JWT helpers."""

from __future__ import annotations

import time
from uuid import uuid4

import jwt
import pytest

from app.core import security
from app.core.security import (
    SessionToken,
    create_access_token,
    decode_access_token,
    decode_session_token,
    hash_password,
    refreshed_access_token,
    verify_password,
)


def test_hash_password_round_trips():
    h = hash_password("secret")
    assert h and h != "secret"
    assert verify_password("secret", h) is True
    assert verify_password("wrong", h) is False


def test_verify_password_handles_none_hash():
    assert verify_password("anything", "") is False


def test_token_round_trips():
    user_id = uuid4()
    tok = create_access_token(user_id)
    decoded = decode_access_token(tok)
    assert decoded == user_id


def test_token_invalid_returns_none():
    assert decode_access_token("not-a-real-token") is None


def test_token_tampered_returns_none():
    user_id = uuid4()
    tok = create_access_token(user_id)
    # Flip a character in the *middle* of the signature segment so the
    # change definitely lands in non-padding bytes.
    header_payload, _, signature = tok.rpartition(".")
    if len(signature) < 2:
        pytest.skip("Unexpectedly short signature")
    midpoint = len(signature) // 2
    flipped_char = "A" if signature[midpoint] != "A" else "B"
    tampered = f"{header_payload}.{signature[:midpoint]}{flipped_char}{signature[midpoint + 1:]}"
    assert decode_access_token(tampered) is None


def _session(token: str) -> SessionToken:
    session = decode_session_token(token)
    assert session is not None
    return session


def _signed_in(hours_ago: int, *, refreshed_hours_ago: int | None = None) -> SessionToken:
    """A session as decoded from a token issued in the past (PyJWT rejects a future iat)."""
    now = int(time.time())
    auth_time = now - hours_ago * 3600
    issued_at = now - (hours_ago if refreshed_hours_ago is None else refreshed_hours_ago) * 3600
    return SessionToken(
        user_id=uuid4(),
        issued_at=issued_at,
        expires_at=security._expiry(issued_at, auth_time),
        auth_time=auth_time,
    )


def test_fresh_token_is_not_refreshed():
    assert refreshed_access_token(_session(create_access_token(uuid4()))) is None


def test_old_token_is_refreshed_within_the_session_limit(monkeypatch):
    monkeypatch.setattr(security.settings, "JWT_EXPIRE_DAYS", 1)
    monkeypatch.setattr(security.settings, "JWT_MAX_SESSION_DAYS", 7)
    original = _signed_in(13)

    renewed = _session(refreshed_access_token(original))
    assert renewed.user_id == original.user_id
    assert renewed.auth_time == original.auth_time
    assert renewed.expires_at > original.expires_at


def test_refresh_never_extends_past_the_session_limit(monkeypatch):
    monkeypatch.setattr(security.settings, "JWT_EXPIRE_DAYS", 1)
    monkeypatch.setattr(security.settings, "JWT_MAX_SESSION_DAYS", 2)
    original = _signed_in(30, refreshed_hours_ago=13)

    renewed = _session(refreshed_access_token(original))
    assert renewed.expires_at == original.auth_time + 2 * 24 * 3600
    # Once a token reaches the limit there is nothing left to extend.
    assert refreshed_access_token(_signed_in(40, refreshed_hours_ago=13)) is None


def test_defaults_keep_a_fixed_seven_day_session():
    assert refreshed_access_token(_signed_in(3 * 24)) is None


def test_token_without_auth_time_uses_issue_time():
    now = int(time.time())
    legacy = jwt.encode(
        {"sub": str(uuid4()), "iat": now, "exp": now + 60},
        security.settings.JWT_SECRET,
        algorithm=security.settings.JWT_ALGORITHM,
    )
    assert _session(legacy).auth_time == now
