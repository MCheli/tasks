"""Unit tests for password hashing and JWT helpers."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
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
