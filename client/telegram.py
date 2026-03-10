from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from telethon import TelegramClient

from client.config import load_client_settings, resolve_session_name

logger = logging.getLogger(__name__)


def is_session_locked_error(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


async def with_session_lock_retry(coro_factory, *, op_name: str, retries: int = 3, delay_sec: float = 1.5):
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not is_session_locked_error(exc) or attempt >= retries:
                raise
            logger.warning(
                "Telethon session locked op=%s retry=%s/%s delay_sec=%.1f",
                op_name,
                attempt,
                retries,
                delay_sec,
            )
            await asyncio.sleep(delay_sec)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{op_name} failed unexpectedly")


@dataclass
class TelegramClientHandle:
    client: TelegramClient
    operation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    async def __call__(self, *args, **kwargs):
        return await self.client(*args, **kwargs)

    async def start(self):
        return await self.client.start()

    async def disconnect(self):
        return await self.client.disconnect()

    def is_connected(self) -> bool:
        return bool(self.client.is_connected())

    async def ensure_started(self, *, op_name: str = "tg_client.start") -> None:
        await ensure_telegram_client_started(self, op_name=op_name)


def build_telegram_client(*, session_suffix: str = "", unique_session_per_run: bool = False) -> TelegramClientHandle:
    client_settings = load_client_settings()
    session_name = resolve_session_name(
        base_session=client_settings.session,
        session_suffix=session_suffix,
        unique_session_per_run=unique_session_per_run,
        pid=os.getpid(),
    )
    return TelegramClientHandle(
        client=TelegramClient(
            session=session_name,
            api_id=client_settings.api_id,
            api_hash=client_settings.api_hash,
            flood_sleep_threshold=client_settings.flood_sleep_threshold,
        )
    )


def unwrap_telegram_client(client_or_handle):
    return client_or_handle.client if isinstance(client_or_handle, TelegramClientHandle) else client_or_handle


async def ensure_telegram_client_started(client_or_handle, *, op_name: str = "tg_client.start") -> None:
    client = unwrap_telegram_client(client_or_handle)
    if not client.is_connected():
        await with_session_lock_retry(lambda: client.start(), op_name=op_name)


_shared_client_handle = build_telegram_client()
client = _shared_client_handle


__all__ = [
    "TelegramClientHandle",
    "build_telegram_client",
    "client",
    "ensure_telegram_client_started",
    "is_session_locked_error",
    "unwrap_telegram_client",
    "with_session_lock_retry",
]
