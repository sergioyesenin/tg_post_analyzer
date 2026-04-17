from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import reports
from deps import get_current_user
from services.auth import AuthUser


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _TraceSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("Unexpected execute() call")
        return self._results.pop(0)


def _build_client(*, user_roles: tuple[str, ...], session: _TraceSession) -> TestClient:
    app = FastAPI()
    app.include_router(reports.router, prefix="/api/reports")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=user_roles)

    app.dependency_overrides[reports.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_get_post_trace_allows_admin_and_returns_multi_agent_trace() -> None:
    report = SimpleNamespace(
        id=11,
        post_id=42,
        status="ready",
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        report_json={
            "status": "ready",
            "meta": {
                "multi_agent": {
                    "final_status": "ready",
                    "stages": {"context": {"status": "completed", "run_count": 1}},
                    "orchestration": {"sequence": ["context", "routing", "expert", "public_opinion", "synthesis"]},
                }
            },
        },
    )
    client = _build_client(user_roles=("admin",), session=_TraceSession([_ScalarOneOrNoneResult(report)]))

    response = client.get("/api/reports/post/42/trace")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "post"
    assert body["entity_id"] == 42
    assert body["report_id"] == 11
    assert body["trace"]["final_status"] == "ready"


def test_get_event_trace_allows_analyst_and_returns_latest_trace() -> None:
    report = SimpleNamespace(
        id=21,
        event_id=7,
        version=3,
        created_at=datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
        report_json={
            "status": "limited",
            "meta": {
                "multi_agent": {
                    "final_status": "limited",
                    "stages": {"reviewer": {"decision": "downgrade"}},
                }
            },
        },
    )
    client = _build_client(user_roles=("analyst",), session=_TraceSession([_ScalarOneOrNoneResult(report)]))

    response = client.get("/api/reports/events/7/trace")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "event"
    assert body["entity_id"] == 7
    assert body["version"] == 3
    assert body["status"] == "limited"
    assert body["trace"]["final_status"] == "limited"


def test_trace_endpoints_forbid_viewer() -> None:
    client = _build_client(user_roles=("viewer",), session=_TraceSession([]))

    post_response = client.get("/api/reports/post/42/trace")
    event_response = client.get("/api/reports/events/7/trace")

    assert post_response.status_code == 403
    assert event_response.status_code == 403


def test_trace_endpoints_return_404_when_trace_absent() -> None:
    post_report = SimpleNamespace(
        id=11,
        post_id=42,
        status="ready",
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        report_json={"status": "ready", "meta": {"generated_at": "2026-04-15T12:00:00Z"}},
    )
    event_report = SimpleNamespace(
        id=21,
        event_id=7,
        version=1,
        created_at=datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
        report_json={"status": "ready"},
    )
    client = _build_client(
        user_roles=("admin",),
        session=_TraceSession([
            _ScalarOneOrNoneResult(post_report),
            _ScalarOneOrNoneResult(event_report),
        ]),
    )

    post_response = client.get("/api/reports/post/42/trace")
    event_response = client.get("/api/reports/events/7/trace")

    assert post_response.status_code == 404
    assert post_response.json()["detail"] == "Trace not found"
    assert event_response.status_code == 404
    assert event_response.json()["detail"] == "Trace not found"


def test_viewer_can_read_public_report_but_cannot_read_trace() -> None:
    report = SimpleNamespace(
        id=31,
        post_id=42,
        status="ready",
        content="public report text",
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        report_json={
            "status": "ready",
            "summary": "public summary",
            "meta": {
                "generated_at": "2026-04-15T12:00:00Z",
                "multi_agent": {"trace_id": "internal-only"},
            },
        },
    )
    client = _build_client(
        user_roles=("viewer",),
        session=_TraceSession([
            _ScalarOneOrNoneResult(report),
        ]),
    )

    public_response = client.get("/api/reports/post/42")
    trace_response = client.get("/api/reports/post/42/trace")

    assert public_response.status_code == 200
    public_json = public_response.json()
    assert public_json["report_json"]["meta"] == {"generated_at": "2026-04-15T12:00:00Z"}
    assert "multi_agent" not in public_json["report_json"]["meta"]
    assert trace_response.status_code == 403


def test_analyst_gets_trace_but_public_endpoint_stays_sanitized() -> None:
    report = SimpleNamespace(
        id=41,
        post_id=77,
        status="limited",
        content="report text",
        created_at=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
        report_json={
            "status": "limited",
            "summary": "summary",
            "meta": {
                "generated_at": "2026-04-15T14:00:00Z",
                "multi_agent": {
                    "final_status": "limited",
                    "stages": {"reviewer": {"decision": "accept_with_limitations"}},
                },
            },
        },
    )
    client = _build_client(
        user_roles=("analyst",),
        session=_TraceSession([
            _ScalarOneOrNoneResult(report),
            _ScalarOneOrNoneResult(report),
        ]),
    )

    public_response = client.get("/api/reports/post/77")
    trace_response = client.get("/api/reports/post/77/trace")

    assert public_response.status_code == 200
    public_json = public_response.json()
    assert public_json["report_json"]["meta"] == {"generated_at": "2026-04-15T14:00:00Z"}
    assert "multi_agent" not in public_json["report_json"]["meta"]

    assert trace_response.status_code == 200
    trace_json = trace_response.json()
    assert trace_json["entity_type"] == "post"
    assert trace_json["entity_id"] == 77
    assert trace_json["trace"]["final_status"] == "limited"
