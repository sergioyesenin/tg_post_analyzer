from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import report_progress
from db.models import Job, User
from services.auth import create_access_token


class _FakeSession:
    def __init__(self, objects_by_key: dict[tuple[object, int], object]):
        self._objects_by_key = objects_by_key

    async def get(self, model, object_id: int, **kwargs):
        return self._objects_by_key.get((model, object_id))

    async def execute(self, stmt):
        report_jobs = [
            obj
            for (model, _), obj in self._objects_by_key.items()
            if model is Job and getattr(obj, "type", None) in report_progress.REPORT_JOB_TYPES
        ]
        report_jobs.sort(
            key=lambda job: (
                getattr(job, "created_at", datetime.min.replace(tzinfo=timezone.utc)),
                getattr(job, "id", 0),
            ),
            reverse=True,
        )
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(
                all=lambda: report_jobs,
            )
        )


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(report_progress.router, prefix="/api/reports/progress")

    async def _fake_get_session():
        yield session

    app.dependency_overrides[report_progress.get_session] = _fake_get_session
    return TestClient(app)


def _build_job(*, job_id: int, status: str, payload: dict, result: dict | None = None, last_error: str | None = None):
    payload_json = dict(payload)
    if result is not None:
        payload_json["_job_result"] = result
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=job_id,
        type="build_post_report",
        status=status,
        payload_json=payload_json,
        last_error=last_error,
        created_at=now,
        updated_at=now,
    )


def _access_token(user_id: int) -> str:
    return create_access_token(user_id=user_id, username=f"user{user_id}", roles=["analyst"])


def test_report_progress_ws_emits_started_event():
    user = SimpleNamespace(id=7, username="analyst", is_active=True)
    job = _build_job(
        job_id=501,
        status="running",
        payload={"post_id": 42, "requested_by_user_id": 7, "source": "api"},
    )
    session = _FakeSession({
        (User, 7): user,
        (Job, 501): job,
    })
    client = _build_client(session)

    with client.websocket_connect(
        f"/api/reports/progress/ws?access_token={_access_token(7)}&request_id=501&entity_type=post&entity_id=42"
    ) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "report_build_started"
    assert event["status"] == "building_report"
    assert event["request_id"] == 501
    assert event["entity_type"] == "post"
    assert event["entity_id"] == 42


def test_report_progress_ws_emits_completed_event():
    user = SimpleNamespace(id=8, username="analyst", is_active=True)
    job = _build_job(
        job_id=601,
        status="done",
        payload={"post_id": 77, "requested_by_user_id": 8, "source": "api"},
        result={"status": "ready", "post_id": 77, "report_id": 999},
    )
    session = _FakeSession({
        (User, 8): user,
        (Job, 601): job,
    })
    client = _build_client(session)

    with client.websocket_connect(
        f"/api/reports/progress/ws?access_token={_access_token(8)}&request_id=601&entity_type=post&entity_id=77"
    ) as websocket:
        event = websocket.receive_json()

    assert event == {
        "type": "report_build_completed",
        "entity_type": "post",
        "entity_id": 77,
        "request_id": 601,
        "status": "completed",
        "timestamp": event["timestamp"],
        "result": {"report_id": 999},
    }


def test_report_progress_ws_treats_limited_report_result_as_completed():
    user = SimpleNamespace(id=18, username="analyst", is_active=True)
    job = _build_job(
        job_id=611,
        status="done",
        payload={"post_id": 79, "requested_by_user_id": 18, "source": "api"},
        result={"status": "limited", "post_id": 79, "report_id": 1001},
    )
    session = _FakeSession({
        (User, 18): user,
        (Job, 611): job,
    })
    client = _build_client(session)

    with client.websocket_connect(
        f"/api/reports/progress/ws?access_token={_access_token(18)}&request_id=611&entity_type=post&entity_id=79"
    ) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "report_build_completed"
    assert event["status"] == "completed"
    assert event["result"] == {"report_id": 1001}


def test_report_progress_ws_emits_failed_event():
    user = SimpleNamespace(id=9, username="analyst", is_active=True)
    job = _build_job(
        job_id=701,
        status="failed",
        payload={"post_id": 88, "requested_by_user_id": 9, "source": "api"},
        result={"status": "failed", "reason": "model_timeout", "message": "Model timed out"},
        last_error="worker timeout",
    )
    session = _FakeSession({
        (User, 9): user,
        (Job, 701): job,
    })
    client = _build_client(session)

    with client.websocket_connect(
        f"/api/reports/progress/ws?access_token={_access_token(9)}&request_id=701&entity_type=post&entity_id=88"
    ) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "report_build_failed"
    assert event["status"] == "failed"
    assert event["error"] == {"code": "model_timeout", "message": "Model timed out"}


def test_report_progress_ws_allows_undefined_request_id_when_entity_binding_is_valid():
    user = SimpleNamespace(id=11, username="analyst", is_active=True)
    job = _build_job(
        job_id=901,
        status="running",
        payload={"post_id": 72, "requested_by_user_id": 11, "source": "api"},
    )
    session = _FakeSession({
        (User, 11): user,
        (Job, 901): job,
    })
    client = _build_client(session)

    with client.websocket_connect(
        f"/api/reports/progress/ws?access_token={_access_token(11)}&request_id=undefined&entity_type=post&entity_id=72"
    ) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "report_build_started"
    assert event["status"] == "building_report"
    assert event["request_id"] == 901
    assert event["entity_type"] == "post"
    assert event["entity_id"] == 72
