from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSetting
from db.session import AsyncSessionLocal
from services.settings_store import upsert_setting

HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 90


def build_runtime_heartbeat_key(runtime_name: str) -> str:
    return f"runtime.{runtime_name}"


async def get_runtime_heartbeat(session: AsyncSession, *, runtime_name: str) -> dict | None:
    key = build_runtime_heartbeat_key(runtime_name)
    row = (await session.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if row is None or not isinstance(row.value_json, dict):
        return None
    return deepcopy(row.value_json)


async def persist_runtime_heartbeat(
    *,
    runtime_name: str,
    status: str,
    details: dict | None = None,
    now: datetime | None = None,
) -> None:
    payload = {
        "runtime": runtime_name,
        "status": status,
        "heartbeat_at": (now or datetime.now(timezone.utc)).isoformat(),
        "details": deepcopy(details or {}),
    }
    async with AsyncSessionLocal() as session:
        await upsert_setting(
            session,
            key=build_runtime_heartbeat_key(runtime_name),
            value_json=payload,
            description=f"Runtime heartbeat for {runtime_name}",
            updated_by_user_id=None,
        )
        await session.commit()
