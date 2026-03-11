from __future__ import annotations

import pytest

from scripts import run_scheduler


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_calls: list[bool] = []

    def start(self) -> None:
        self.started = True

    def get_jobs(self):
        return [type("_Job", (), {"id": "retention.daily"})()]

    def shutdown(self, *, wait: bool) -> None:
        self.shutdown_calls.append(wait)


class _FakeStopEvent:
    async def wait(self) -> None:
        return None


@pytest.mark.asyncio
async def test_main_async_returns_without_starting_scheduler_when_disabled(monkeypatch):
    build_scheduler_called = False

    async def _fake_get_all_settings(_session):
        return {"features": {"scheduler_retention_v2": False}, "scheduler": {"enabled": True}}

    def _fake_build_scheduler():
        nonlocal build_scheduler_called
        build_scheduler_called = True
        return _FakeScheduler()

    monkeypatch.setattr(run_scheduler, "AsyncSessionLocal", lambda: _FakeSessionContext())
    monkeypatch.setattr(run_scheduler, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(run_scheduler, "build_scheduler", _fake_build_scheduler)

    await run_scheduler.main_async()

    assert build_scheduler_called is False


@pytest.mark.asyncio
async def test_main_async_starts_registers_and_shuts_down_scheduler(monkeypatch):
    scheduler = _FakeScheduler()
    register_calls: list[dict] = []
    heartbeat_calls: list[dict] = []

    async def _fake_get_all_settings(_session):
        return {"features": {"scheduler_retention_v2": True}, "scheduler": {"enabled": True, "retention_hour": 4}}

    def _fake_register_periodic_jobs(scheduler_obj, *, effective_settings):
        register_calls.append({"scheduler": scheduler_obj, "effective_settings": effective_settings})

    async def _fake_persist_runtime_heartbeat(**kwargs):
        heartbeat_calls.append(kwargs)

    monkeypatch.setattr(run_scheduler, "AsyncSessionLocal", lambda: _FakeSessionContext())
    monkeypatch.setattr(run_scheduler, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(run_scheduler, "build_scheduler", lambda: scheduler)
    monkeypatch.setattr(run_scheduler, "register_periodic_jobs", _fake_register_periodic_jobs)
    monkeypatch.setattr(run_scheduler, "persist_runtime_heartbeat", _fake_persist_runtime_heartbeat)
    monkeypatch.setattr(run_scheduler.asyncio, "Event", _FakeStopEvent)

    await run_scheduler.main_async()

    assert scheduler.started is True
    assert scheduler.shutdown_calls == [False]
    assert register_calls == [
        {
            "scheduler": scheduler,
            "effective_settings": {
                "features": {"scheduler_retention_v2": True},
                "scheduler": {"enabled": True, "retention_hour": 4},
            },
        }
    ]
    assert [call["status"] for call in heartbeat_calls] == ["running", "stopped"]
    assert heartbeat_calls[0]["details"]["jobs"] == ["retention.daily"]


@pytest.mark.asyncio
async def test_main_async_shuts_down_scheduler_if_initial_heartbeat_fails(monkeypatch):
    scheduler = _FakeScheduler()

    async def _fake_get_all_settings(_session):
        return {"features": {"scheduler_retention_v2": True}, "scheduler": {"enabled": True}}

    async def _failing_persist_runtime_heartbeat(**kwargs):
        if kwargs["status"] == "running":
            raise RuntimeError("heartbeat write failed")

    monkeypatch.setattr(run_scheduler, "AsyncSessionLocal", lambda: _FakeSessionContext())
    monkeypatch.setattr(run_scheduler, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(run_scheduler, "build_scheduler", lambda: scheduler)
    monkeypatch.setattr(run_scheduler, "register_periodic_jobs", lambda scheduler_obj, *, effective_settings: None)
    monkeypatch.setattr(run_scheduler, "persist_runtime_heartbeat", _failing_persist_runtime_heartbeat)

    with pytest.raises(RuntimeError, match="heartbeat write failed"):
        await run_scheduler.main_async()

    assert scheduler.started is True
    assert scheduler.shutdown_calls == [False]
