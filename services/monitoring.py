from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from client import client
from config import settings
from db.models import Comment, Job, JobDeadLetter, Post
from services.jobs import JobType
from services.runtime_heartbeat import HEARTBEAT_TIMEOUT_SECONDS, get_runtime_heartbeat
from services.scheduler_dispatch import retention_scheduler_enabled

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scheduled_run_bounds(*, now: datetime, hour: int, minute: int, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    scheduled_today = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now >= scheduled_today:
        last_expected_local = scheduled_today
        next_expected_local = scheduled_today + timedelta(days=1)
    else:
        last_expected_local = scheduled_today - timedelta(days=1)
        next_expected_local = scheduled_today
    return last_expected_local.astimezone(timezone.utc), next_expected_local.astimezone(timezone.utc)


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

    dead_letter_count = int(
        await session.scalar(
            select(func.count()).select_from(JobDeadLetter)
        )
        or 0
    )

    return {
        "total": int(sum(by_status.values())),
        "by_status": by_status,
        "pending_lag_seconds": pending_lag_seconds,
        "retry_lag_seconds": retry_lag_seconds,
        "dead_letter_count": dead_letter_count,
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


async def pipeline_snapshot(session: AsyncSession, *, retention_days: int = 30) -> dict:
    now = _utcnow()
    hour_ago = now - timedelta(hours=1)
    cutoff = now - timedelta(days=max(1, int(retention_days)))

    last_ingested_at = await session.scalar(select(func.max(Post.created_at)))
    ingest_lag_seconds = None
    if last_ingested_at is not None:
        ingest_lag_seconds = max(0.0, (now - last_ingested_at).total_seconds())

    last_post_date = await session.scalar(select(func.max(Post.date)))
    post_freshness_lag_seconds = None
    if last_post_date is not None:
        post_freshness_lag_seconds = max(0.0, (now - last_post_date).total_seconds())

    jobs_created_1h = int(
        await session.scalar(
            select(func.count()).select_from(Job).where(Job.created_at >= hour_ago)
        )
        or 0
    )
    jobs_done_1h = int(
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "done")
            .where(Job.updated_at >= hour_ago)
        )
        or 0
    )
    backlog_delta_1h = jobs_created_1h - jobs_done_1h

    cc_total_with_error = int(
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.type == "collect_comments")
            .where(Job.last_error.is_not(None))
        )
        or 0
    )
    cc_flood = int(
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.type == "collect_comments")
            .where(Job.last_error.like("collect_comments:flood_wait:%"))
        )
        or 0
    )
    cc_rpc = int(
        await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.type == "collect_comments")
            .where(
                Job.last_error.in_(
                    [
                        "collect_comments:rpc_error",
                        "collect_comments:entity_error",
                        "collect_comments:discussion_error",
                    ]
                )
            )
        )
        or 0
    )
    flood_rate = (cc_flood / cc_total_with_error) if cc_total_with_error > 0 else 0.0
    rpc_rate = (cc_rpc / cc_total_with_error) if cc_total_with_error > 0 else 0.0

    oldest_unarchived_post_date = await session.scalar(
        select(func.min(Post.date)).where(Post.date < cutoff)
    )
    archive_lag_seconds = None
    if oldest_unarchived_post_date is not None:
        archive_lag_seconds = max(0.0, (cutoff - oldest_unarchived_post_date).total_seconds())

    last_archive_job_at = await session.scalar(
        select(func.max(Job.updated_at))
        .where(Job.type == "archive_retention")
        .where(Job.status == "done")
    )
    archive_job_lag_seconds = None
    if last_archive_job_at is not None:
        archive_job_lag_seconds = max(0.0, (now - last_archive_job_at).total_seconds())

    return {
        "ingest": {
            "last_ingested_at": last_ingested_at.isoformat() if last_ingested_at else None,
            "ingest_lag_seconds": ingest_lag_seconds,
            "last_post_date": last_post_date.isoformat() if last_post_date else None,
            "post_freshness_lag_seconds": post_freshness_lag_seconds,
        },
        "collect_comments": {
            "error_pool_size": cc_total_with_error,
            "flood_count": cc_flood,
            "rpc_count": cc_rpc,
            "flood_rate": round(flood_rate, 4),
            "rpc_rate": round(rpc_rate, 4),
        },
        "backlog": {
            "jobs_created_1h": jobs_created_1h,
            "jobs_done_1h": jobs_done_1h,
            "delta_1h": backlog_delta_1h,
        },
        "archive": {
            "retention_cutoff": cutoff.isoformat(),
            "oldest_unarchived_post_date": oldest_unarchived_post_date.isoformat() if oldest_unarchived_post_date else None,
            "archive_lag_seconds": archive_lag_seconds,
            "last_archive_job_at": last_archive_job_at.isoformat() if last_archive_job_at else None,
            "archive_job_lag_seconds": archive_job_lag_seconds,
        },
    }


