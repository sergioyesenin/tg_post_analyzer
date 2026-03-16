from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import dashboard
from deps import get_current_user
from services.auth import AuthUser


class _FakeSession:
    pass


def _build_client(session: _FakeSession, *, roles: tuple[str, ...]) -> TestClient:
    app = FastAPI()
    app.include_router(dashboard.router, prefix="/api/dashboard")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=roles)

    app.dependency_overrides[dashboard.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_dashboard_posts_allows_viewer(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    client = _build_client(_FakeSession(), roles=("viewer",))

    async def _fake_limit(_session, limit):
        return 20

    async def _fake_build(*args, **kwargs):
        assert kwargs["comments_refresh_available"] is False
        return {
            "mode": "posts",
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "partial": False,
            "warnings": [],
            "filters_applied": {
                "date_from": now.isoformat().replace("+00:00", "Z"),
                "date_to": now.isoformat().replace("+00:00", "Z"),
                "limit": 20,
                "channel_ids": [],
                "categories": [],
                "min_comments": None,
                "report_status": [],
                "sort_by": "comments_count",
                "sort_order": "desc",
            },
            "summary": {
                "posts_count": 0,
                "total_comments": 0,
                "avg_involvement": None,
                "channels_count": 0,
                "reports_ready": 0,
                "reports_missing": 0,
                "reports_pending": 0,
                "reports_failed": 0,
            },
            "items": [],
            "meta": {"sort": {"by": "comments_count", "order": "desc"}, "supported_sorts": ["comments_count"]},
        }

    monkeypatch.setattr(dashboard, "_resolve_limit", _fake_limit)
    monkeypatch.setattr(dashboard, "build_posts_dashboard", _fake_build)

    iso_now = now.isoformat().replace("+00:00", "Z")
    response = client.get(f"/api/dashboard/posts?date_from={iso_now}&date_to={iso_now}")

    assert response.status_code == 200
    assert response.json()["mode"] == "posts"


def test_dashboard_process_graph_returns_404_when_missing(monkeypatch):
    client = _build_client(_FakeSession(), roles=("analyst",))

    async def _fake_build(_session, *, process_id: int):
        assert process_id == 77
        return None

    monkeypatch.setattr(dashboard, "build_process_graph", _fake_build)

    response = client.get("/api/dashboard/processes/77/graph")

    assert response.status_code == 404
    assert response.json() == {"detail": "Process not found"}


def test_dashboard_forbids_unknown_role(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    client = _build_client(_FakeSession(), roles=("guest",))

    async def _fake_limit(_session, limit):
        return 20

    monkeypatch.setattr(dashboard, "_resolve_limit", _fake_limit)

    iso_now = now.isoformat().replace("+00:00", "Z")
    response = client.get(f"/api/dashboard/posts?date_from={iso_now}&date_to={iso_now}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_dashboard_posts_returns_422_for_invalid_channel_ids(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    client = _build_client(_FakeSession(), roles=("viewer",))

    async def _fake_limit(_session, limit):
        return 20

    async def _unexpected_build(*args, **kwargs):
        raise AssertionError("build_posts_dashboard should not run for invalid query params")

    monkeypatch.setattr(dashboard, "_resolve_limit", _fake_limit)
    monkeypatch.setattr(dashboard, "build_posts_dashboard", _unexpected_build)

    iso_now = now.isoformat().replace("+00:00", "Z")
    response = client.get(f"/api/dashboard/posts?date_from={iso_now}&date_to={iso_now}&channel_ids=1,abc")

    assert response.status_code == 422


def test_dashboard_events_returns_422_for_invalid_channel_ids(monkeypatch):
    client = _build_client(_FakeSession(), roles=("viewer",))

    async def _fake_limit(_session, limit):
        return 20

    async def _unexpected_build(*args, **kwargs):
        raise AssertionError("build_events_dashboard should not run for invalid query params")

    monkeypatch.setattr(dashboard, "_resolve_limit", _fake_limit)
    monkeypatch.setattr(dashboard, "build_events_dashboard", _unexpected_build)

    response = client.get("/api/dashboard/events?channel_ids=abc")

    assert response.status_code == 422
