from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from deps import get_session, require_roles
from db.models import Post, Comment
from services.auth import AuthUser, write_audit_log

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
