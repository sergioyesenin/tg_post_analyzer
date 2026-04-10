from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services import pipeline_runtime


@pytest.mark.asyncio
async def test_run_ai_cycle_does_not_auto_enqueue_report_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_all_settings(_session):
        return {
            "jobs": {
                "job_batch_size": 10,
                "job_worker_concurrency": 1,
                "ai_scheduler_limit": 25,
            },
            "reports": {
                "post_report_delay_hours": 12,
            },
        }

    async def _fake_run_ai_jobs(*, job_batch_size: int, worker_id: str, job_worker_concurrency: int) -> int:
        assert job_batch_size == 10
        assert worker_id == "ai-test-worker"
        assert job_worker_concurrency == 1
        return 3

    async def _unexpected_schedule_due_post_report_jobs(*, min_age_hours: int, limit: int) -> int:
        raise AssertionError(
            f"run_ai_cycle must not auto-enqueue report jobs anymore: min_age_hours={min_age_hours} limit={limit}"
        )

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "run_ai_jobs", _fake_run_ai_jobs)
    monkeypatch.setattr(
        pipeline_runtime,
        "schedule_due_post_report_jobs",
        _unexpected_schedule_due_post_report_jobs,
    )

    queued, executed = await pipeline_runtime.run_ai_cycle(
        worker_id="ai-test-worker",
        job_batch_size_arg=None,
        job_worker_concurrency_arg=None,
        post_report_age_hours_arg=None,
        scheduler_limit_arg=None,
    )

    assert queued == 0
    assert executed == 3


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


def _report_job(*, job_type: str, payload: dict, job_id: int = 1):
    return SimpleNamespace(
        id=job_id,
        type=job_type,
        payload_json=payload,
        attempts=1,
        max_attempts=5,
        status="running",
        last_error=None,
        retry_at=None,
        locked_by="ai-test-worker",
        locked_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_run_ai_jobs_processes_queued_build_post_report(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_session = _FakeSession()
    fetch_session = _FakeSession()
    empty_fetch_session = _FakeSession()
    process_job = _report_job(job_type="build_post_report", payload={"post_id": 42})
    process_session = _FakeSession(job=process_job)
    mark_done_calls: list[object] = []
    fetch_calls = {"count": 0}

    async def _fake_get_all_settings(_session):
        return {
            "jobs": {
                "ai_job_timeout_seconds": 30,
            }
        }

    async def _fake_fetch_and_lock_jobs(_session, *, worker_id: str, limit: int, allowed_types: set[str]):
        assert worker_id == "ai-test-worker"
        assert limit == 1
        assert "build_post_report" in allowed_types
        fetch_calls["count"] += 1
        return [process_job] if fetch_calls["count"] == 1 else []

    async def _fake_build_post_report(session, *, post_id: int, report_project, report_config):
        assert session is process_session
        assert post_id == 42
        assert report_project == "fake-project"
        assert report_config == {"mode": "test"}
        return {"status": pipeline_runtime.reporting_module.REPORT_STATUS_READY}

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job)

    async def _unexpected_mark_related_event_reports_stale(_session, *, post_id: int):
        assert post_id == 42
        return 0

    monkeypatch.setattr(
        pipeline_runtime,
        "AsyncSessionLocal",
        _session_factory(settings_session, fetch_session, process_session, empty_fetch_session),
    )
    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "fetch_and_lock_jobs", _fake_fetch_and_lock_jobs)
    monkeypatch.setattr(pipeline_runtime, "get_report_project", lambda: "fake-project")
    monkeypatch.setattr(pipeline_runtime, "report_config_from_settings", lambda _settings: {"mode": "test"})
    monkeypatch.setattr(pipeline_runtime, "build_post_report", _fake_build_post_report)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)
    monkeypatch.setattr(
        pipeline_runtime,
        "_mark_related_event_reports_stale",
        _unexpected_mark_related_event_reports_stale,
    )

    executed = await pipeline_runtime.run_ai_jobs(
        job_batch_size=10,
        worker_id="ai-test-worker",
        job_worker_concurrency=1,
    )

    assert executed == 1
    assert process_job.payload_json["_job_result"]["status"] == pipeline_runtime.reporting_module.REPORT_STATUS_READY
    assert mark_done_calls == [process_job]
    assert settings_session.commit_calls == 0
    assert fetch_session.commit_calls == 1
    assert process_session.commit_calls == 1
    assert empty_fetch_session.commit_calls == 1


@pytest.mark.asyncio
async def test_run_ai_jobs_keeps_build_post_report_batch_passive(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_session = _FakeSession()
    fetch_session = _FakeSession()
    empty_fetch_session = _FakeSession()
    batch_job = _report_job(
        job_type="build_post_report_batch",
        payload={"filters": {"channel_ids": [1], "limit": 25}},
        job_id=7,
    )
    process_session = _FakeSession(job=batch_job)
    fetch_calls = {"count": 0}

    async def _fake_get_all_settings(_session):
        return {
            "jobs": {
                "ai_job_timeout_seconds": 30,
            }
        }

    async def _fake_fetch_and_lock_jobs(_session, *, worker_id: str, limit: int, allowed_types: set[str]):
        assert worker_id == "ai-test-worker"
        assert limit == 1
        assert "build_post_report_batch" in allowed_types
        fetch_calls["count"] += 1
        return [batch_job] if fetch_calls["count"] == 1 else []

    async def _unexpected_dispatch_post_report_batch(*args, **kwargs):
        raise AssertionError("Passive AI worker must not dispatch batch report jobs")

    monkeypatch.setattr(
        pipeline_runtime,
        "AsyncSessionLocal",
        _session_factory(settings_session, fetch_session, process_session, empty_fetch_session),
    )
    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "fetch_and_lock_jobs", _fake_fetch_and_lock_jobs)
    monkeypatch.setattr(pipeline_runtime, "get_report_project", lambda: "fake-project")
    monkeypatch.setattr(pipeline_runtime, "report_config_from_settings", lambda _settings: {"mode": "test"})
    monkeypatch.setattr(pipeline_runtime, "dispatch_post_report_batch", _unexpected_dispatch_post_report_batch)

    executed = await pipeline_runtime.run_ai_jobs(
        job_batch_size=5,
        worker_id="ai-test-worker",
        job_worker_concurrency=1,
    )

    assert executed == 0
    assert batch_job.status == pipeline_runtime.JOB_STATUS_FAILED
    assert batch_job.last_error == "build_post_report_batch:passive_mode_batch_dispatch_disabled"
    assert batch_job.payload_json["_job_result"] == {
        "status": "failed",
        "reason": "passive_ai_worker_no_batch_dispatch",
        "message": "AI worker passive mode does not expand batch report jobs into build_post_report jobs.",
        "filters": {"channel_ids": [1], "limit": 25},
    }
    assert settings_session.commit_calls == 0
    assert fetch_session.commit_calls == 1
    assert process_session.commit_calls == 1
    assert empty_fetch_session.commit_calls == 1
