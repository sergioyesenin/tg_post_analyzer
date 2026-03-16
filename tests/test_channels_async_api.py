from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import channels
from db.models import Job
from deps import get_current_user
from services.auth import AuthUser


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, *, inflight_jobs=None):
        self.inflight_jobs = inflight_jobs or []
        self.commit_calls = 0

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is Job:
            return _FakeResult(rows=self.inflight_jobs)
        raise AssertionError(f"Unexpected entity in statement: {entity}")

    async def commit(self):
        self.commit_calls += 1


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(channels.router, prefix="/api/channels")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="admin", is_active=True, roles=("admin",))

    app.dependency_overrides[channels.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_add_channel_enqueues_async_job(monkeypatch):
    session = _FakeSession()
    client = _build_client(session)
    audit_calls = []

    async def _fake_enqueue_job(_session, *, job_type, payload, priority, max_attempts):
        assert job_type == "add_channel"
        assert payload["username"] == "new_channel"
        assert payload["requested_by_user_id"] == 1
        assert priority == 5
        assert max_attempts == 3
        return SimpleNamespace(id=501, type=job_type)

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(channels, "enqueue_job", _fake_enqueue_job)
    monkeypatch.setattr(channels, "write_audit_log", _fake_write_audit_log)

    response = client.post("/api/channels/add", json={"username": "@new_channel"})

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "job_id": 501,
        "job_type": "add_channel",
        "status_url": "/api/jobs/501",
        "result_url": "/api/jobs/501/result",
    }
    assert session.commit_calls == 1
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "channels.add.queued"


def test_add_channel_reuses_existing_inflight_job(monkeypatch):
    inflight_job = SimpleNamespace(
        id=777,
        type="add_channel",
        status="pending",
        created_at=None,
        payload_json={"username": "new_channel"},
    )
    session = _FakeSession(inflight_jobs=[inflight_job])
    client = _build_client(session)

    async def _fail_enqueue_job(*_args, **_kwargs):
        raise AssertionError("enqueue_job should not be called when inflight job exists")

    monkeypatch.setattr(channels, "enqueue_job", _fail_enqueue_job)

    response = client.post("/api/channels/add", json={"username": "https://t.me/new_channel"})

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "job_id": 777,
        "job_type": "add_channel",
        "status_url": "/api/jobs/777",
        "result_url": "/api/jobs/777/result",
    }
    assert session.commit_calls == 0
