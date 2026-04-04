from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import linking
from deps import get_current_user
from services.auth import AuthUser


class _FakeResult:
    def __init__(self, *, scalar_one_or_none=None):
        self._scalar_one_or_none = scalar_one_or_none

    def scalar_one_or_none(self):
        return self._scalar_one_or_none


class _FakeSession:
    def __init__(self, *, objects_by_key: dict[tuple[object, int], object] | None = None, inflight_job=None):
        self._objects_by_key = objects_by_key or {}
        self._inflight_job = inflight_job
        self.commit_calls = 0

    async def get(self, model, object_id: int):
        return self._objects_by_key.get((model, object_id))

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is linking.Job:
            return _FakeResult(scalar_one_or_none=self._inflight_job)
        raise AssertionError(f"Unexpected execute() for entity={entity}")

    async def commit(self):
        self.commit_calls += 1


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(linking.router, prefix="/api")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="admin", is_active=True, roles=("admin",))

    app.dependency_overrides[linking.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_run_linking_returns_202_with_job_links(monkeypatch):
    session = _FakeSession(objects_by_key={(linking.Post, 42): SimpleNamespace(id=42)})
    client = _build_client(session)
    audit_calls = []

    async def _fake_enqueue(_session, *, post_id, source, requested_by_user_id, dedupe_key):
        assert post_id == 42
        assert source == "api.linking.run"
        assert requested_by_user_id == 1
        assert dedupe_key == "build_post_links:42"
        return SimpleNamespace(id=301, type="build_post_links")

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(linking, "enqueue_post_link_job", _fake_enqueue)
    monkeypatch.setattr(linking, "write_audit_log", _fake_write_audit_log)

    response = client.post("/api/linking/run?post_id=42")

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "job_id": 301,
        "job_type": "build_post_links",
        "status_url": "/api/jobs/301",
        "result_url": "/api/jobs/301/result",
    }
    assert session.commit_calls == 1
    assert audit_calls[0]["action"] == "linking.run.queued"


def test_run_linking_reuses_existing_inflight_job_when_duplicate(monkeypatch):
    inflight_job = SimpleNamespace(id=302, type="build_post_links")
    session = _FakeSession(
        objects_by_key={(linking.Post, 42): SimpleNamespace(id=42)},
        inflight_job=inflight_job,
    )
    client = _build_client(session)

    async def _fake_enqueue(*_args, **_kwargs):
        return None

    async def _fake_write_audit_log(*_args, **_kwargs):
        return None

    monkeypatch.setattr(linking, "enqueue_post_link_job", _fake_enqueue)
    monkeypatch.setattr(linking, "write_audit_log", _fake_write_audit_log)

    response = client.post("/api/linking/run?post_id=42")

    assert response.status_code == 202
    assert response.json()["job_id"] == 302
    assert response.json()["job_type"] == "build_post_links"
    assert session.commit_calls == 1


def test_rebuild_events_returns_202_with_job_links(monkeypatch):
    session = _FakeSession()
    client = _build_client(session)
    audit_calls = []
    date_from = datetime(2026, 3, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc)

    async def _fake_enqueue(_session, *, date_from, date_to, source, requested_by_user_id, dedupe_key):
        assert source == "api.events.rebuild"
        assert requested_by_user_id == 1
        assert dedupe_key == f"rebuild_events:{date_from.isoformat()}:{date_to.isoformat()}"
        return SimpleNamespace(id=401, type="rebuild_events")

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(linking, "enqueue_rebuild_events_job", _fake_enqueue)
    monkeypatch.setattr(linking, "write_audit_log", _fake_write_audit_log)

    response = client.post(
        "/api/events/rebuild",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == 401
    assert response.json()["job_type"] == "rebuild_events"
    assert session.commit_calls == 1
    assert audit_calls[0]["action"] == "events.rebuild.queued"


def test_rebuild_processes_returns_202_with_job_links(monkeypatch):
    session = _FakeSession()
    client = _build_client(session)
    audit_calls = []
    date_from = datetime(2026, 3, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc)

    async def _fake_enqueue(_session, *, date_from, date_to, source, requested_by_user_id, dedupe_key):
        assert source == "api.processes.rebuild"
        assert requested_by_user_id == 1
        assert dedupe_key == f"rebuild_processes:{date_from.isoformat()}:{date_to.isoformat()}"
        return SimpleNamespace(id=402, type="rebuild_processes")

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(linking, "enqueue_rebuild_processes_job", _fake_enqueue)
    monkeypatch.setattr(linking, "write_audit_log", _fake_write_audit_log)

    response = client.post(
        "/api/processes/rebuild",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == 402
    assert response.json()["job_type"] == "rebuild_processes"
    assert session.commit_calls == 1
    assert audit_calls[0]["action"] == "processes.rebuild.queued"
