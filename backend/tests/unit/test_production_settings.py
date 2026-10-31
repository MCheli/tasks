"""Production refuses the public default session secret."""

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
    }
    values.update(overrides)
    return Settings(**values)


def test_development_is_not_checked():
    assert check_production_settings(_settings(ENV="development", JWT_SECRET=DEV_JWT_SECRET)) == []


@pytest.mark.parametrize(
    "secret", [DEV_JWT_SECRET, "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32", ""]
)
def test_default_jwt_secret_is_fatal_in_production(secret):
    with pytest.raises(RuntimeError, match="TASKS_JWT_SECRET"):
        check_production_settings(_settings(JWT_SECRET=secret))


def test_hardened_production_has_no_warnings():
    assert check_production_settings(_settings()) == []


def test_soft_problems_are_warnings():
    warnings = check_production_settings(
        _settings(JWT_SECRET="short", API_KEY_PEPPER=DEV_API_KEY_PEPPER, COOKIE_SECURE=False)
    )
    assert len(warnings) == 3
