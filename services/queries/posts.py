from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Channel, Comment, Post


async def get_post_by_id(session: AsyncSession, *, post_id: int) -> Post | None:
    return (
        await session.execute(select(Post).where(Post.id == post_id))
    ).scalar_one_or_none()


async def get_post_with_channel_by_id(
    session: AsyncSession, *, post_id: int
) -> tuple[Post, Channel] | None:
    stmt = (
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def get_post_with_channel_by_post_id(
    session: AsyncSession,
    post_id: int,
) -> tuple[Post, Channel] | None:
    stmt = (
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]

async def list_top_posts(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    limit: int,
) -> list[Post]:
    stmt = (
        select(Post)
        .join(Channel)
        .where(Post.date >= date_from)
        .where(Post.date <= date_to)
        .order_by(desc(Post.comments_count))
        .limit(limit)
        .options(selectinload(Post.channel))
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_comments_for_post(
    session: AsyncSession, *, post_id: int
) -> list[Comment]:
    return list(
        (
            await session.execute(select(Comment).where(Comment.post_id == post_id))
        ).scalars().all()
    )