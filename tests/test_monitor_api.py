from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import monitor
from deps import get_current_user
from services.auth import AuthUser


class _FirstResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, *, scalar_values: list[object] | None = None, execute_results: list[object] | None = None) -> None:
        self.scalar_values = list(scalar_values or [])
        self.execute_results = list(execute_results or [])
        self.commit_calls = 0

    async def scalar(self, _stmt):
        if not self.scalar_values:
            raise AssertionError("Unexpected scalar() call")
        return self.scalar_values.pop(0)

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("Unexpected execute() call")
        return self.execute_results.pop(0)

    async def commit(self):
        self.commit_calls += 1


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(monitor.router, prefix="/api/monitor")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="admin", is_active=True, roles=("admin",))

    app.dependency_overrides[monitor.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_monitor_summary_is_polling_safe_without_commit() -> None:
    session = _FakeSession(scalar_values=[12, 34])
    client = _build_client(session)

    response = client.get("/api/monitor/summary")

    assert response.status_code == 200
    assert response.json() == {"posts_last_24h": 12, "comments_last_24h": 34}
    assert session.commit_calls == 0


def test_monitor_db_size_is_polling_safe_without_commit() -> None:
    row = SimpleNamespace(db_name="tgpa", bytes=1024, pretty="1 kB")
    session = _FakeSession(execute_results=[_FirstResult(row)])
    client = _build_client(session)

    response = client.get("/api/monitor/db-size")

    assert response.status_code == 200
    assert response.json() == {"database": "tgpa", "bytes": 1024, "pretty": "1 kB"}
    assert session.commit_calls == 0


def test_monitor_full_reuses_scheduler_snapshot_and_skips_commit(monkeypatch) -> None:
    session = _FakeSession()
    client = _build_client(session)
    scheduler_calls: list[dict] = []

    async def _fake_get_all_settings(_session):
        return {"monitor": {}, "retention": {"retention_days": 30}}

    async def _fake_scheduler_snapshot(_session, *, effective_settings):
        scheduler_calls.append(effective_settings)
        return {"status": "ok", "enabled": True}

    async def _fake_health_snapshot(_session, *, effective_settings=None, scheduler=None):
        assert scheduler == {"status": "ok", "enabled": True}
        return {"status": "ok", "dependencies": {}}

    async def _fake_jobs_snapshot(_session):
        return {"by_status": {"pending": 0}}

    async def _fake_pipeline_snapshot(_session, *, retention_days):
        assert retention_days == 30
        return {"runtime": {}}

    async def _fake_activity_snapshot(_session, *, hours):
        assert hours == 24
        return {"posts_last_hours": 1, "comments_last_hours": 2}

    async def _fake_database_snapshot(_session):
        return {"database": "tgpa"}

    monkeypatch.setattr(monitor, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(monitor, "scheduler_snapshot", _fake_scheduler_snapshot)
    monkeypatch.setattr(monitor, "health_snapshot", _fake_health_snapshot)
    monkeypatch.setattr(monitor, "jobs_snapshot", _fake_jobs_snapshot)
    monkeypatch.setattr(monitor, "pipeline_snapshot", _fake_pipeline_snapshot)
    monkeypatch.setattr(monitor, "activity_snapshot", _fake_activity_snapshot)
    monkeypatch.setattr(monitor, "database_snapshot", _fake_database_snapshot)
    monkeypatch.setattr(monitor, "system_snapshot", lambda: {"runtime": {"role": "api"}})
    monkeypatch.setattr(monitor, "evaluate_alerts", lambda **_kwargs: {"status": "ok", "alerts_count": 0, "alerts": []})

    response = client.get("/api/monitor/full")

    assert response.status_code == 200
    assert response.json()["scheduler"] == {"status": "ok", "enabled": True}
    assert len(scheduler_calls) == 1
    assert session.commit_calls == 0


def test_monitor_alerts_is_polling_safe_without_commit(monkeypatch) -> None:
    session = _FakeSession()
    client = _build_client(session)

    async def _fake_get_all_settings(_session):
        return {"monitor": {}, "retention": {"retention_days": 30}}

    async def _fake_health_snapshot(_session, *, effective_settings=None, scheduler=None):
        return {"status": "ok", "dependencies": {}}

    async def _fake_jobs_snapshot(_session):
        return {"by_status": {"pending": 0}}

    async def _fake_pipeline_snapshot(_session, *, retention_days):
        assert retention_days == 30
        return {"runtime": {}}

    monkeypatch.setattr(monitor, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(monitor, "health_snapshot", _fake_health_snapshot)
    monkeypatch.setattr(monitor, "jobs_snapshot", _fake_jobs_snapshot)
    monkeypatch.setattr(monitor, "pipeline_snapshot", _fake_pipeline_snapshot)
    monkeypatch.setattr(monitor, "system_snapshot", lambda: {"runtime": {"role": "api"}})
    monkeypatch.setattr(monitor, "evaluate_alerts", lambda **_kwargs: {"status": "ok", "alerts_count": 0, "alerts": []})

    response = client.get("/api/monitor/alerts")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert session.commit_calls == 0
