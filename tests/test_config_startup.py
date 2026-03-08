import importlib
import sys

import pytest


RELEVANT_ENV_KEYS = [
    "PYTHON_DOTENV_DISABLED",
    "TG_API_ID",
    "TG_API_HASH",
    "DB_URL",
    "DATABASE_URL",
    "APP_TZ",
    "TZ",
    "AUTH_JWT_SECRET",
]


def _reload_config_with_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]):
    for key in RELEVANT_ENV_KEYS:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    sys.modules.pop("config", None)
    return importlib.import_module("config")


def test_config_fails_fast_when_required_env_missing(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(RuntimeError) as exc:
        _reload_config_with_env(
            monkeypatch,
            {
                "TG_API_ID": "12345",
                "TG_API_HASH": "hash",
                "APP_TZ": "UTC",
            },
        )

    message = str(exc.value)
    assert "Missing required env var: AUTH_JWT_SECRET" in message
    assert "Missing required env var: DB_URL" in message


def test_config_accepts_deprecated_aliases_with_warning(monkeypatch: pytest.MonkeyPatch):
    with pytest.warns(UserWarning, match="deprecated"):
        module = _reload_config_with_env(
            monkeypatch,
            {
                "TG_API_ID": "12345",
                "TG_API_HASH": "hash",
                "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
                "TZ": "UTC",
                "AUTH_JWT_SECRET": "test-secret",
            },
        )

    assert module.settings.DB_URL.startswith("postgresql+asyncpg://")
    assert module.settings.tz == "UTC"
