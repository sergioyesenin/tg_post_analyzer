from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from deps import get_session
from db.models import Post, Channel, Comment
from schemas.post import PostCardOut, PostDetailOut
from schemas.comment import CommentOut

router = APIRouter()

@router.get("/top", response_model=list[PostCardOut])
async def top_posts(
    date_from: datetime,
    date_to: datetime,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Post)
        .join(Channel)
        .where(Post.date >= date_from)
        .where(Post.date <= date_to)
        .order_by(desc(Post.comments_count))
        .limit(limit)
        .options(selectinload(Post.channel))
    )

    result = await session.execute(stmt)
    posts = result.scalars().all()

    return [
        PostCardOut(
            id=p.id,
            channel_id=p.channel_id,
            channel_username=p.channel.username,
            published_at=p.date,
            text_preview=(p.text[:200] if p.text else None),
            comments_count=p.comments_count,
        )
        for p in posts
    ]


@router.get("/{post_id}", response_model=PostDetailOut)
async def get_post(post_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/{post_id}/comments", response_model=list[CommentOut])
async def get_comments(post_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Comment).where(Comment.post_id == post_id)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return result.scalars().all()
