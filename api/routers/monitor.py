from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from deps import get_session, require_roles
from db.models import Post, Comment
from services.auth import AuthUser, write_audit_log
from services.monitoring import (
    activity_snapshot,
    database_snapshot,
    health_snapshot,
    jobs_snapshot,
    system_snapshot,
)

router = APIRouter()

@router.get("/summary")
async def monitor_summary(
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    since = datetime.utcnow() - timedelta(hours=24)

    posts_count = await session.scalar(
        select(func.count()).select_from(Post).where(Post.date >= since)
    )

    comments_count = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.date >= since)
    )

    payload = {
        "posts_last_24h": posts_count,
        "comments_last_24h": comments_count,
    }
    await write_audit_log(
        session,
        action="monitor.summary.read",
        actor_user_id=current_user.id,
        target_type="monitor",
        details=payload,
    )
    await session.commit()
    return payload


@router.get("/db-size")
async def db_size(
    current_user: AuthUser = Depends(require_roles("admin")),
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

    payload = {
        "database": row.db_name,
        "bytes": int(row.bytes),
        "pretty": row.pretty,
    }
    await write_audit_log(
        session,
        action="monitor.db_size.read",
        actor_user_id=current_user.id,
        target_type="monitor",
        details=payload,
    )
    await session.commit()
    return payload


@router.get("/health")
async def monitor_health(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    return await health_snapshot(session)


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
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    payload = {
        "health": await health_snapshot(session),
        "system": system_snapshot(),
        "jobs": await jobs_snapshot(session),
        "activity_24h": await activity_snapshot(session, hours=24),
        "database": await database_snapshot(session),
    }
    await write_audit_log(
        session,
        action="monitor.full.read",
        actor_user_id=current_user.id,
        target_type="monitor",
        details={
            "status": payload["health"].get("status"),
            "pending_jobs": payload["jobs"].get("by_status", {}).get("pending", 0),
        },
    )
    await session.commit()
    return payload
