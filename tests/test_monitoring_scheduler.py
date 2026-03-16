from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from services import monitoring


class _FakeSession:
    def __init__(self, scalar_values: list[object], execute_result: object = object()) -> None:
        self._scalar_values = list(scalar_values)
        self._execute_result = execute_result

    async def scalar(self, _stmt):
        if not self._scalar_values:
            raise AssertionError("Unexpected scalar() call")
        return self._scalar_values.pop(0)

    async def execute(self, _stmt):
        return self._execute_result


def test_scheduled_run_bounds_returns_previous_and_next_window():
    last_run_at, next_run_at = monitoring._scheduled_run_bounds(
        now=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
        hour=3,
        minute=0,
        tz_name="Europe/Minsk",
    )

    assert last_run_at.isoformat() == "2026-03-11T00:00:00+00:00"
    assert next_run_at.isoformat() == "2026-03-12T00:00:00+00:00"


def test_scheduler_snapshot_reports_disabled_mode():
    session = _FakeSession([None, None])
    monitoring_heartbeat = {
        "status": "running",
        "heartbeat_at": "2026-03-11T12:00:00+00:00",
        "details": {"pid": 123},
    }

    original_tz = monitoring.settings.tz
    monitoring.settings.tz = "Europe/Minsk"
    original_get_runtime_heartbeat = monitoring.get_runtime_heartbeat
    monitoring.get_runtime_heartbeat = lambda _session, runtime_name: asyncio.sleep(0, result=monitoring_heartbeat)

    try:
        snapshot = asyncio.run(
            monitoring.scheduler_snapshot(
                session,
                effective_settings={
                    "features": {"scheduler_retention_v2": False},
                    "scheduler": {"enabled": True, "retention_hour": 3, "retention_minute": 0},
                },
            )
        )
    finally:
        monitoring.settings.tz = original_tz
        monitoring.get_runtime_heartbeat = original_get_runtime_heartbeat

    assert snapshot["status"] == "disabled"
    assert snapshot["retention_mode"] == "telegram_fallback"
    assert snapshot["enabled"] is False
    assert snapshot["last_enqueue_at"] is None


def test_scheduler_snapshot_reports_missing_recent_enqueue(monkeypatch):
    now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
    old_enqueue = datetime(2026, 3, 10, 23, 50, tzinfo=timezone.utc)
    session = _FakeSession([old_enqueue, old_enqueue])

    monkeypatch.setattr(monitoring, "_utcnow", lambda: now)
    monkeypatch.setattr(monitoring.settings, "tz", "Europe/Minsk")
    monkeypatch.setattr(
        monitoring,
        "get_runtime_heartbeat",
        lambda _session, runtime_name: asyncio.sleep(
            0,
            result={"status": "running", "heartbeat_at": now.isoformat(), "details": {"pid": 1}},
        ),
    )

    snapshot = asyncio.run(
        monitoring.scheduler_snapshot(
            session,
            effective_settings={
                "features": {"scheduler_retention_v2": True},
                "scheduler": {"enabled": True, "retention_hour": 3, "retention_minute": 0},
            },
        )
    )

    assert snapshot["status"] == "late_or_missing"
    assert snapshot["retention_mode"] == "scheduler"
    assert snapshot["enabled"] is True
    assert snapshot["last_enqueue_at"] == "2026-03-10T23:50:00+00:00"
    assert snapshot["process"]["status"] == "running"


def test_scheduler_snapshot_reports_stale_process(monkeypatch):
    now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
    recent_enqueue = datetime(2026, 3, 11, 11, 55, tzinfo=timezone.utc)
    session = _FakeSession([recent_enqueue, recent_enqueue])

    monkeypatch.setattr(monitoring, "_utcnow", lambda: now)
    monkeypatch.setattr(monitoring.settings, "tz", "Europe/Minsk")
    monkeypatch.setattr(
        monitoring,
        "get_runtime_heartbeat",
        lambda _session, runtime_name: asyncio.sleep(
            0,
            result={"status": "running", "heartbeat_at": "2026-03-11T11:58:00+00:00", "details": {"pid": 22}},
        ),
    )

    snapshot = asyncio.run(
        monitoring.scheduler_snapshot(
            session,
            effective_settings={
                "features": {"scheduler_retention_v2": True},
                "scheduler": {"enabled": True, "retention_hour": 3, "retention_minute": 0},
            },
        )
    )

    assert snapshot["status"] == "process_stale"
    assert snapshot["process"]["status"] == "stale"
    assert snapshot["process"]["pid"] == 22


def test_health_snapshot_includes_scheduler_dependency(monkeypatch):
    now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession([now, now], execute_result=object())

    monkeypatch.setattr(monitoring, "_utcnow", lambda: now)
    monkeypatch.setattr(monitoring.time, "perf_counter", lambda: 1.0)
    monkeypatch.setattr(monitoring.settings, "tz", "Europe/Minsk")
    monkeypatch.setattr(
        monitoring,
        "get_runtime_heartbeat",
        lambda _session, runtime_name: asyncio.sleep(
            0,
            result={"status": "running", "heartbeat_at": now.isoformat(), "details": {"pid": 77}},
        ),
    )

    payload = asyncio.run(
        monitoring.health_snapshot(
            session,
            effective_settings={
                "features": {"scheduler_retention_v2": True},
                "scheduler": {"enabled": True, "retention_hour": 3, "retention_minute": 0},
            },
        )
    )

    assert payload["status"] == "ok"
    assert payload["dependencies"]["telegram_client"] == {
        "ok": True,
        "connected": True,
        "status": "ok",
        "last_heartbeat_at": "2026-03-11T12:00:00+00:00",
    }
    assert payload["dependencies"]["ai_pipeline"] == {
        "ok": True,
        "status": "ok",
        "last_heartbeat_at": "2026-03-11T12:00:00+00:00",
    }
    assert payload["dependencies"]["scheduler"] == {
        "ok": True,
        "enabled": True,
        "status": "ok",
        "retention_mode": "scheduler",
        "next_expected_run_at": "2026-03-12T00:00:00+00:00",
        "last_enqueue_at": "2026-03-11T12:00:00+00:00",
        "last_heartbeat_at": "2026-03-11T12:00:00+00:00",
        "process_status": "running",
    }


