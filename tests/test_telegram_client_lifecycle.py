from __future__ import annotations

import asyncio
import sqlite3

from client import config as client_config
from client import telegram as client_telegram


def test_resolve_session_name_supports_suffix_and_unique_pid():
    assert client_config.resolve_session_name(base_session="base", session_suffix="", unique_session_per_run=False) == "base"
    assert client_config.resolve_session_name(base_session="base", session_suffix="api", unique_session_per_run=False) == "base_api"
    assert (
        client_config.resolve_session_name(
            base_session="base",
            session_suffix="worker",
            unique_session_per_run=True,
            pid=123,
        )
        == "base_worker_123"
    )


def test_build_telegram_client_uses_resolved_session_name(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeTelethonClient:
        def __init__(self, *, session, api_id, api_hash, flood_sleep_threshold):
            captured["session"] = session
            captured["api_id"] = api_id
            captured["api_hash"] = api_hash
            captured["flood_sleep_threshold"] = flood_sleep_threshold

    monkeypatch.setattr(
        client_telegram,
        "load_client_settings",
        lambda: client_config.TelegramClientSettings(
            session="base.session",
            api_id=1,
            api_hash="hash",
            flood_sleep_threshold=3,
        ),
    )
    monkeypatch.setattr(client_telegram, "TelegramClient", _FakeTelethonClient)
    monkeypatch.setattr(client_telegram.os, "getpid", lambda: 777)

    handle = client_telegram.build_telegram_client(session_suffix="pipeline", unique_session_per_run=True)

    assert isinstance(handle, client_telegram.TelegramClientHandle)
    assert captured == {
        "session": "base.session_pipeline_777",
        "api_id": 1,
        "api_hash": "hash",
        "flood_sleep_threshold": 3,
    }


def test_ensure_telegram_client_started_retries_locked_session(monkeypatch):
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    class _FakeClient:
        def __init__(self):
            self.connected = False

        def is_connected(self):
            return self.connected

        async def start(self):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise sqlite3.OperationalError("database is locked")
            self.connected = True

    async def _fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr(client_telegram.asyncio, "sleep", _fake_sleep)

    asyncio.run(client_telegram.ensure_telegram_client_started(_FakeClient(), op_name="test.start"))

    assert attempts["count"] == 3
    assert sleep_calls == [1.5, 1.5]
