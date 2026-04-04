from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from schemas.linking import LinkRunResponse
from services import pipeline_runtime
from services.jobs import JOB_RESULT_KEY, JobType


class _FakeSession:
    def __init__(self, objects_by_key: dict[tuple[object, int], object] | None = None):
        self._objects_by_key = objects_by_key or {}
        self.commit_calls = 0

    async def get(self, model, object_id: int):
        return self._objects_by_key.get((model, object_id))

    async def commit(self):
        self.commit_calls += 1


class _FakeSessionContext:
    def __init__(self, session: _FakeSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_run_link_job_persists_result_and_audit(monkeypatch: pytest.MonkeyPatch):
    db_job = SimpleNamespace(
        id=11,
        type=JobType.BUILD_POST_LINKS,
        payload_json={"post_id": 42, "requested_by_user_id": 7, "source": "api.linking.run"},
    )
    post = SimpleNamespace(id=42)
    session = _FakeSession(
        {
            (pipeline_runtime.Job, 11): db_job,
            (pipeline_runtime.Post, 42): post,
        }
    )
    audit_calls = []
    mark_done_calls = []

    class _FakePipeline:
        async def run_for_post(self, _session, _post):
            return LinkRunResponse(
                post_id=42,
                links_verified=3,
                links_proposed=0,
                links_rejected=2,
                candidates_checked=5,
                verify_checked=0,
                critic_checked=0,
                queued_for_review=0,
            )

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job.id)

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(
        pipeline_runtime.NoLlmLinkingPipeline,
        "build_default",
        classmethod(lambda cls: _FakePipeline()),
    )
    monkeypatch.setattr(pipeline_runtime, "write_audit_log", _fake_write_audit_log)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)

    executed = await pipeline_runtime._run_link_job(job=SimpleNamespace(id=11), worker_id="worker-1")

    assert executed == 1
    assert db_job.payload_json[JOB_RESULT_KEY]["links_verified"] == 3
    assert mark_done_calls == [11]
    assert session.commit_calls == 1
    assert audit_calls[0]["action"] == "linking.run.executed"


@pytest.mark.asyncio
async def test_run_rebuild_events_job_persists_result_and_audit(monkeypatch: pytest.MonkeyPatch):
    date_from = datetime(2026, 3, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 31, tzinfo=timezone.utc)
    db_job = SimpleNamespace(
        id=12,
        type=JobType.REBUILD_EVENTS,
        payload_json={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "requested_by_user_id": 8,
            "source": "api.events.rebuild",
        },
    )
    session = _FakeSession({(pipeline_runtime.Job, 12): db_job})
    audit_calls = []
    mark_done_calls = []

    async def _fake_rebuild_events(_session, *, date_from, date_to, created_by):
        assert created_by == "job-pipeline"
        return 4

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job.id)

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "rebuild_events", _fake_rebuild_events)
    monkeypatch.setattr(pipeline_runtime, "write_audit_log", _fake_write_audit_log)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)

    executed = await pipeline_runtime._run_rebuild_events_job(job=SimpleNamespace(id=12), worker_id="worker-2")

    assert executed == 1
    assert db_job.payload_json[JOB_RESULT_KEY]["rebuilt_events"] == 4
    assert mark_done_calls == [12]
    assert session.commit_calls == 1
    assert audit_calls[0]["action"] == "events.rebuild.executed"


@pytest.mark.asyncio
async def test_run_rebuild_processes_job_persists_result_and_audit(monkeypatch: pytest.MonkeyPatch):
    date_from = datetime(2026, 3, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 31, tzinfo=timezone.utc)
    db_job = SimpleNamespace(
        id=13,
        type=JobType.REBUILD_PROCESSES,
        payload_json={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "requested_by_user_id": 9,
            "source": "api.processes.rebuild",
        },
    )
    session = _FakeSession({(pipeline_runtime.Job, 13): db_job})
    audit_calls = []
    mark_done_calls = []

    async def _fake_rebuild_processes(_session, *, date_from, date_to, created_by):
        assert created_by == "job-pipeline"
        return 6

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job.id)

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "rebuild_processes", _fake_rebuild_processes)
    monkeypatch.setattr(pipeline_runtime, "write_audit_log", _fake_write_audit_log)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)

    executed = await pipeline_runtime._run_rebuild_processes_job(job=SimpleNamespace(id=13), worker_id="worker-3")

    assert executed == 1
    assert db_job.payload_json[JOB_RESULT_KEY]["rebuilt_process_edges"] == 6
    assert mark_done_calls == [13]
    assert session.commit_calls == 1
    assert audit_calls[0]["action"] == "processes.rebuild.executed"

