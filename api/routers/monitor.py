from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from deps import get_session
from db.models import Post, Comment

router = APIRouter()

@router.get("/summary")
async def monitor_summary(session: AsyncSession = Depends(get_session)):
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