async def scheduler_snapshot(session: AsyncSession, *, effective_settings: dict) -> dict:
    now = _utcnow()
    scheduler_settings = effective_settings.get("scheduler", {})
    scheduler_enabled = retention_scheduler_enabled(effective_settings)
    retention_hour = int(scheduler_settings.get("retention_hour", 3))
    retention_minute = int(scheduler_settings.get("retention_minute", 0))
    last_expected_run_at, next_expected_run_at = _scheduled_run_bounds(
        now=now,
        hour=retention_hour,
        minute=retention_minute,
        tz_name=settings.tz,
    )

    archive_enqueue_at = await session.scalar(
        select(func.max(Job.created_at)).where(Job.type == JobType.ARCHIVE_RETENTION)
    )
    jobs_retention_enqueue_at = await session.scalar(
        select(func.max(Job.created_at)).where(Job.type == JobType.JOBS_RETENTION)
    )
    last_enqueue_at = max(
        [value for value in [archive_enqueue_at, jobs_retention_enqueue_at] if value is not None],
        default=None,
    )
    heartbeat_payload = await get_runtime_heartbeat(session, runtime_name="scheduler")
    heartbeat_at_raw = None if heartbeat_payload is None else heartbeat_payload.get("heartbeat_at")
    heartbeat_at = None
    if isinstance(heartbeat_at_raw, str):
        try:
            heartbeat_at = datetime.fromisoformat(heartbeat_at_raw)
        except ValueError:
            heartbeat_at = None
    heartbeat_age_seconds = None
    if heartbeat_at is not None:
        heartbeat_age_seconds = max(0.0, (now - heartbeat_at).total_seconds())

    process_state = "missing"
    if heartbeat_payload is not None:
        process_state = str(heartbeat_payload.get("status") or "unknown")
        if process_state == "running" and heartbeat_age_seconds is not None and heartbeat_age_seconds > HEARTBEAT_TIMEOUT_SECONDS:
            process_state = "stale"

    enqueue_lag_seconds = None
    if last_enqueue_at is not None:
        enqueue_lag_seconds = max(0.0, (now - last_enqueue_at).total_seconds())

    if not scheduler_enabled:
        status = "disabled"
    elif process_state in {"missing", "stale", "stopped", "unknown"}:
        status = f"process_{process_state}"
    elif last_enqueue_at is None or last_enqueue_at < last_expected_run_at:
        status = "late_or_missing"
    else:
        status = "ok"

    return {
        "status": status,
        "retention_mode": "scheduler" if scheduler_enabled else "telegram_fallback",
        "enabled": scheduler_enabled,
        "timezone": settings.tz,
        "schedule": {
            "retention_hour": retention_hour,
            "retention_minute": retention_minute,
            "last_expected_run_at": last_expected_run_at.isoformat(),
            "next_expected_run_at": next_expected_run_at.isoformat(),
        },
        "process": {
            "status": process_state if scheduler_enabled else "disabled",
            "last_heartbeat_at": heartbeat_at.isoformat() if heartbeat_at else None,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "heartbeat_timeout_seconds": HEARTBEAT_TIMEOUT_SECONDS,
            "pid": None if heartbeat_payload is None else ((heartbeat_payload.get("details") or {}).get("pid")),
        },
        "last_archive_enqueue_at": archive_enqueue_at.isoformat() if archive_enqueue_at else None,
        "last_jobs_retention_enqueue_at": jobs_retention_enqueue_at.isoformat() if jobs_retention_enqueue_at else None,
        "last_enqueue_at": last_enqueue_at.isoformat() if last_enqueue_at else None,
        "enqueue_lag_seconds": enqueue_lag_seconds,
    }


