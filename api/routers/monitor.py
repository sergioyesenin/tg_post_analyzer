from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from deps import get_session, require_roles
from services.settings_store import get_all_settings
from db.models import Post, Comment
from services.auth import AuthUser
from services.monitoring import (
    activity_snapshot,
    database_snapshot,
    evaluate_alerts,
    health_snapshot,
    jobs_snapshot,
    pipeline_snapshot,
    runtime_topology_expectations,
    scheduler_snapshot,
    system_snapshot,
)

router = APIRouter()

@router.get("/summary")
async def monitor_summary(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    posts_count = await session.scalar(
        select(func.count()).select_from(Post).where(Post.date >= since)
    )

    comments_count = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.date >= since)
    )

    return {
        "posts_last_24h": posts_count,
        "comments_last_24h": comments_count,
    }


@router.get("/db-size")
async def db_size(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
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

    return {
        "database": row.db_name,
        "bytes": int(row.bytes),
        "pretty": row.pretty,
    }


@router.get("/health")
async def monitor_health(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    effective_settings = await get_all_settings(session)
    return await health_snapshot(session, effective_settings=effective_settings)


@router.get("/system")
async def monitor_system(
    _: AuthUser = Depends(require_roles("admin")),
):
    return system_snapshot()


@router.get("/jobs")
async def monitor_jobs(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    return await jobs_snapshot(session)


@router.get("/full")
async def monitor_full(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    effective_settings = await get_all_settings(session)
    monitor_settings = effective_settings.get("monitor", {})
    retention_settings = effective_settings.get("retention", {})
    retention_days = int(retention_settings.get("retention_days", 30))
    scheduler = await scheduler_snapshot(session, effective_settings=effective_settings)
    health = await health_snapshot(session, effective_settings=effective_settings, scheduler=scheduler)
    system = system_snapshot()
    jobs = await jobs_snapshot(session)
    pipeline = await pipeline_snapshot(session, retention_days=retention_days)
    alerts = evaluate_alerts(
        health=health,
        system=system,
        jobs=jobs,
        pipeline=pipeline,
        thresholds=monitor_settings,
    )
    payload = {
        "health": health,
        "system": system,
        "jobs": jobs,
        "pipeline": pipeline,
        "scheduler": scheduler,
        "alerts": alerts,
        "activity_24h": await activity_snapshot(session, hours=24),
        "database": await database_snapshot(session),
    }
    return payload


@router.get("/scheduler")
async def monitor_scheduler(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    effective_settings = await get_all_settings(session)
    return await scheduler_snapshot(session, effective_settings=effective_settings)


@router.get("/alerts")
async def monitor_alerts(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    effective_settings = await get_all_settings(session)
    monitor_settings = effective_settings.get("monitor", {})
    retention_settings = effective_settings.get("retention", {})
    retention_days = int(retention_settings.get("retention_days", 30))
    health = await health_snapshot(session, effective_settings=effective_settings)
    system = system_snapshot()
    jobs = await jobs_snapshot(session)
    pipeline = await pipeline_snapshot(session, retention_days=retention_days)
    payload = evaluate_alerts(
        health=health,
        system=system,
        jobs=jobs,
        pipeline=pipeline,
        thresholds=monitor_settings,
    )
    return payload


@router.get("/runtime-topology")
async def monitor_runtime_topology(
    _: AuthUser = Depends(require_roles("admin")),
):
    return runtime_topology_expectations()


@router.get("/pipeline")
async def monitor_pipeline(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    effective_settings = await get_all_settings(session)
    retention_settings = effective_settings.get("retention", {})
    retention_days = int(retention_settings.get("retention_days", 30))
    return await pipeline_snapshot(session, retention_days=retention_days)
