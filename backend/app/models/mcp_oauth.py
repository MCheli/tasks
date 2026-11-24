"""Storage for the MCP connector's OAuth 2.1 authorization server (see app/mcp/oauth.py).

Three small tables, all keyed so that the two uvicorn workers can share them:

- mcp_oauth_clients: dynamically registered clients (claude.ai registers itself). The record
  is the RFC 7591 client information the SDK hands us, kept whole as JSON.
- mcp_oauth_codes: one-time authorization codes, stored hashed, used once.
- mcp_oauth_tokens: opaque access and refresh tokens, stored hashed. An access/refresh pair
  shares a pair_id so revoking one revokes both.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def hash_token(raw: str) -> str:
    """Hash a code or token for storage, keyed with the API-key pepper.

    The values themselves have 256 bits of entropy, so the pepper only ties them to this
    deployment: rotating TASKS_API_KEY_PEPPER signs every connector out, like it revokes
    every API key.
    """
    from app.config import settings

    return hmac.new(
        settings.API_KEY_PEPPER.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class OAuthClient(Base):
    __tablename__ = "mcp_oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The full OAuthClientInformationFull dump (redirect_uris, auth method, secret, scope...).
    info: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OAuthCode(Base):
    __tablename__ = "mcp_oauth_codes"

    code_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(200), nullable=False)
    scopes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OAuthToken(Base):
    __tablename__ = "mcp_oauth_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # access | refresh
    pair_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid4)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scopes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_mcp_oauth_tokens_pair", "pair_id"),)
