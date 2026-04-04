from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services import pipeline_runtime


class _FakeSession:
    def __init__(self, job):
        self.job = job
        self.commit_calls = 0
        self.rollback_calls = 0
        self.execute_calls: list[tuple[object, object | None]] = []

    async def get(self, model, job_id: int):
        del model
        if self.job.id == job_id:
            return self.job
        return None

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def execute(self, stmt, params=None):
        self.execute_calls.append((stmt, params))
        return None


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _job(*, job_id: int = 1, source: str = "scheduler"):
    return SimpleNamespace(
        id=job_id,
        type="collect_comments",
        payload_json={"post_id": 42, "source": source},
        attempts=1,
        max_attempts=5,
        status="running",
        last_error=None,
        retry_at=None,
        locked_by="worker-1",
        locked_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
    )


def _tg_client():
    return SimpleNamespace(operation_lock=asyncio.Lock())


@pytest.mark.asyncio
async def test_run_comment_job_marks_discussion_error_retryable(monkeypatch: pytest.MonkeyPatch):
    job = _job(source="scheduler")
    session = _FakeSession(job)
    mark_failed_calls: list[dict] = []

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "discussion_error", "error": "discussion_resolved_but_top_level_thread_unconfirmed"}

    async def _fake_mark_job_failed(_session, *, job, error, retry_base_seconds=30, retry_max_seconds=3600):
        mark_failed_calls.append(
            {
                "job": job,
                "error": error,
                "retry_base_seconds": retry_base_seconds,
                "retry_max_seconds": retry_max_seconds,
            }
        )

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)
    monkeypatch.setattr(pipeline_runtime, "mark_job_failed", _fake_mark_job_failed)

    result = await pipeline_runtime._run_comment_job(
        job=job,
        tg_client=_tg_client(),
        worker_id="worker-1",
        cc_sleep_min_ms=0,
        cc_sleep_max_ms=0,
        collect_comments_processed=0,
        collect_comments_quota_per_run=5,
        collect_comments_global_cooldown_until=None,
        collect_comments_flood_streak=0,
    )

    assert result == (0, 1, None, 0, False)
    assert mark_failed_calls == [
        {
            "job": job,
            "error": "collect_comments:discussion_error",
            "retry_base_seconds": 120,
            "retry_max_seconds": 7200,
        }
    ]
    assert job.payload_json["_job_result"]["status"] == "discussion_error"
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_run_comment_job_keeps_successful_api_job_completion(monkeypatch: pytest.MonkeyPatch):
    job = _job(source="api")
    session = _FakeSession(job)
    mark_done_calls: list[object] = []
    mark_failed_calls: list[dict] = []
    sync_calls: list[dict] = []

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "ok", "comments_saved": 3}

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job)

    async def _fake_mark_job_failed(_session, *, job, error, retry_base_seconds=30, retry_max_seconds=3600):
        mark_failed_calls.append({"job": job, "error": error})

    async def _fake_sync_post_report_staleness(_session, *, post_id, source, dependency_type, dependency_id):
        sync_calls.append(
            {
                "post_id": post_id,
                "source": source,
                "dependency_type": dependency_type,
                "dependency_id": dependency_id,
            }
        )
        return {"status": "queued", "post_id": post_id}

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)
    monkeypatch.setattr(pipeline_runtime, "mark_job_failed", _fake_mark_job_failed)
    monkeypatch.setattr(pipeline_runtime, "sync_post_report_staleness", _fake_sync_post_report_staleness)

    result = await pipeline_runtime._run_comment_job(
        job=job,
        tg_client=_tg_client(),
        worker_id="worker-1",
        cc_sleep_min_ms=0,
        cc_sleep_max_ms=0,
        collect_comments_processed=0,
        collect_comments_quota_per_run=5,
        collect_comments_global_cooldown_until=None,
        collect_comments_flood_streak=0,
    )

    assert result == (1, 1, None, 0, False)
    assert mark_done_calls == [job]
    assert mark_failed_calls == []
    assert sync_calls == [
        {
            "post_id": 42,
            "source": "api:comments_refresh",
            "dependency_type": "comments_refresh",
            "dependency_id": 42,
        }
    ]
    assert job.payload_json["_job_result"] == {
        "status": "ok",
        "comments_saved": 3,
        "post_report_sync": {"status": "queued", "post_id": 42},
    }
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_run_comment_job_keeps_no_discussion_terminal_completion(monkeypatch: pytest.MonkeyPatch):
    job = _job(source="scheduler")
    session = _FakeSession(job)
    mark_done_calls: list[object] = []

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "no_discussion", "comments_saved": 0}

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job)

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)

    result = await pipeline_runtime._run_comment_job(
        job=job,
        tg_client=_tg_client(),
        worker_id="worker-1",
        cc_sleep_min_ms=0,
        cc_sleep_max_ms=0,
        collect_comments_processed=0,
        collect_comments_quota_per_run=5,
        collect_comments_global_cooldown_until=None,
        collect_comments_flood_streak=0,
    )

    assert result == (1, 1, None, 0, False)
    assert mark_done_calls == [job]
    assert job.payload_json["_job_result"] == {"status": "no_discussion", "comments_saved": 0}
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_run_comment_job_syncs_post_report_even_for_unchanged_comment_refresh(monkeypatch: pytest.MonkeyPatch):
    job = _job(source="scheduler")
    session = _FakeSession(job)
    mark_done_calls: list[object] = []
    sync_calls: list[dict] = []

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "unchanged", "comments_saved": 2, "comments_count": 2}

    async def _fake_mark_job_done(_session, *, job):
        mark_done_calls.append(job)

    async def _fake_sync_post_report_staleness(_session, *, post_id, source, dependency_type, dependency_id):
        sync_calls.append(
            {
                "post_id": post_id,
                "source": source,
                "dependency_type": dependency_type,
                "dependency_id": dependency_id,
            }
        )
        return {"status": "unchanged", "post_id": post_id}

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)
    monkeypatch.setattr(pipeline_runtime, "mark_job_done", _fake_mark_job_done)
    monkeypatch.setattr(pipeline_runtime, "sync_post_report_staleness", _fake_sync_post_report_staleness)

    result = await pipeline_runtime._run_comment_job(
        job=job,
        tg_client=_tg_client(),
        worker_id="worker-1",
        cc_sleep_min_ms=0,
        cc_sleep_max_ms=0,
        collect_comments_processed=0,
        collect_comments_quota_per_run=5,
        collect_comments_global_cooldown_until=None,
        collect_comments_flood_streak=0,
    )

    assert result == (1, 1, None, 0, False)
    assert mark_done_calls == [job]
    assert sync_calls == [
        {
            "post_id": 42,
            "source": "scheduler:comments_refresh",
            "dependency_type": "comments_refresh",
            "dependency_id": 42,
        }
    ]


@pytest.mark.asyncio
async def test_run_comment_job_rolls_back_partial_mutations_before_retrying_reconciliation_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    job = _job(source="scheduler")
    session = _FakeSession(job)
    mark_failed_calls: list[dict] = []

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "discussion_error", "error": "comment_reconciliation_incomplete"}

    async def _fake_mark_job_failed(_session, *, job, error, retry_base_seconds=30, retry_max_seconds=3600):
        mark_failed_calls.append({"job": job, "error": error})

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)
    monkeypatch.setattr(pipeline_runtime, "mark_job_failed", _fake_mark_job_failed)

    result = await pipeline_runtime._run_comment_job(
        job=job,
        tg_client=_tg_client(),
        worker_id="worker-1",
        cc_sleep_min_ms=0,
        cc_sleep_max_ms=0,
        collect_comments_processed=0,
        collect_comments_quota_per_run=5,
        collect_comments_global_cooldown_until=None,
        collect_comments_flood_streak=0,
    )

    assert result == (0, 1, None, 0, False)
    assert session.rollback_calls == 1
    assert mark_failed_calls == [{"job": job, "error": "collect_comments:discussion_error"}]
    assert session.commit_calls == 1

