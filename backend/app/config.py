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


# Defaults that are public in this repo. Production must override them.
DEV_JWT_SECRET = "dev-only-not-secret-change-me"
DEV_API_KEY_PEPPER = "dev-only-api-key-pepper-change-me"
_PLACEHOLDER_SECRETS = {DEV_JWT_SECRET, "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32", ""}


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
    JWT_SECRET: str = Field(default=DEV_JWT_SECRET)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str | None = None

    # API keys — pepper for HMAC hashing. Rotating this invalidates all keys.
    API_KEY_PEPPER: str = Field(default=DEV_API_KEY_PEPPER)

    # Test user (seeded on startup if both set)
    TEST_USER_EMAIL: str | None = None
    TEST_USER_PASSWORD: str | None = None

    # Google OAuth (scaffolded; not wired yet)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    # Public demo (see app/demo.py). DEMO_MODE turns a deployment into the read-only demo;
    # DEMO_URL on the real deployment makes its login page link to the demo.
    DEMO_MODE: bool = False
    DEMO_URL: str | None = None
    DEMO_USER_EMAIL: str = "claudius@tasks.dev"

    # CORS — comma-separated string in env, parsed via property below.
    # Stored as raw str so pydantic-settings doesn't try to JSON-decode it.
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:8000"

    @field_validator("COOKIE_DOMAIN", "DEMO_URL", mode="before")
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


def check_production_settings(s: Settings) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for insecure production settings.

    Anyone who knows the JWT secret can mint a session for any user, and the defaults are in git.
    A default JWT secret is an error, but it is logged rather than raised for now: the prod env
    hasn't been confirmed, and Watchtower would otherwise auto-deploy a crash loop.
    TODO: fail closed (raise) once production's TASKS_JWT_SECRET is confirmed set.
    """
    if not s.is_production:
        return [], []
    errors = []
    if s.JWT_SECRET in _PLACEHOLDER_SECRETS:
        errors.append(
            "TASKS_ENV=production with the default TASKS_JWT_SECRET: anyone can forge sessions. "
            "Set it to `openssl rand -hex 32`."
        )
    warnings = []
    if len(s.JWT_SECRET) < 32:
        warnings.append("TASKS_JWT_SECRET is shorter than 32 characters.")
    if s.API_KEY_PEPPER == DEV_API_KEY_PEPPER:
        warnings.append(
            "TASKS_API_KEY_PEPPER is the public default. Setting it invalidates existing API keys."
        )
    if not s.COOKIE_SECURE:
        warnings.append("TASKS_COOKIE_SECURE is false; session cookies can travel over plain HTTP.")
    return errors, warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
