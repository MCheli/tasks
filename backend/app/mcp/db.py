"""Database sessions for the connector's own code paths (the OAuth provider and the tools).

They run outside FastAPI's request dependency, so they open their own sessions here. Tests
replace `session` with a factory that hands out the test transaction's session.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


def session() -> AsyncSession:
    return AsyncSessionLocal()
