"""Application configuration sourced from env (TASKS_ prefix) and .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> tuple[str, ...]:
    """Look for .env in the project root regardless of CWD.

    Backend code lives at <root>/backend/app/config.py — walk up to find .env.
    Falls back to plain ".env" so a CWD-local file still wins.
    """
    here = Path(__file__).resolve()
    candidates: list[str] = [".env"]
    for parent in here.parents:
        env_path = parent / ".env"
        if env_path.is_file():
            candidates.append(str(env_path))
            break
    return tuple(candidates)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        env_prefix="TASKS_",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    ENV: str = "development"
    ENABLE_DOCS: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://cycle_todo:changeme@localhost:5432/cycle_todo"

    # Auth
    JWT_SECRET: str = Field(default="dev-only-not-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str | None = None

    # Test user (seeded on startup if both set)
    TEST_USER_EMAIL: str | None = None
    TEST_USER_PASSWORD: str | None = None

    # Google OAuth (scaffolded; not wired yet)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    # CORS — comma-separated string in env, parsed via property below.
    # Stored as raw str so pydantic-settings doesn't try to JSON-decode it.
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:8000"

    @field_validator("COOKIE_DOMAIN", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v

    @property
    def allowed_origins_list(self) -> list[str]:
        return [s.strip() for s in self.ALLOWED_ORIGINS.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
