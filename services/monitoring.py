from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from client import client
from db.models import Comment, Job, Post

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def system_snapshot() -> dict:
    now = _utcnow().isoformat()
    disk = shutil.disk_usage("/")
    payload = {
        "timestamp": now,
        "host": {
            "cpu_count": os.cpu_count(),
            "pid": os.getpid(),
        },
        "disk": {
            "total_bytes": int(disk.total),
            "used_bytes": int(disk.used),
            "free_bytes": int(disk.free),
            "used_percent": round((disk.used / disk.total) * 100.0, 2) if disk.total else None,
        },
    }

    if psutil is not None:
        vm = psutil.virtual_memory()
        process = psutil.Process(os.getpid())
        payload["cpu"] = {
            "system_percent": float(psutil.cpu_percent(interval=0.1)),
            "process_percent": float(process.cpu_percent(interval=0.0)),
        }
        payload["memory"] = {
            "total_bytes": int(vm.total),
            "available_bytes": int(vm.available),
            "used_bytes": int(vm.used),
            "used_percent": float(vm.percent),
            "process_rss_bytes": int(process.memory_info().rss),
        }
    else:
        payload["cpu"] = {"system_percent": None, "process_percent": None}
        payload["memory"] = {
            "total_bytes": None,
            "available_bytes": None,
            "used_bytes": None,
            "used_percent": None,
            "process_rss_bytes": None,
        }
    return payload


async def jobs_snapshot(session: AsyncSession) -> dict:
    status_rows = (
        await session.execute(
            select(Job.status, func.count(Job.id))
            .group_by(Job.status)
            .order_by(Job.status.asc())
        )
    ).all()
    by_status = {status: int(count) for status, count in status_rows}

    now = _utcnow()
    oldest_pending = (
        await session.execute(
            select(func.min(Job.run_at)).where(Job.status == "pending")
        )
    ).scalar_one_or_none()
    pending_lag_seconds = None
    if oldest_pending is not None:
        pending_lag_seconds = max(0.0, (now - oldest_pending).total_seconds())

    oldest_retry = (
        await session.execute(
            select(func.min(Job.retry_at))
            .where(Job.status == "pending")
            .where(Job.retry_at.is_not(None))
        )
    ).scalar_one_or_none()
    retry_lag_seconds = None
    if oldest_retry is not None:
        retry_lag_seconds = max(0.0, (now - oldest_retry).total_seconds())

    return {
        "total": int(sum(by_status.values())),
        "by_status": by_status,
        "pending_lag_seconds": pending_lag_seconds,
        "retry_lag_seconds": retry_lag_seconds,
    }


async def activity_snapshot(session: AsyncSession, *, hours: int = 24) -> dict:
    since = _utcnow() - timedelta(hours=hours)
    posts_count = await session.scalar(
        select(func.count()).select_from(Post).where(Post.date >= since)
    )
    comments_count = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.date >= since)
    )
    return {
        "since": since.isoformat(),
        "posts_last_hours": int(posts_count or 0),
        "comments_last_hours": int(comments_count or 0),
    }


async def database_snapshot(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            text(
                "SELECT "
                "current_database() AS db_name, "
                "pg_database_size(current_database()) AS bytes, "
                "pg_size_pretty(pg_database_size(current_database())) AS pretty"
            )
        )
    ).first()
    if row is None:
        return {"database": None, "bytes": None, "pretty": None}
    return {
        "database": row.db_name,
        "bytes": int(row.bytes),
        "pretty": row.pretty,
    }


async def health_snapshot(session: AsyncSession) -> dict:
    started = time.perf_counter()
    db_ok = True
    db_error = None
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = repr(exc)

    db_latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    tg_connected = bool(client.is_connected())
    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "time_utc": _utcnow().isoformat(),
        "dependencies": {
            "database": {
                "ok": db_ok,
                "latency_ms": db_latency_ms,
                "error": db_error,
            },
            "telegram_client": {
                "ok": tg_connected,
                "connected": tg_connected,
            },
        },
    }
