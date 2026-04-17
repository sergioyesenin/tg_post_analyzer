from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.public_report_boundary import sanitize_public_report_json
from api.routers import linking, reports
from deps import get_current_user
from services.auth import AuthUser


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ReportsSession:
    def __init__(self, report):
        self._report = report

    async def execute(self, _stmt):
        return _ScalarOneOrNoneResult(self._report)


class _LinkingSession:
    def __init__(self, *, get_map=None, execute_results=None):
        self._get_map = get_map or {}
        self._execute_results = list(execute_results or [])

    async def get(self, model, key):
        return self._get_map.get((model.__name__, key))

    async def execute(self, _stmt):
        if not self._execute_results:
            raise AssertionError("Unexpected execute() call")
        return self._execute_results.pop(0)

    async def scalar(self, _stmt):
        return None


def _override_user(app: FastAPI) -> None:
    async def _fake_current_user():
        return AuthUser(id=1, username="tester", is_active=True, roles=("viewer",))

    app.dependency_overrides[get_current_user] = _fake_current_user


def test_sanitize_public_report_json_strips_only_multi_agent_meta():
    payload = {
        "status": "ready",
        "summary": "summary",
        "topics": [{"name": "topic"}],
        "model_info": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "latency_ms": 120,
            "fallback_used": False,
        },
        "meta": {
            "generated_at": "2026-04-13T10:00:00Z",
            "multi_agent": {"trace_id": "abc", "steps": [{"agent": "critic"}]},
        },
    }

    sanitized = sanitize_public_report_json(payload)

    assert sanitized == {
        "status": "ready",
        "summary": "summary",
        "topics": [{"name": "topic"}],
        "model_info": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "latency_ms": 120,
            "fallback_used": False,
        },
        "meta": {
            "generated_at": "2026-04-13T10:00:00Z",
        },
    }
    assert payload["meta"]["multi_agent"]["trace_id"] == "abc"


def test_sanitize_public_report_json_keeps_non_internal_meta_and_top_level_model_info() -> None:
    payload = {
        "status": "limited",
        "summary": "summary",
        "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
        "meta": {
            "generated_at": "2026-04-13T10:00:00Z",
            "refresh_attempt": {"source": "refresh_comments"},
            "multi_agent": {"trace_id": "internal"},
        },
    }

    sanitized = sanitize_public_report_json(payload)

    assert sanitized == {
        "status": "limited",
        "summary": "summary",
        "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
        "meta": {
            "generated_at": "2026-04-13T10:00:00Z",
            "refresh_attempt": {"source": "refresh_comments"},
        },
    }


def test_get_report_omits_multi_agent_meta_from_public_payload():
    app = FastAPI()
    app.include_router(reports.router, prefix="/api/reports")
    _override_user(app)

    report = SimpleNamespace(
        id=11,
        post_id=42,
        status="ready",
        content="report text",
        report_json={
            "status": "ready",
            "summary": "public summary",
            "topics": [{"name": "alpha"}],
            "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
            "meta": {
                "generated_at": "2026-04-13T10:00:00Z",
                "multi_agent": {"trace_id": "internal"},
            },
        },
        created_at=datetime(2026, 4, 13, 10, 0, tzinfo=timezone.utc),
    )

    async def _fake_get_session():
        yield _ReportsSession(report)

    app.dependency_overrides[reports.get_session] = _fake_get_session
    client = TestClient(app)

    response = client.get("/api/reports/post/42")

    assert response.status_code == 200
    assert response.json()["report_json"] == {
        "status": "ready",
        "summary": "public summary",
        "topics": [{"name": "alpha"}],
        "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
        "meta": {"generated_at": "2026-04-13T10:00:00Z"},
    }


def test_event_and_process_details_omit_internal_trace_payloads(monkeypatch):
    app = FastAPI()
    app.include_router(linking.router, prefix="/api")
    _override_user(app)

    now = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
    event = SimpleNamespace(
        id=7,
        title="Event",
        status="verified",
        started_at=now,
        ended_at=None,
        confidence=0.9,
        created_by="pipeline",
    )
    process = SimpleNamespace(
        id=8,
        title="Process",
        status="verified",
        started_at=now,
        ended_at=None,
        confidence=0.8,
        created_by="pipeline",
    )
    event_report = SimpleNamespace(
        id=71,
        version=3,
        report_text="event report",
        report_json={
            "status": "ready",
            "summary": "event summary",
            "cross_post_topics": [{"name": "incident"}],
            "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
            "meta": {"multi_agent": {"trace_id": "event-internal"}},
        },
        created_at=now,
    )
    process_report = SimpleNamespace(
        id=81,
        version=2,
        report_text="process report",
        report_json={
            "status": "ready",
            "summary": "process summary",
            "stage_analysis": [{"main_topics": ["escalation"]}],
            "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
            "meta": {"multi_agent": {"trace_id": "process-internal"}},
        },
        created_at=now,
    )

    async def _fake_event_metrics(_session, event_ids):
        assert event_ids == [7]
        return {7: {"comments_count": 4, "involvement": 0.2}}

    async def _fake_process_metrics(_session, process_ids):
        assert process_ids == [8]
        return {8: {"comments_count": 6, "involvement": 0.4}}

    monkeypatch.setattr(linking, "load_event_metrics", _fake_event_metrics)
    monkeypatch.setattr(linking, "load_process_metrics", _fake_process_metrics)

    event_session = _LinkingSession(
        get_map={(linking.Event.__name__, 7): event},
        execute_results=[
            _RowsResult([(101,), (102,)]),
            _RowsResult([("channel_a",), ("channel_b",)]),
            _ScalarOneOrNoneResult(event_report),
        ],
    )
    process_session = _LinkingSession(
        get_map={(linking.Process.__name__, 8): process},
        execute_results=[
            _RowsResult([]),
            _ScalarOneOrNoneResult(process_report),
        ],
    )

    async def _fake_get_event_session():
        yield event_session

    async def _fake_get_process_session():
        yield process_session

    client = TestClient(app)

    app.dependency_overrides[linking.get_session] = _fake_get_event_session
    event_response = client.get("/api/events/7")
    assert event_response.status_code == 200
    assert event_response.json()["latest_report"]["report_json"] == {
        "status": "ready",
        "summary": "event summary",
        "cross_post_topics": [{"name": "incident"}],
        "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
    }

    app.dependency_overrides[linking.get_session] = _fake_get_process_session
    process_response = client.get("/api/processes/8")
    assert process_response.status_code == 200
    assert process_response.json()["latest_report"]["report_json"] == {
        "status": "ready",
        "summary": "process summary",
        "stage_analysis": [{"main_topics": ["escalation"]}],
        "model_info": {"provider": "openai", "model": "gpt-4o-mini"},
    }
