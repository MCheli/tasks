"""Startup-time seeding.

Currently only seeds the test user. No cycles or tasks are created on
boot — those happen on-demand the first time the user opens a category.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger("tasks.seed")


async def ensure_test_user() -> None:
    if not (settings.TEST_USER_EMAIL and settings.TEST_USER_PASSWORD):
        logger.info("TEST_USER_* env vars not set; skipping seed.")
        return

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(User).where(User.email == settings.TEST_USER_EMAIL)
        )
        if existing:
            logger.info("Test user %s already exists.", settings.TEST_USER_EMAIL)
            return
        user = User(
            email=settings.TEST_USER_EMAIL,
            hashed_password=hash_password(settings.TEST_USER_PASSWORD),
        )
        db.add(user)
        await db.commit()
        logger.info("Seeded test user %s.", settings.TEST_USER_EMAIL)
