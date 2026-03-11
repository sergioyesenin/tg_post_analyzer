from __future__ import annotations

from datetime import datetime, timezone

import pytest

import services.scheduler_dispatch as scheduler_dispatch
from services.scheduler_dispatch import enqueue_daily_retention_jobs, retention_scheduler_enabled
from services.scheduler_runtime import build_scheduler_db_url, register_periodic_jobs


class _FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def add_job(self, func, **kwargs) -> None:
        self.calls.append({"func": func, **kwargs})


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.commits = 0

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        self.commits += 1


def test_build_scheduler_db_url_converts_asyncpg_to_psycopg2():
    assert (
        build_scheduler_db_url("postgresql+asyncpg://user:pass@localhost:5432/app")
        == "postgresql+psycopg2://user:pass@localhost:5432/app"
    )


def test_build_scheduler_db_url_leaves_other_schemes_intact():
    assert build_scheduler_db_url("sqlite:///local.db") == "sqlite:///local.db"


def test_build_scheduler_db_url_handles_password_with_reserved_url_chars():
    assert (
        build_scheduler_db_url("postgresql+asyncpg://user:GQD+uF]G3hnXPeXRub*gJ+M6+aGoX)wn@localhost:5432/app")
        == "postgresql+psycopg2://user:GQD+uF%5DG3hnXPeXRub%2AgJ+M6+aGoX%29wn@localhost:5432/app"
    )


def test_retention_scheduler_enabled_requires_both_flag_and_scheduler_switch():
    assert retention_scheduler_enabled({"features": {"scheduler_retention_v2": True}, "scheduler": {"enabled": True}}) is True
    assert retention_scheduler_enabled({"features": {"scheduler_retention_v2": True}, "scheduler": {"enabled": False}}) is False
    assert retention_scheduler_enabled({"features": {"scheduler_retention_v2": False}, "scheduler": {"enabled": True}}) is False


def test_register_periodic_jobs_adds_retention_daily_job():
    scheduler = _FakeScheduler()
    register_periodic_jobs(
        scheduler,
        effective_settings={"scheduler": {"retention_hour": 4, "retention_minute": 15}},
    )

    assert len(scheduler.calls) == 1
    job = scheduler.calls[0]
    assert job["id"] == "retention.daily"
    assert job["replace_existing"] is True
    assert job["coalesce"] is True
    assert job["max_instances"] == 1


@pytest.mark.asyncio
async def test_enqueue_daily_retention_jobs_uses_effective_settings_defaults(monkeypatch):
    calls: list[dict] = []

    async def _fake_enqueue_job(session, **kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(scheduler_dispatch, "enqueue_job", _fake_enqueue_job)

    session = _FakeAsyncSession()
    result = await enqueue_daily_retention_jobs(
        session,
        effective_settings={
            "retention": {"retention_days": 45, "archive_batch_size": 222},
            "jobs": {"done_retention_days": 9, "dead_letter_retention_days": 77, "cleanup_batch_size": 333},
        },
        now=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
    )

    assert result == {
        "date": "2026-03-11",
        "archive_job_created": 1,
        "jobs_retention_job_created": 1,
    }
    assert session.commits == 1
    assert len(calls) == 2
    assert calls[0]["job_type"] == "archive_retention"
    assert calls[0]["payload"] == {"retention_days": 45, "batch_limit": 222}
    assert calls[0]["dedupe_key"] == "archive_retention:2026-03-11"
    assert calls[1]["job_type"] == "jobs_retention"
    assert calls[1]["payload"] == {
        "done_retention_days": 9,
        "dead_letter_retention_days": 77,
        "batch_limit": 333,
    }
    assert calls[1]["dedupe_key"] == "jobs_retention:2026-03-11"


@pytest.mark.asyncio
async def test_dispatch_daily_retention_returns_disabled_without_enqueue(monkeypatch):
    async def _fake_get_all_settings(_session):
        return {"features": {"scheduler_retention_v2": False}, "scheduler": {"enabled": True}}

    async def _unexpected_enqueue(*args, **kwargs):
        raise AssertionError("enqueue_daily_retention_jobs should not be called when scheduler is disabled")

    monkeypatch.setattr(scheduler_dispatch, "AsyncSessionLocal", _FakeAsyncSession)
    monkeypatch.setattr(scheduler_dispatch, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(scheduler_dispatch, "enqueue_daily_retention_jobs", _unexpected_enqueue)

    result = await scheduler_dispatch.dispatch_daily_retention()

    assert result == {
        "status": "disabled",
        "archive_job_created": 0,
        "jobs_retention_job_created": 0,
    }


@pytest.mark.asyncio
async def test_dispatch_daily_retention_returns_ok_payload_when_enabled(monkeypatch):
    async def _fake_get_all_settings(_session):
        return {"features": {"scheduler_retention_v2": True}, "scheduler": {"enabled": True}}

    async def _fake_enqueue_daily_retention_jobs(session, **kwargs):
        assert kwargs["effective_settings"]["scheduler"]["enabled"] is True
        return {
            "date": "2026-03-11",
            "archive_job_created": 1,
            "jobs_retention_job_created": 0,
        }

    monkeypatch.setattr(scheduler_dispatch, "AsyncSessionLocal", _FakeAsyncSession)
    monkeypatch.setattr(scheduler_dispatch, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(scheduler_dispatch, "enqueue_daily_retention_jobs", _fake_enqueue_daily_retention_jobs)

    result = await scheduler_dispatch.dispatch_daily_retention()

    assert result == {
        "status": "ok",
        "date": "2026-03-11",
        "archive_job_created": 1,
        "jobs_retention_job_created": 0,
    }
