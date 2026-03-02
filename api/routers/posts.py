from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from deps import get_session, require_roles
from db.models import Post, Channel, Comment
from schemas.post import PostCardOut, PostDetailOut
from schemas.comment import CommentOut
from services.TGqueries import update_post_comments
from services.auth import AuthUser

router = APIRouter()

@router.get("/top", response_model=list[PostCardOut])
async def top_posts(
    date_from: datetime,
    date_to: datetime,
    limit: int = 20,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
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
            date=p.date,
            text_preview=(p.text.splitlines()[0] if p.text else None),
            comments_count=p.comments_count,
            views=p.views,
            involvement=p.involvement,
        )
        for p in posts
    ]


@router.get("/{post_id}", response_model=PostDetailOut)
async def get_post(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/{post_id}/comments", response_model=list[CommentOut])
async def get_comments(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Comment).where(Comment.post_id == post_id)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return result.scalars().all()

@router.post("/{post_id}/comments/update")
async def update_comments(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        result = await update_post_comments(session, post_id)

    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Post not found")
    return result
