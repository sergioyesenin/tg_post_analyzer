import importlib
import sys

import pytest

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


def test_legacy_man_entrypoint_reuses_canonical_app(monkeypatch: pytest.MonkeyPatch):
    api_main = _import_api_app(monkeypatch)
    legacy_module = importlib.import_module("man")
    assert legacy_module.app is api_main.app
