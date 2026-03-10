from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import pipeline


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

    monkeypatch.setattr(pipeline.asyncio, "sleep", _fake_sleep)

    result = asyncio.run(pipeline._with_session_lock_retry(lambda: _op(), op_name="client.start", retries=3, delay_sec=0.01))

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep_calls == [0.01, 0.01]


def test_with_session_lock_retry_does_not_swallow_non_lock_errors():
    async def _op():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(pipeline._with_session_lock_retry(lambda: _op(), op_name="client.start", retries=3, delay_sec=0.01))


def test_clamp_positive_int_respects_bounds_and_fallback():
    assert pipeline._clamp_positive_int(4, default=2, minimum=1, maximum=8) == 4
    assert pipeline._clamp_positive_int(0, default=2, minimum=1, maximum=8) == 1
    assert pipeline._clamp_positive_int(99, default=2, minimum=1, maximum=8) == 8
    assert pipeline._clamp_positive_int(None, default=3, minimum=1, maximum=8) == 3


def test_split_locked_jobs_by_type_separates_collect_comments():
    jobs = [
        SimpleNamespace(id=1, type=pipeline.JobType.COLLECT_COMMENTS),
        SimpleNamespace(id=2, type=pipeline.JobType.BUILD_POST_REPORT),
        SimpleNamespace(id=3, type=pipeline.JobType.ARCHIVE_RETENTION),
        SimpleNamespace(id=4, type=pipeline.JobType.COLLECT_COMMENTS),
    ]

    collect_jobs, other_jobs = pipeline._split_locked_jobs_by_type(jobs)

    assert [job.id for job in collect_jobs] == [1, 4]
    assert [job.id for job in other_jobs] == [2, 3]
