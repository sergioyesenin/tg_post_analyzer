from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services import pipeline_runtime
from services.jobs import JobType


class _FakeSession:
    def __init__(self, job=None):
        self.job = job
        self.commit_calls = 0
        self.rollback_calls = 0

    async def get(self, model, job_id: int):
        del model
        if self.job is not None and self.job.id == job_id:
            return self.job
        return None

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _session_factory(*sessions):
    queue = list(sessions)

    def _factory():
        if not queue:
            raise AssertionError("Unexpected AsyncSessionLocal() call")
        return _FakeSessionContext(queue.pop(0))

    return _factory


def _report_job(*, job_type: str, payload: dict, attempts: int = 1, max_attempts: int = 5, job_id: int = 1):
    return SimpleNamespace(
        id=job_id,
        type=job_type,
        payload_json=payload,
        attempts=attempts,
        max_attempts=max_attempts,
        status="running",
        last_error=None,
        retry_at=None,
        locked_by="ai-test-worker",
        locked_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_enqueue_ai_job_dependencies_skips_active_refresh_job(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_has_active_dependency_job(_session, *, job_type: str, payload_key: str, entity_id: int) -> bool:
        assert job_type == JobType.REFRESH_COMMENTS
        assert payload_key == "post_id"
        assert entity_id == 42
        return True

    async def _unexpected_enqueue_comment_refresh_job(*args, **kwargs):
        raise AssertionError("Active refresh dependency must not be enqueued again")

    monkeypatch.setattr(pipeline_runtime, "_has_active_dependency_job", _fake_has_active_dependency_job)
    monkeypatch.setattr(pipeline_runtime, "enqueue_comment_refresh_job", _unexpected_enqueue_comment_refresh_job)

    result = await pipeline_runtime._enqueue_ai_job_dependencies(
        object(),
        parent_job=SimpleNamespace(id=1, type=JobType.BUILD_POST_REPORT),
        dependencies=[{"job_type": JobType.REFRESH_COMMENTS, "post_id": 42, "reason": "waiting_refresh_post_data"}],
    )

    assert result == {"requested": 1, "enqueued": 0, "already_active": 1}


@pytest.mark.asyncio
async def test_run_ai_jobs_enqueues_dependencies_before_requeue(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_session = _FakeSession()
    fetch_session = _FakeSession()
    process_job = _report_job(job_type=JobType.BUILD_EVENT_REPORT, payload={"event_id": 10}, attempts=1, max_attempts=5)
    process_session = _FakeSession(job=process_job)
    empty_fetch_session = _FakeSession()
    fetch_calls = {"count": 0}
    requeue_calls: list[tuple[object, str]] = []

    async def _fake_get_all_settings(_session):
        return {"jobs": {"ai_job_timeout_seconds": 30}}

    async def _fake_fetch_and_lock_jobs(_session, *, worker_id: str, limit: int, allowed_types: set[str]):
        assert worker_id == "ai-test-worker"
        assert limit == 1
        fetch_calls["count"] += 1
        return [process_job] if fetch_calls["count"] == 1 else []

    async def _fake_build_event_report_draft(_session, *, event_id: int):
        assert event_id == 10
        return {
            "status": pipeline_runtime.REPORT_STATUS_DEFERRED,
            "reason": "waiting_post_reports",
            "dependencies": [{"job_type": JobType.BUILD_POST_REPORT, "post_id": 77, "reason": "waiting_post_reports"}],
        }

    async def _fake_enqueue_ai_job_dependencies(_session, *, parent_job, dependencies: list[dict]):
        assert parent_job is process_job
        assert dependencies == [{"job_type": JobType.BUILD_POST_REPORT, "post_id": 77, "reason": "waiting_post_reports"}]
        return {"requested": 1, "enqueued": 1, "already_active": 0}

    async def _fake_requeue_job(_session, *, job, retry_at, error: str | None = None):
        assert job is process_job
        assert retry_at is not None
        requeue_calls.append((job, str(error)))

    monkeypatch.setattr(
        pipeline_runtime,
        "AsyncSessionLocal",
        _session_factory(settings_session, fetch_session, process_session, empty_fetch_session),
    )
    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "fetch_and_lock_jobs", _fake_fetch_and_lock_jobs)
    monkeypatch.setattr(pipeline_runtime, "report_config_from_settings", lambda _settings: {"mode": "test"})
    monkeypatch.setattr(pipeline_runtime, "build_event_report_draft", _fake_build_event_report_draft)
    monkeypatch.setattr(pipeline_runtime, "_enqueue_ai_job_dependencies", _fake_enqueue_ai_job_dependencies)
    monkeypatch.setattr(pipeline_runtime, "requeue_job", _fake_requeue_job)

    executed = await pipeline_runtime.run_ai_jobs(
        job_batch_size=5,
        worker_id="ai-test-worker",
        job_worker_concurrency=1,
    )

    assert executed == 0
    assert requeue_calls == [(process_job, f"{JobType.BUILD_EVENT_REPORT}:waiting_dependencies")]
    assert process_job.payload_json["_job_result"]["dependency_enqueue"] == {"requested": 1, "enqueued": 1, "already_active": 0}


@pytest.mark.asyncio
async def test_run_ai_jobs_fails_deferred_parent_when_retry_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_session = _FakeSession()
    fetch_session = _FakeSession()
    process_job = _report_job(job_type=JobType.BUILD_PROCESS_REPORT, payload={"process_id": 20}, attempts=5, max_attempts=5)
    process_session = _FakeSession(job=process_job)
    empty_fetch_session = _FakeSession()
    fetch_calls = {"count": 0}
    mark_failed_calls: list[str] = []

    async def _fake_get_all_settings(_session):
        return {"jobs": {"ai_job_timeout_seconds": 30}}

    async def _fake_fetch_and_lock_jobs(_session, *, worker_id: str, limit: int, allowed_types: set[str]):
        assert worker_id == "ai-test-worker"
        assert limit == 1
        fetch_calls["count"] += 1
        return [process_job] if fetch_calls["count"] == 1 else []

    async def _fake_build_process_report_draft(_session, *, process_id: int):
        assert process_id == 20
        return {
            "status": pipeline_runtime.REPORT_STATUS_DEFERRED,
            "reason": "blocked_event_reports",
            "dependencies": [],
        }

    async def _fake_enqueue_ai_job_dependencies(_session, *, parent_job, dependencies: list[dict]):
        assert parent_job is process_job
        assert dependencies == []
        return {"requested": 0, "enqueued": 0, "already_active": 0}

    async def _unexpected_requeue_job(*args, **kwargs):
        raise AssertionError("Exhausted deferred parent must not be requeued again")

    async def _fake_mark_job_failed(_session, *, job, error: str, retry_base_seconds: int = 30, retry_max_seconds: int = 3600):
        assert job is process_job
        mark_failed_calls.append(error)

    monkeypatch.setattr(
        pipeline_runtime,
        "AsyncSessionLocal",
        _session_factory(settings_session, fetch_session, process_session, empty_fetch_session),
    )
    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "fetch_and_lock_jobs", _fake_fetch_and_lock_jobs)
    monkeypatch.setattr(pipeline_runtime, "report_config_from_settings", lambda _settings: {"mode": "test"})
    monkeypatch.setattr(pipeline_runtime, "build_process_report_draft", _fake_build_process_report_draft)
    monkeypatch.setattr(pipeline_runtime, "_enqueue_ai_job_dependencies", _fake_enqueue_ai_job_dependencies)
    monkeypatch.setattr(pipeline_runtime, "requeue_job", _unexpected_requeue_job)
    monkeypatch.setattr(pipeline_runtime, "mark_job_failed", _fake_mark_job_failed)

    executed = await pipeline_runtime.run_ai_jobs(
        job_batch_size=5,
        worker_id="ai-test-worker",
        job_worker_concurrency=1,
    )

    assert executed == 0
    assert mark_failed_calls == [f"{JobType.BUILD_PROCESS_REPORT}:waiting_dependencies:blocked_event_reports"]
    assert process_job.payload_json["_job_result"]["dependency_enqueue"] == {"requested": 0, "enqueued": 0, "already_active": 0}
