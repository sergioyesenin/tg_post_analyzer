from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

ROOT_DIR = Path(__file__).resolve().parents[1]

_DEFAULT_ENV = {
    "APP_ENV": "test",
    "TG_API_ID": "123456",
    "TG_API_HASH": "test_api_hash",
    "AUTH_JWT_SECRET": "TestJwtSecretValue_WithEnoughEntropy_123!",
    "AUTH_PROVIDER_MODE": "local",
}


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _ensure_env_defaults(env: dict[str, str]) -> dict[str, str]:
    for key, value in _DEFAULT_ENV.items():
        env.setdefault(key, value)
    return env


def _admin_url_for(test_url: URL) -> URL:
    drivername = test_url.drivername
    if drivername == "postgresql+asyncpg":
        drivername = "postgresql+psycopg2"
    elif drivername == "postgres":
        drivername = "postgresql+psycopg2"
    elif drivername == "postgresql":
        drivername = "postgresql+psycopg2"
    return test_url.set(drivername=drivername, database="postgres")


def ensure_database_exists(test_database_url: str) -> None:
    url = make_url(test_database_url)
    database_name = url.database
    if not database_name:
        raise RuntimeError("TEST_DATABASE_URL must include a database name")

    admin_engine = create_engine(_admin_url_for(url), isolation_level="AUTOCOMMIT", future=True)
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_name},
            ).scalar()
            if not exists:
                connection.execute(text(f"CREATE DATABASE {_quote_ident(database_name)}"))
    finally:
        admin_engine.dispose()


def run_migrations(test_database_url: str) -> None:
    env = _ensure_env_defaults(os.environ.copy())
    env["DB_URL"] = test_database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=ROOT_DIR,
        env=env,
    )


def main() -> None:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        raise RuntimeError("TEST_DATABASE_URL is required for backend integration bootstrap")

    ensure_database_exists(test_database_url)
    run_migrations(test_database_url)
    print(f"Backend test database is ready: {test_database_url}")


if __name__ == "__main__":
    main()
