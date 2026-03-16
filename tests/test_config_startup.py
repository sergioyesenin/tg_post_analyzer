import importlib
import sys

import pytest


RELEVANT_ENV_KEYS = [
    "PYTHON_DOTENV_DISABLED",
    "APP_ENV",
    "TG_API_ID",
    "TG_API_HASH",
    "DB_URL",
    "DATABASE_URL",
    "APP_TZ",
    "TZ",
    "AUTH_JWT_SECRET",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
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
                "APP_ENV": "dev",
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
                "APP_ENV": "dev",
                "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
                "TZ": "UTC",
                "AUTH_JWT_SECRET": STRONG_TEST_JWT_SECRET,
            },
        )

    assert module.settings.DB_URL.startswith("postgresql+asyncpg://")
    assert module.settings.tz == "UTC"


def test_config_uses_dev_cors_defaults_when_origins_are_not_explicit(monkeypatch: pytest.MonkeyPatch):
    module = _reload_config_with_env(
        monkeypatch,
        {
            "TG_API_ID": "12345",
            "TG_API_HASH": "hash",
            "APP_ENV": "dev",
            "DB_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
            "APP_TZ": "UTC",
            "AUTH_JWT_SECRET": STRONG_TEST_JWT_SECRET,
        },
    )

    assert module.settings.CORS_ALLOWED_ORIGINS == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    assert module.settings.CORS_ALLOW_CREDENTIALS is True


def test_config_requires_explicit_prod_cors_origins(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(RuntimeError) as exc:
        _reload_config_with_env(
            monkeypatch,
            {
                "TG_API_ID": "12345",
                "TG_API_HASH": "hash",
                "APP_ENV": "production",
                "DB_URL": "postgresql+asyncpg://app:strong-pass@db.example.com:5432/tg_analytics",
                "APP_TZ": "UTC",
                "AUTH_JWT_SECRET": STRONG_TEST_JWT_SECRET,
            },
        )

    assert "CORS_ALLOWED_ORIGINS must be set outside dev/local/test" in str(exc.value)


def test_config_rejects_wildcard_origins_when_credentials_enabled(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(RuntimeError) as exc:
        _reload_config_with_env(
            monkeypatch,
            {
                "TG_API_ID": "12345",
                "TG_API_HASH": "hash",
                "APP_ENV": "dev",
                "DB_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
                "APP_TZ": "UTC",
                "AUTH_JWT_SECRET": STRONG_TEST_JWT_SECRET,
                "CORS_ALLOWED_ORIGINS": "*",
                "CORS_ALLOW_CREDENTIALS": "true",
            },
        )

    assert "wildcard origins cannot be used with credentials" in str(exc.value)


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
                "APP_ENV": "dev",
                "DB_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
                "APP_TZ": "UTC",
                "AUTH_JWT_SECRET": secret_value,
            },
        )

    assert expected_fragment in str(exc.value)


def test_config_rejects_insecure_db_credentials_in_non_dev(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(RuntimeError) as exc:
        _reload_config_with_env(
            monkeypatch,
            {
                "TG_API_ID": "12345",
                "TG_API_HASH": "hash",
                "APP_ENV": "production",
                "DB_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics",
                "APP_TZ": "UTC",
                "AUTH_JWT_SECRET": STRONG_TEST_JWT_SECRET,
            },
        )

    message = str(exc.value)
    assert "Insecure DB credentials are not allowed outside dev/local/test" in message