async def health_snapshot(session: AsyncSession, *, effective_settings: dict | None = None) -> dict:
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
    scheduler = None
    if effective_settings is not None:
        scheduler = await scheduler_snapshot(session, effective_settings=effective_settings)
    status = "ok" if db_ok else "degraded"
    if scheduler is not None and scheduler.get("status") not in {"ok", "disabled"}:
        status = "degraded"
    dependencies = {
        "database": {
            "ok": db_ok,
            "latency_ms": db_latency_ms,
            "error": db_error,
        },
        "telegram_client": {
            "ok": tg_connected,
            "connected": tg_connected,
        },
    }
    if scheduler is not None:
        dependencies["scheduler"] = {
            "ok": scheduler.get("status") in {"ok", "disabled"},
            "enabled": scheduler.get("enabled"),
            "status": scheduler.get("status"),
            "retention_mode": scheduler.get("retention_mode"),
            "next_expected_run_at": ((scheduler.get("schedule") or {}).get("next_expected_run_at")),
            "last_enqueue_at": scheduler.get("last_enqueue_at"),
            "last_heartbeat_at": ((scheduler.get("process") or {}).get("last_heartbeat_at")),
            "process_status": ((scheduler.get("process") or {}).get("status")),
        }

    return {
        "status": status,
        "time_utc": _utcnow().isoformat(),
        "dependencies": dependencies,
    }


