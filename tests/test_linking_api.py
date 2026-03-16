from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import linking, links
from deps import get_current_user
from services.auth import AuthUser


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return type("_Scalars", (), {"all": lambda self_: list(self._rows)})()


class _FakeSession:
    def __init__(self, *, get_map=None, execute_results=None):
        self.get_map = get_map or {}
        self.execute_results = list(execute_results or [])

    async def get(self, model, key):
        return self.get_map.get((model.__name__, key))

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("Unexpected execute() call")
        return self.execute_results.pop(0)


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(linking.router, prefix="/api")
    app.include_router(links.router, prefix="/api/links")

    async def _fake_get_session():
        yield session

    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=("viewer",))

    app.dependency_overrides[linking.get_session] = _fake_get_session
    app.dependency_overrides[links.get_session] = _fake_get_session
    app.dependency_overrides[get_current_user] = _fake_current_user
    return TestClient(app)


def test_get_process_returns_membership_rows(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    process = SimpleNamespace(
        id=7,
        title="Process",
        status="verified",
        started_at=now,
        ended_at=None,
        confidence=0.88,
        created_by="pipeline",
    )
    membership = SimpleNamespace(
        event_id=101,
        relation_type="update",
        direction="none",
        score=0.91,
        status="verified",
    )
    session = _FakeSession(
        get_map={(linking.Process.__name__, 7): process},
        execute_results=[
            _FakeRowsResult([(membership, "Event 101", now, None, 0.67)]),
            _FakeRowsResult([(101, 501), (101, 502)]),
        ],
    )

    async def _fake_metrics(_session, process_ids):
        assert process_ids == [7]
        return {7: {"comments_count": 12, "involvement": 0.27}}

    monkeypatch.setattr(linking, "load_process_metrics", _fake_metrics)
    client = _build_client(session)

    response = client.get("/api/processes/7")

    assert response.status_code == 200
    assert response.json()["process"]["id"] == 7
    assert response.json()["events"] == [
        {
            "event_id": 101,
            "title": "Event 101",
            "started_at": "2026-03-12T12:00:00Z",
            "ended_at": None,
            "confidence": 0.67,
            "relation_type": "update",
            "direction": "none",
            "score": 0.91,
            "status": "verified",
            "post_ids": [501, 502],
        }
    ]


def test_legacy_links_route_delegates_to_canonical_post_links(monkeypatch):
    post = SimpleNamespace(id=42)
    link = SimpleNamespace(
        id=5,
        src_post_id=42,
        dst_post_id=99,
        link_type="related",
        direction="src_to_dst",
        score=0.77,
        status="verified",
        evidence_json=None,
        model_version=None,
        pipeline_version="no-llm-v1",
        created_at=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 12, 11, 0, tzinfo=timezone.utc),
    )
    session = _FakeSession(
        get_map={(linking.Post.__name__, 42): post},
        execute_results=[_FakeRowsResult([link])],
    )
    client = _build_client(session)

    response = client.get("/api/links/posts/42")

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"] == "</api/posts/42/links>; rel=\"successor-version\""
    assert response.json()["post_id"] == 42
    assert response.json()["links"][0]["dst_post_id"] == 99
