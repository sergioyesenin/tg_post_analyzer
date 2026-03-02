from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from deps import get_session, require_roles
from db.models import Post, Comment
from services.auth import AuthUser

router = APIRouter()

@router.get("/summary")
async def monitor_summary(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    since = datetime.utcnow() - timedelta(hours=24)

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
