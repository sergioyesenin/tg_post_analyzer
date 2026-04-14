from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import reports
from deps import get_current_user
from services.auth import AuthUser


class _FakeSession:
    def __init__(self, objects_by_key: dict[tuple[object, int], object]):
        self._objects_by_key = objects_by_key
        self.commit_calls = 0

    async def get(self, model, object_id: int):
        return self._objects_by_key.get((model, object_id))

    async def commit(self):
        self.commit_calls += 1


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(reports.router, prefix="/api/reports")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=("analyst",))

    app.dependency_overrides[reports.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_update_post_report_returns_202_with_job_links(monkeypatch):
    session = _FakeSession({(reports.Post, 42): SimpleNamespace(id=42)})
    client = _build_client(session)

    async def _fake_enqueue(_session, *, post_id: int, source: str, requested_by_user_id: int, dedupe_key: str):
        assert post_id == 42
        assert source == "api"
        assert requested_by_user_id == 1
        assert dedupe_key == "post:42"
        return SimpleNamespace(id=101, type="build_post_report")

    async def _fake_no_duplicate(*args, **kwargs):
        return None

    monkeypatch.setattr(reports, "enqueue_post_report_job", _fake_enqueue)
    monkeypatch.setattr(reports, "find_blocking_report_duplicate", _fake_no_duplicate)

    response = client.post("/api/reports/post/42/update")

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "job_id": 101,
        "job_type": "build_post_report",
        "status_url": "/api/jobs/101",
        "result_url": "/api/jobs/101/result",
    }
    assert session.commit_calls == 1


def test_update_event_report_returns_202_with_job_links(monkeypatch):
    session = _FakeSession({(reports.Event, 5): SimpleNamespace(id=5)})
    client = _build_client(session)

    async def _fake_enqueue(_session, *, event_id: int, source: str, requested_by_user_id: int, dedupe_key: str):
        assert event_id == 5
        assert source == "api"
        assert requested_by_user_id == 1
        assert dedupe_key == "event:5"
        return SimpleNamespace(id=102, type="build_event_report")

    async def _fake_no_duplicate(*args, **kwargs):
        return None

    monkeypatch.setattr(reports, "enqueue_event_report_job", _fake_enqueue)
    monkeypatch.setattr(reports, "find_blocking_report_duplicate", _fake_no_duplicate)

    response = client.post("/api/reports/events/5/update")

    assert response.status_code == 202
    assert response.json()["job_id"] == 102
    assert response.json()["job_type"] == "build_event_report"


def test_update_process_report_returns_202_with_job_links(monkeypatch):
    session = _FakeSession({(reports.Process, 6): SimpleNamespace(id=6)})
    client = _build_client(session)

    async def _fake_enqueue(_session, *, process_id: int, source: str, requested_by_user_id: int, dedupe_key: str):
        assert process_id == 6
        assert source == "api"
        assert requested_by_user_id == 1
        assert dedupe_key == "process:6"
        return SimpleNamespace(id=103, type="build_process_report")

    async def _fake_no_duplicate(*args, **kwargs):
        return None

    monkeypatch.setattr(reports, "enqueue_process_report_job", _fake_enqueue)
    monkeypatch.setattr(reports, "find_blocking_report_duplicate", _fake_no_duplicate)

    response = client.post("/api/reports/processes/6/update")

    assert response.status_code == 202
    assert response.json()["job_id"] == 103
    assert response.json()["job_type"] == "build_process_report"


def test_generate_post_reports_by_filter_returns_202_batch_job(monkeypatch):
    session = _FakeSession({})
    client = _build_client(session)

    async def _fake_enqueue(_session, *, filters: dict, source: str):
        assert source == "api"
        assert filters == {
            "channel_ids": [1, 3],
            "categories": ["regional", "incident"],
            "date_from": None,
            "date_to": None,
            "min_comments": 5,
            "limit": 25,
        }
        return SimpleNamespace(id=104, type="build_post_report_batch")

    monkeypatch.setattr(reports, "enqueue_post_report_batch_job", _fake_enqueue)

    response = client.post(
        "/api/reports/posts/generate-by-filter?channel_ids=1,3&categories=regional,incident&min_comments=5&limit=25"
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "job_id": 104,
        "job_type": "build_post_report_batch",
        "status_url": "/api/jobs/104",
        "result_url": "/api/jobs/104/result",
        "batch": {
            "limit": 25,
            "channel_ids": [1, 3],
            "categories": ["regional", "incident"],
            "date_from": None,
            "date_to": None,
            "min_comments": 5,
        },
    }
    assert session.commit_calls == 1


def test_list_post_reports_returns_422_for_invalid_channel_ids() -> None:
    session = _FakeSession({})
    client = _build_client(session)

    response = client.get("/api/reports/posts/list?channel_ids=7,nope")

    assert response.status_code == 422


def test_generate_post_reports_by_filter_returns_422_for_invalid_channel_ids(monkeypatch):
    session = _FakeSession({})
    client = _build_client(session)

    async def _unexpected_enqueue(*args, **kwargs):
        raise AssertionError("enqueue_post_report_batch_job should not run for invalid query params")

    monkeypatch.setattr(reports, "enqueue_post_report_batch_job", _unexpected_enqueue)

    response = client.post("/api/reports/posts/generate-by-filter?channel_ids=1,boom&limit=25")

    assert response.status_code == 422
