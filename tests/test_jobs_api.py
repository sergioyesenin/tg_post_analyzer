from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import jobs as jobs_router
from deps import get_current_user
from services.auth import AuthUser


class _FakeSession:
    def __init__(self, jobs_by_id: dict[int, object]):
        self._jobs_by_id = jobs_by_id

    async def get(self, model, job_id: int):
        return self._jobs_by_id.get(job_id)


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(jobs_router.router, prefix="/api/jobs")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=("viewer",))

    app.dependency_overrides[jobs_router.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_job_status_returns_serialized_job():
    now = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=7,
        type="build_post_report",
        status="running",
        priority=1,
        run_at=now,
        retry_at=None,
        attempts=1,
        max_attempts=5,
        locked_by="worker-1",
        locked_at=now,
        heartbeat_at=now,
        last_error=None,
        created_at=now,
        updated_at=now,
        payload_json={},
    )
    client = _build_client(_FakeSession({7: job}))

    response = client.get("/api/jobs/7")

    assert response.status_code == 200
    assert response.json()["id"] == 7
    assert response.json()["status"] == "running"
    assert response.json()["result_url"] == "/api/jobs/7/result"


def test_job_result_returns_not_ready_payload_for_pending_job():
    now = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=8,
        type="refresh_comments",
        status="pending",
        priority=1,
        run_at=now,
        retry_at=None,
        attempts=0,
        max_attempts=5,
        locked_by=None,
        locked_at=None,
        heartbeat_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        payload_json={},
    )
    client = _build_client(_FakeSession({8: job}))

    response = client.get("/api/jobs/8/result")

    assert response.status_code == 200
    assert response.json() == {
        "status": "pending",
        "job_id": 8,
        "ready": False,
        "result": None,
    }


def test_job_result_returns_stored_result_for_done_job():
    now = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=9,
        type="build_post_report",
        status="done",
        priority=1,
        run_at=now,
        retry_at=None,
        attempts=1,
        max_attempts=5,
        locked_by=None,
        locked_at=None,
        heartbeat_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        payload_json={"_job_result": {"status": "ready", "report_id": 33}},
    )
    client = _build_client(_FakeSession({9: job}))

    response = client.get("/api/jobs/9/result")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "report_id": 33}


def test_job_result_returns_failed_payload_with_error():
    now = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id=10,
        type="build_event_report",
        status="failed",
        priority=1,
        run_at=now,
        retry_at=None,
        attempts=5,
        max_attempts=5,
        locked_by=None,
        locked_at=None,
        heartbeat_at=None,
        last_error="worker_failed",
        created_at=now,
        updated_at=now,
        payload_json={},
    )
    client = _build_client(_FakeSession({10: job}))

    response = client.get("/api/jobs/10/result")

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "job_id": 10,
        "error": "worker_failed",
    }
