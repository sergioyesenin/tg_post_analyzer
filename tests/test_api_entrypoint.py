import importlib
import sys

import pytest
from fastapi.testclient import TestClient

STRONG_TEST_JWT_SECRET = "A_strong_test_secret_value_2026!XYZ"


def _import_api_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "hash")
    monkeypatch.setenv("DB_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("APP_TZ", "UTC")
    monkeypatch.setenv("AUTH_JWT_SECRET", STRONG_TEST_JWT_SECRET)

    for module_name in ("config", "db.session", "api.main", "man"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("api.main")


def test_api_main_exposes_app_and_registers_routes(monkeypatch: pytest.MonkeyPatch):
    module = _import_api_app(monkeypatch)
    app = module.app

    assert app is not None
    paths = {route.path for route in app.routes}
    assert any(path.startswith("/api/auth") for path in paths)
    assert any(path.startswith("/api/channels") for path in paths)
    assert "/" in paths
    assert "/{full_path:path}" in paths
    assert not any(path.startswith("/web") for path in paths)


def test_frontend_routes_serve_react_spa_and_do_not_shadow_api(monkeypatch: pytest.MonkeyPatch):
    module = _import_api_app(monkeypatch)
    client = TestClient(module.app)

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert 'id="root"' in root_response.text

    spa_response = client.get("/dashboard/posts")
    assert spa_response.status_code == 200
    assert 'id="root"' in spa_response.text

    api_response = client.get("/api/route-that-does-not-exist")
    assert api_response.status_code == 404


def test_legacy_man_entrypoint_reuses_canonical_app(monkeypatch: pytest.MonkeyPatch):
    api_main = _import_api_app(monkeypatch)
    legacy_module = importlib.import_module("man")
    assert legacy_module.app is api_main.app
