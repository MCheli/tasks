"""Production refuses public default secrets."""

from __future__ import annotations

import pytest

from app.config import DEV_API_KEY_PEPPER, DEV_JWT_SECRET, Settings, check_production_settings

STRONG = "a" * 64


def _settings(**overrides) -> Settings:
    values = {
        "ENV": "production",
        "JWT_SECRET": STRONG,
        "API_KEY_PEPPER": "b" * 64,
        "COOKIE_SECURE": True,
        "DATABASE_URL": "postgresql+asyncpg://cycle_todo:s3cret-db-pw@db:5432/cycle_todo",
    }
    values.update(overrides)
    return Settings(**values)


def test_development_is_not_checked():
    assert check_production_settings(_settings(ENV="development", JWT_SECRET=DEV_JWT_SECRET)) == (
        [],
        [],
    )


@pytest.mark.parametrize(
    "secret", [DEV_JWT_SECRET, "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32", ""]
)
def test_default_jwt_secret_is_an_error_in_production(secret):
    errors, _ = check_production_settings(_settings(JWT_SECRET=secret))
    assert len(errors) == 1 and "TASKS_JWT_SECRET" in errors[0]


def test_short_jwt_secret_is_an_error():
    errors, _ = check_production_settings(_settings(JWT_SECRET="short"))
    assert len(errors) == 1 and "shorter than 32" in errors[0]


@pytest.mark.parametrize("pepper", [DEV_API_KEY_PEPPER, ""])
def test_default_pepper_is_an_error(pepper):
    errors, _ = check_production_settings(_settings(API_KEY_PEPPER=pepper))
    assert len(errors) == 1 and "TASKS_API_KEY_PEPPER" in errors[0]


def test_default_database_password_is_an_error():
    errors, _ = check_production_settings(
        _settings(DATABASE_URL="postgresql+asyncpg://cycle_todo:changeme@db:5432/cycle_todo")
    )
    assert len(errors) == 1 and "TASKS_DATABASE_URL" in errors[0]


def test_hardened_production_has_no_findings():
    assert check_production_settings(_settings()) == ([], [])


def test_insecure_cookie_is_only_a_warning():
    errors, warnings = check_production_settings(_settings(COOKIE_SECURE=False))
    assert errors == []
    assert len(warnings) == 1 and "TASKS_COOKIE_SECURE" in warnings[0]


async def test_startup_fails_closed(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "settings", _settings(JWT_SECRET=DEV_JWT_SECRET))
    with pytest.raises(RuntimeError, match="insecure production settings"):
        async with main.lifespan(main.app):
            pass


@pytest.mark.parametrize(
    ("env", "enable_docs", "expected"),
    [
        ("development", None, True),
        ("production", None, False),
        ("production", True, True),
        ("development", False, False),
    ],
)
def test_docs_default_off_in_production(env, enable_docs, expected):
    assert _settings(ENV=env, ENABLE_DOCS=enable_docs).docs_enabled is expected
