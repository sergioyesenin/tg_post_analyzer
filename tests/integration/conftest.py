from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

ROOT_DIR = Path(__file__).resolve().parents[2]

_DEFAULT_ENV = {
    "APP_ENV": "test",
    "TG_API_ID": "123456",
    "TG_API_HASH": "test_api_hash",
    "AUTH_JWT_SECRET": "TestJwtSecretValue_WithEnoughEntropy_123!",
    "AUTH_PROVIDER_MODE": "local",
}


def _apply_test_env_defaults() -> None:
    for key, value in _DEFAULT_ENV.items():
        os.environ.setdefault(key, value)


_apply_test_env_defaults()

from deps import get_session


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require TEST_DATABASE_URL and a real Postgres database.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture(scope="session")
def integration_database_url(pytestconfig: pytest.Config) -> str:
    if not pytestconfig.getoption("--run-integration"):
        pytest.skip("integration tests are disabled without --run-integration")

    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        raise pytest.UsageError("TEST_DATABASE_URL is required when running integration tests")
    return value


@pytest.fixture(scope="session")
def integration_database_ready(integration_database_url: str) -> None:
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = integration_database_url
    subprocess.run(
        [sys.executable, "scripts/test_bootstrap_backend.py"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )


def _sync_url_for(database_url: str) -> URL:
    url = make_url(database_url)
    if url.drivername == "postgresql+asyncpg":
        return url.set(drivername="postgresql+psycopg2")
    if url.drivername == "postgres":
        return url.set(drivername="postgresql+psycopg2")
    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg2")
    return url


@pytest.fixture(scope="session")
def integration_engine(integration_database_ready: None, integration_database_url: str):
    engine = create_async_engine(integration_database_url, future=True, poolclass=NullPool)
    yield engine


@pytest.fixture(scope="session")
def integration_sync_engine(integration_database_ready: None, integration_database_url: str):
    engine = create_engine(_sync_url_for(integration_database_url), future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def integration_async_session_factory(integration_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=integration_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def integration_sync_session_factory(integration_sync_engine) -> sessionmaker[Session]:
    return sessionmaker(bind=integration_sync_engine, class_=Session, expire_on_commit=False)


def _truncate_public_tables(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT tablename "
                "FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version' "
                "ORDER BY tablename"
            )
        ).all()
        if not rows:
            return
        joined = ", ".join(f'"{row[0]}"' for row in rows)
        session.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
        session.commit()


@pytest.fixture(autouse=True)
def _clean_database(request: pytest.FixtureRequest, integration_sync_session_factory: sessionmaker[Session]):
    if "integration" not in request.keywords:
        yield
        return

    _truncate_public_tables(integration_sync_session_factory)
    yield
    _truncate_public_tables(integration_sync_session_factory)


@pytest.fixture()
def integration_client(integration_async_session_factory: async_sessionmaker[AsyncSession]) -> TestClient:
    from api.main import app

    async def _integration_get_session():
        async with integration_async_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _integration_get_session
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
