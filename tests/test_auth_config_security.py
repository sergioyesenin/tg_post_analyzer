from __future__ import annotations

import pytest

from config import Settings


def _base_env(monkeypatch, *, app_env: str, cookie_secure: str, cookie_samesite: str = "lax") -> None:
    values = {
        "TG_API_ID": "123456",
        "TG_API_HASH": "hash",
        "DB_URL": "postgresql+asyncpg://app:strong-password-123@localhost:5432/tg_analytics",
        "AUTH_JWT_SECRET": "VeryStrongJwtSecretValue123!VeryStrong",
        "APP_ENV": app_env,
        "APP_TZ": "UTC",
        "AUTH_REFRESH_COOKIE_SECURE": cookie_secure,
        "AUTH_REFRESH_COOKIE_SAMESITE": cookie_samesite,
        "AUTH_REFRESH_COOKIE_PATH": "/api/auth",
        "AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
        "AUTH_LOGIN_MAX_ATTEMPTS": "10",
        "AUTH_REFRESH_MAX_ATTEMPTS": "20",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_settings_reject_insecure_refresh_cookie_outside_non_prod(monkeypatch):
    _base_env(monkeypatch, app_env="prod", cookie_secure="false")

    with pytest.raises(RuntimeError, match="AUTH_REFRESH_COOKIE_SECURE must be true"):
        Settings()


def test_settings_allow_insecure_refresh_cookie_in_dev(monkeypatch):
    _base_env(monkeypatch, app_env="dev", cookie_secure="false")

    cfg = Settings()

    assert cfg.IS_NON_PROD is True
    assert cfg.AUTH_REFRESH_COOKIE_SECURE is False


def test_settings_reject_samesite_none_without_secure(monkeypatch):
    _base_env(monkeypatch, app_env="dev", cookie_secure="false", cookie_samesite="none")

    with pytest.raises(RuntimeError, match="AUTH_REFRESH_COOKIE_SAMESITE=none requires AUTH_REFRESH_COOKIE_SECURE=true"):
        Settings()


def test_settings_reject_invalid_refresh_cookie_path(monkeypatch):
    _base_env(monkeypatch, app_env="dev", cookie_secure="false")
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_PATH", "api/auth")

    with pytest.raises(RuntimeError, match="AUTH_REFRESH_COOKIE_PATH: value must start with '/'"):
        Settings()


def test_settings_reject_localhost_refresh_cookie_domain_outside_non_prod(monkeypatch):
    _base_env(monkeypatch, app_env="prod", cookie_secure="true")
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_DOMAIN", "localhost")

    with pytest.raises(RuntimeError, match="AUTH_REFRESH_COOKIE_DOMAIN cannot point to localhost"):
        Settings()
