from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Comment, Post


async def count_posts_since(
    session: AsyncSession,
    *,
    since: datetime,
) -> int:
    stmt = select(func.count()).select_from(Post).where(Post.date >= since)
    return int(await session.scalar(stmt) or 0)


async def count_comments_since(
    session: AsyncSession,
    *,
    since: datetime,
) -> int:
    stmt = select(func.count()).select_from(Comment).where(Comment.date >= since)
    return int(await session.scalar(stmt) or 0)