def test_health_snapshot_degrades_when_scheduler_process_is_missing(monkeypatch):
    now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession([now, now], execute_result=object())

    monkeypatch.setattr(monitoring, "_utcnow", lambda: now)
    monkeypatch.setattr(monitoring.time, "perf_counter", lambda: 1.0)
    monkeypatch.setattr(monitoring.settings, "tz", "Europe/Minsk")
    monkeypatch.setattr(
        monitoring,
        "get_runtime_heartbeat",
        lambda _session, runtime_name: asyncio.sleep(0, result=None),
    )

    payload = asyncio.run(
        monitoring.health_snapshot(
            session,
            effective_settings={
                "features": {"scheduler_retention_v2": True},
                "scheduler": {"enabled": True, "retention_hour": 3, "retention_minute": 0},
            },
        )
    )

    assert payload["status"] == "degraded"
    assert payload["dependencies"]["telegram_client"]["status"] == "process_missing"
    assert payload["dependencies"]["ai_pipeline"]["status"] == "process_missing"
    assert payload["dependencies"]["scheduler"]["status"] == "process_missing"
    assert payload["dependencies"]["scheduler"]["ok"] is False


def test_evaluate_alerts_warns_when_scheduler_enabled_but_not_ok():
    payload = monitoring.evaluate_alerts(
        health={
            "dependencies": {
                "database": {"latency_ms": 10},
                "telegram_client": {"connected": True, "status": "ok"},
                "ai_pipeline": {"ok": True, "status": "ok"},
                "scheduler": {"enabled": True, "ok": False, "status": "process_stale"},
            }
        },
        system={"disk": {"used_percent": 10}, "memory": {"used_percent": 10}},
        jobs={"by_status": {"pending": 0}, "pending_lag_seconds": 0, "retry_lag_seconds": 0, "dead_letter_count": 0},
        thresholds={},
        pipeline={},
    )

    assert payload["status"] == "warning"
    assert payload["alerts_count"] == 1
    assert payload["alerts"][0]["metric"] == "scheduler.status"


def test_pipeline_snapshot_uses_recent_window_for_collect_comments_rates(monkeypatch):
    now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession(
        [
            now,
            now,
            12,
            10,
            4,
            1,
            1,
            None,
            None,
        ]
    )

    monkeypatch.setattr(monitoring, "_utcnow", lambda: now)
    monkeypatch.setattr(
        monitoring,
        "get_runtime_heartbeat",
        lambda _session, runtime_name: asyncio.sleep(
            0,
            result={"status": "running", "heartbeat_at": now.isoformat(), "details": {"pid": 5}},
        ),
    )

    payload = asyncio.run(monitoring.pipeline_snapshot(session, retention_days=30, window_hours=2))

    assert payload["collect_comments"] == {
        "window_since": "2026-03-11T10:00:00+00:00",
        "error_pool_size": 4,
        "flood_count": 1,
        "rpc_count": 1,
        "flood_rate": 0.25,
        "rpc_rate": 0.25,
    }
    assert payload["runtime"]["telegram_pipeline"]["status"] == "ok"
    assert payload["runtime"]["ai_pipeline"]["status"] == "ok"


def test_runtime_topology_expectations_exposes_canonical_roles():
    payload = monitoring.runtime_topology_expectations()

    assert [role["role"] for role in payload["roles"]] == [
        "api",
        "scheduler",
        "telegram_pipeline",
        "ai_pipeline",
    ]
    assert payload["monitoring_expectations"]["api"].startswith("Use HTTP/API health")
    assert "runtime.scheduler" in payload["monitoring_expectations"]["scheduler"]


def test_system_snapshot_marks_api_runtime_scope_and_uses_non_blocking_cpu(monkeypatch):
    cpu_intervals: list[float] = []

    class _FakeVm:
        total = 1000
        available = 400
        used = 600
        percent = 60.0

    class _FakeProcessMemory:
        rss = 321

    class _FakeProcess:
        def __init__(self, _pid):
            self.pid = _pid

        def cpu_percent(self, *, interval):
            cpu_intervals.append(interval)
            return 1.5

        def memory_info(self):
            return _FakeProcessMemory()

    class _FakePsutil:
        @staticmethod
        def virtual_memory():
            return _FakeVm()

        @staticmethod
        def Process(pid):
            return _FakeProcess(pid)

        @staticmethod
        def cpu_percent(*, interval):
            cpu_intervals.append(interval)
            return 2.5

    monkeypatch.setattr(monitoring, "psutil", _FakePsutil())
    monkeypatch.setattr(monitoring, "_utcnow", lambda: datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc))

    payload = monitoring.system_snapshot()

    assert payload["runtime"]["role"] == "api"
    assert payload["runtime"]["entrypoint"] == "python scripts/run_api.py"
    assert cpu_intervals == [0.0, 0.0]
