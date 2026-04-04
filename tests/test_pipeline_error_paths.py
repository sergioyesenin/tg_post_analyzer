from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from services import pipeline_runtime
from services import pipeline_runtime_common
from services.jobs import JobType


def test_with_session_lock_retry_retries_locked_session(monkeypatch: pytest.MonkeyPatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    async def _fake_sleep(delay: float):
        sleep_calls.append(delay)

    async def _op():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    monkeypatch.setattr(pipeline_runtime.asyncio, "sleep", _fake_sleep)

    result = asyncio.run(
        pipeline_runtime.with_session_lock_retry(lambda: _op(), op_name="client.start", retries=3, delay_sec=0.01)
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep_calls == [0.01, 0.01]


def test_with_session_lock_retry_does_not_swallow_non_lock_errors():
    async def _op():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(pipeline_runtime.with_session_lock_retry(lambda: _op(), op_name="client.start", retries=3, delay_sec=0.01))


def test_clamp_positive_int_respects_bounds_and_fallback():
    assert pipeline_runtime._clamp_positive_int(4, default=2, minimum=1, maximum=8) == 4
    assert pipeline_runtime._clamp_positive_int(0, default=2, minimum=1, maximum=8) == 1
    assert pipeline_runtime._clamp_positive_int(99, default=2, minimum=1, maximum=8) == 8
    assert pipeline_runtime._clamp_positive_int(None, default=3, minimum=1, maximum=8) == 3


def test_split_jobs_for_telegram_worker_separates_comment_jobs():
    jobs = [
        SimpleNamespace(id=1, type=JobType.COLLECT_COMMENTS),
        SimpleNamespace(id=2, type=JobType.REFRESH_COMMENTS),
        SimpleNamespace(id=3, type=JobType.BUILD_POST_REPORT),
        SimpleNamespace(id=4, type=JobType.ARCHIVE_RETENTION),
    ]

    comment_jobs, other_jobs = pipeline_runtime.split_jobs_for_telegram_worker(jobs)

    assert [job.id for job in comment_jobs] == [1, 2]
    assert [job.id for job in other_jobs] == [3, 4]


def test_build_post_links_priority_is_higher_than_collect_comments():
    post = SimpleNamespace(comments_count=1000, views=100000, involvement=0.9)

    collect_priority = pipeline_runtime._collect_comments_job_priority(post=post, scan_index=0)

    assert pipeline_runtime.PRIORITY_BUILD_POST_LINKS < collect_priority


@pytest.mark.asyncio
async def test_sleep_until_next_telegram_cycle_uses_backward_compatible_default_threshold(
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}
    sleep_calls: list[int] = []

    async def _fake_has_due_priority_job(*, allowed_types, max_priority):
        captured["allowed_types"] = allowed_types
        captured["max_priority"] = max_priority
        return False

    async def _fake_sleep(delay: int):
        sleep_calls.append(delay)

    monkeypatch.setattr(pipeline_runtime_common, "has_due_priority_job", _fake_has_due_priority_job)
    monkeypatch.setattr(pipeline_runtime_common.asyncio, "sleep", _fake_sleep)

    await pipeline_runtime_common.sleep_until_next_telegram_cycle(target_seconds=1)

    assert captured["allowed_types"] == {JobType.REFRESH_COMMENTS}
    assert captured["max_priority"] == 20
    assert sleep_calls == [1]


@pytest.mark.asyncio
async def test_run_telegram_cycle_serializes_channel_ingest_with_shared_telethon_session(monkeypatch):
    channels = [
        SimpleNamespace(id=1, username="one"),
        SimpleNamespace(id=2, username="two"),
        SimpleNamespace(id=3, username="three"),
    ]
    concurrent = {"current": 0, "max": 0}

    async def _fake_get_all_settings(_session):
        return {
            "ingest": {
                "lookback_days": 3,
                "max_posts_per_channel": 10,
                "comment_first_delay_hours": 2,
                "comment_interval_hours": 2,
                "comment_window_hours": 24,
                "comment_schedule_jitter_seconds": 0,
            },
            "jobs": {
                "job_batch_size": 10,
                "collect_comments_quota_per_run": 1,
                "done_retention_days": 14,
                "dead_letter_retention_days": 90,
                "cleanup_batch_size": 1000,
                "job_worker_concurrency": 2,
            },
            "retention": {
                "retention_days": 30,
                "archive_batch_size": 1000,
            },
        }

    async def _fake_process_channel(_client, channel, **_kwargs):
        concurrent["current"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["current"])
        await asyncio.sleep(0)
        concurrent["current"] -= 1
        return channel.id

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "_get_active_channels", lambda: asyncio.sleep(0, result=channels))
    monkeypatch.setattr(pipeline_runtime, "_process_channel", _fake_process_channel)
    monkeypatch.setattr(pipeline_runtime, "run_telegram_link_jobs_until_idle", lambda **_kwargs: asyncio.sleep(0, result=0))
    monkeypatch.setattr(pipeline_runtime, "count_incomplete_link_jobs", lambda: asyncio.sleep(0, result=0))
    monkeypatch.setattr(pipeline_runtime, "run_telegram_jobs", lambda **_kwargs: asyncio.sleep(0, result=0))
    monkeypatch.setattr(pipeline_runtime, "retention_scheduler_enabled", lambda _settings: True)

    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", _FakeSessionContext)

    result = await pipeline_runtime.run_telegram_cycle(
        client=object(),
        days=3,
        max_posts_per_channel_arg=10,
        comment_first_delay_hours_arg=2,
        comment_interval_hours_arg=2,
        comment_window_hours_arg=24,
        job_batch_size_arg=10,
        retention_days_arg=30,
        archive_batch_size_arg=1000,
        skip_rebuild_graphs=True,
        worker_id="worker-1",
    )

    assert result.processed_posts == 6
    assert result.executed_jobs == 0
    assert concurrent["max"] == 1

