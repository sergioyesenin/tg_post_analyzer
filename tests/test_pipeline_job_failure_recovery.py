from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services import pipeline_runtime


class _FakeSession:
    def __init__(self, job=None, *, rollback_raises: Exception | None = None, commit_raises: Exception | None = None) -> None:
        self.job = job
        self.rollback_raises = rollback_raises
        self.commit_raises = commit_raises
        self.rollback_calls = 0
        self.commit_calls = 0
        self.get_calls: list[tuple[object, int]] = []

    async def rollback(self) -> None:
        self.rollback_calls += 1
        if self.rollback_raises is not None:
            raise self.rollback_raises

    async def get(self, model, job_id: int):
        self.get_calls.append((model, job_id))
        return self.job

    async def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_raises is not None:
            raise self.commit_raises


def test_persist_job_failure_after_exception_rolls_back_and_commits(monkeypatch):
    calls: list[dict] = []

    async def _fake_mark_job_failed(session, *, job, error, retry_base_seconds=30, retry_max_seconds=3600):
        calls.append(
            {
                "session": session,
                "job": job,
                "error": error,
                "retry_base_seconds": retry_base_seconds,
                "retry_max_seconds": retry_max_seconds,
            }
        )

    session = _FakeSession(job=SimpleNamespace(id=42))
    monkeypatch.setattr(pipeline_runtime, "mark_job_failed", _fake_mark_job_failed)

    result = asyncio.run(
        pipeline_runtime._persist_job_failure_after_exception(
            session,
            job_id=42,
            error="job_unexpected:build_post_links:RuntimeError:boom",
            retry_base_seconds=120,
            retry_max_seconds=7200,
        )
    )

    assert result is True
    assert session.rollback_calls == 1
    assert session.commit_calls == 1
    assert calls[0]["error"] == "job_unexpected:build_post_links:RuntimeError:boom"
    assert calls[0]["retry_base_seconds"] == 120
    assert calls[0]["retry_max_seconds"] == 7200


def test_persist_job_failure_after_exception_returns_false_when_followup_persist_fails(monkeypatch):
    async def _fake_mark_job_failed(session, *, job, error, retry_base_seconds=30, retry_max_seconds=3600):
        return None

    session = _FakeSession(job=SimpleNamespace(id=42), commit_raises=RuntimeError("commit failed"))
    monkeypatch.setattr(pipeline_runtime, "mark_job_failed", _fake_mark_job_failed)

    result = asyncio.run(
        pipeline_runtime._persist_job_failure_after_exception(
            session,
            job_id=42,
            error="job_unexpected:test",
        )
    )

    assert result is False
    assert session.rollback_calls == 2
