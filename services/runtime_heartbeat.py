from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RuntimeHeartbeat
from db.session import AsyncSessionLocal

HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 90


def build_runtime_heartbeat_key(runtime_name: str) -> str:
    """
    Оставлено для обратной совместимости с кодом/тестами, которые
    строят legacy-ключ вида 'runtime.<name>'.

    В новой схеме сам ключ не используется как PK — идентификатором
    служит колонка runtime_heartbeats.runtime_name.
    """
    return f"runtime.{runtime_name}"


def _normalize_runtime_name(runtime_name: str) -> str:
    name = (runtime_name or "").strip()
    if not name:
        raise ValueError("runtime_name must not be empty")
    # Поддерживаем оба варианта обращения: "ai_pipeline" и "runtime.ai_pipeline".
    if name.startswith("runtime."):
        name = name[len("runtime."):]
    return name


async def get_runtime_heartbeat(session: AsyncSession, *, runtime_name: str) -> dict | None:
    """
    Читает heartbeat из таблицы runtime_heartbeats.

    Возвращает dict в том же формате, что использовался ранее при хранении
    в app_settings, чтобы потребители (services/monitoring.py и др.) не менялись:

        {
            "runtime": "<name>",
            "status": "<status>",
            "heartbeat_at": "<ISO>",
            "details": {...},
        }
    """
    normalized = _normalize_runtime_name(runtime_name)
    row = (
        await session.execute(
            select(RuntimeHeartbeat).where(RuntimeHeartbeat.runtime_name == normalized)
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    heartbeat_at: datetime = row.heartbeat_at
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)

    return {
        "runtime": normalized,
        "status": str(row.status),
        "heartbeat_at": heartbeat_at.isoformat(),
        "details": deepcopy(row.details_json) if isinstance(row.details_json, dict) else {},
    }


async def persist_runtime_heartbeat(
    *,
    runtime_name: str,
    status: str,
    details: dict | None = None,
    now: datetime | None = None,
) -> None:
    """
    Upsert heartbeat в runtime_heartbeats.

    Идемпотентен по runtime_name. Заменяет прежний путь через app_settings.
    """
    normalized = _normalize_runtime_name(runtime_name)
    heartbeat_ts = now or datetime.now(timezone.utc)
    if heartbeat_ts.tzinfo is None:
        heartbeat_ts = heartbeat_ts.replace(tzinfo=timezone.utc)

    details_payload = deepcopy(details or {})

    async with AsyncSessionLocal() as session:
        stmt = (
            insert(RuntimeHeartbeat)
            .values(
                runtime_name=normalized,
                status=str(status),
                heartbeat_at=heartbeat_ts,
                details_json=details_payload,
                updated_at=heartbeat_ts,
            )
            .on_conflict_do_update(
                index_elements=[RuntimeHeartbeat.runtime_name],
                set_={
                    "status": str(status),
                    "heartbeat_at": heartbeat_ts,
                    "details_json": details_payload,
                    "updated_at": heartbeat_ts,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()