def evaluate_alerts(
    *,
    health: dict,
    system: dict,
    jobs: dict,
    thresholds: dict,
    pipeline: dict | None = None,
) -> dict:
    alerts: list[dict] = []

    def _add_alert(severity: str, metric: str, current, threshold, message: str) -> None:
        alerts.append(
            {
                "severity": severity,
                "metric": metric,
                "current": current,
                "threshold": threshold,
                "message": message,
            }
        )

    def _check_numeric(metric: str, current, warn_key: str, crit_key: str, message: str) -> None:
        if current is None:
            return
        warn_val = thresholds.get(warn_key)
        crit_val = thresholds.get(crit_key)
        if crit_val is not None and current >= crit_val:
            _add_alert("critical", metric, current, crit_val, message)
            return
        if warn_val is not None and current >= warn_val:
            _add_alert("warning", metric, current, warn_val, message)

    disk_used_percent = (system.get("disk") or {}).get("used_percent")
    memory_used_percent = (system.get("memory") or {}).get("used_percent")
    pending_jobs = (jobs.get("by_status") or {}).get("pending", 0)
    pending_lag_seconds = jobs.get("pending_lag_seconds")
    retry_lag_seconds = jobs.get("retry_lag_seconds")
    db_latency_ms = ((health.get("dependencies") or {}).get("database") or {}).get("latency_ms")
    tg_connected = ((health.get("dependencies") or {}).get("telegram_client") or {}).get("connected")
    dead_letter_count = jobs.get("dead_letter_count")
    scheduler_dependency = ((health.get("dependencies") or {}).get("scheduler") or {})
    scheduler_ok = scheduler_dependency.get("ok")
    scheduler_enabled = scheduler_dependency.get("enabled")
    scheduler_status = scheduler_dependency.get("status")
    pipeline = pipeline or {}
    pipeline_ingest_lag = ((pipeline.get("ingest") or {}).get("ingest_lag_seconds"))
    pipeline_backlog_delta = ((pipeline.get("backlog") or {}).get("delta_1h"))
    pipeline_flood_rate = ((pipeline.get("collect_comments") or {}).get("flood_rate"))
    pipeline_rpc_rate = ((pipeline.get("collect_comments") or {}).get("rpc_rate"))
    pipeline_archive_lag = ((pipeline.get("archive") or {}).get("archive_lag_seconds"))

    _check_numeric(
        "disk.used_percent",
        disk_used_percent,
        "disk_used_percent_warn",
        "disk_used_percent_crit",
        "Disk usage is above threshold.",
    )
    _check_numeric(
        "memory.used_percent",
        memory_used_percent,
        "memory_used_percent_warn",
        "memory_used_percent_crit",
        "Memory usage is above threshold.",
    )
    _check_numeric(
        "jobs.pending",
        pending_jobs,
        "pending_jobs_warn",
        "pending_jobs_crit",
        "Pending jobs count is above threshold.",
    )
    _check_numeric(
        "jobs.pending_lag_seconds",
        pending_lag_seconds,
        "pending_lag_seconds_warn",
        "pending_lag_seconds_crit",
        "Pending jobs lag is above threshold.",
    )
    _check_numeric(
        "jobs.retry_lag_seconds",
        retry_lag_seconds,
        "retry_lag_seconds_warn",
        "retry_lag_seconds_crit",
        "Retry lag is above threshold.",
    )
    _check_numeric(
        "database.latency_ms",
        db_latency_ms,
        "database_latency_ms_warn",
        "database_latency_ms_crit",
        "Database latency is above threshold.",
    )
    _check_numeric(
        "jobs.dead_letter_count",
        dead_letter_count,
        "dead_letter_count_warn",
        "dead_letter_count_crit",
        "Dead-letter queue has items.",
    )
    _check_numeric(
        "pipeline.ingest_lag_seconds",
        pipeline_ingest_lag,
        "ingest_lag_seconds_warn",
        "ingest_lag_seconds_crit",
        "Ingestion lag is above threshold.",
    )
    _check_numeric(
        "pipeline.backlog_delta_1h",
        pipeline_backlog_delta,
        "backlog_delta_1h_warn",
        "backlog_delta_1h_crit",
        "Backlog growth per hour is above threshold.",
    )
    _check_numeric(
        "pipeline.collect_comments.flood_rate",
        pipeline_flood_rate,
        "collect_comments_flood_rate_warn",
        "collect_comments_flood_rate_crit",
        "Collect-comments FloodWait rate is above threshold.",
    )
    _check_numeric(
        "pipeline.collect_comments.rpc_rate",
        pipeline_rpc_rate,
        "collect_comments_rpc_rate_warn",
        "collect_comments_rpc_rate_crit",
        "Collect-comments RPC error rate is above threshold.",
    )
    _check_numeric(
        "pipeline.archive_lag_seconds",
        pipeline_archive_lag,
        "archive_lag_seconds_warn",
        "archive_lag_seconds_crit",
        "Archive lag is above threshold.",
    )

    if thresholds.get("telegram_disconnected_is_warn", True) and tg_connected is False:
        _add_alert(
            "warning",
            "telegram.connected",
            tg_connected,
            True,
            "Telegram client is disconnected.",
        )
    if scheduler_enabled and scheduler_ok is False:
        _add_alert(
            "warning",
            "scheduler.status",
            scheduler_status,
            "ok",
            "Scheduler process or retention schedule state is degraded.",
        )

    status = "ok"
    if any(a["severity"] == "critical" for a in alerts):
        status = "critical"
    elif alerts:
        status = "warning"
    return {
        "status": status,
        "alerts_count": len(alerts),
        "alerts": alerts,
    }
