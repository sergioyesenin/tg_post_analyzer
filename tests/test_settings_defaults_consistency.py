from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import settings as settings_router
from deps import get_current_user
from services.auth import AuthUser
from services.settings_defaults import CANONICAL_SETTINGS_DEFAULTS, get_canonical_defaults
from services import pipeline_runtime
from services.settings_store import get_all_settings, is_internal_setting_key
from services.settings_validation import SCHEMA_BY_KEY


class _FakeScalars:
    def all(self):
        return []


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def scalars(self):
        if not self._rows:
            return _FakeScalars()
        return type("_Scalars", (), {"all": lambda self_: self._rows})()


class _FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or []

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def test_canonical_defaults_match_validation_schema_defaults():
    for key, schema in SCHEMA_BY_KEY.items():
        assert schema.model_validate({}).model_dump() == CANONICAL_SETTINGS_DEFAULTS[key]


def test_get_all_settings_uses_canonical_defaults_for_empty_store():
    effective = asyncio.run(get_all_settings(_FakeSession()))
    assert effective == get_canonical_defaults()


def test_effective_settings_endpoint_returns_expected_defaults(monkeypatch):
    app = FastAPI()
    app.include_router(settings_router.router, prefix="/api/settings")

    async def _fake_get_session():
        yield object()

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=("admin",))

    async def _fake_get_all_settings(_session):
        return get_canonical_defaults()

    app.dependency_overrides[settings_router.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    monkeypatch.setattr(settings_router, "get_all_settings", _fake_get_all_settings)

    client = TestClient(app)
    response = client.get("/api/settings/effective")

    assert response.status_code == 200
    assert response.json() == get_canonical_defaults()


def test_pipeline_runtime_fallbacks_match_canonical_defaults():
    defaults = CANONICAL_SETTINGS_DEFAULTS

    assert pipeline_runtime.get_telegram_poll_seconds.__kwdefaults__ == {"default": None}
    assert pipeline_runtime.get_ai_poll_seconds.__kwdefaults__ == {"default": None}
    assert defaults["ingest"]["collect_comments_sleep_min_ms"] == 2500
    assert defaults["ingest"]["collect_comments_sleep_max_ms"] == 4500


def test_get_all_settings_ignores_internal_runtime_rows():
    row = type(
        "_Row",
        (),
        {"key": "runtime.scheduler", "value_json": {"status": "running", "heartbeat_at": "2026-03-11T12:00:00+00:00"}},
    )()

    effective = asyncio.run(get_all_settings(_FakeSession(rows=[row])))

    assert "runtime.scheduler" not in effective
    assert is_internal_setting_key("runtime.scheduler") is True
