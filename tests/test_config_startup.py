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

STRONG_TEST_JWT_SECRET = "A_strong_test_secret_value_2026!XYZ"


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
                "AUTH_JWT_SECRET": STRONG_TEST_JWT_SECRET,
            },
        )

    assert module.settings.DB_URL.startswith("postgresql+asyncpg://")
    assert module.settings.tz == "UTC"


@pytest.mark.parametrize(
    ("secret_value", "expected_fragment"),
    [
        ("change-me-in-prod", "insecure placeholder value"),
        ("", "Missing required env var: AUTH_JWT_SECRET"),
        ("short-secret", "at least 32 characters"),
        ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "at least 3 character classes"),
    ],
)
def test_config_fails_fast_for_weak_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
    secret_value: str,
    expected_fragment: str,
):
    with pytest.raises(RuntimeError) as exc:
        _reload_config_with_env(
            monkeypatch,
            {
                "TG_API_ID": "12345",
                "TG_API_HASH": "hash",
                "DB_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
                "APP_TZ": "UTC",
                "AUTH_JWT_SECRET": secret_value,
            },
        )

    assert expected_fragment in str(exc.value)
